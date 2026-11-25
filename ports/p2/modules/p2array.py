"""Typed, paged random access to P2 external RAM. On-die buffers stay bounded."""

# SPDX-License-Identifier: MIT
import struct
from p2 import PSRAM

# width, inclusive minimum and maximum; floats are packed by struct.
_FORMATS = {
    "B": (1, 0, 255),
    "b": (1, -128, 127),
    "H": (2, 0, 65535),
    "h": (2, -32768, 32767),
    "I": (4, 0, 0xFFFFFFFF),
    "i": (4, -0x80000000, 0x7FFFFFFF),
    "f": (4, None, None),
}


class Array:
    """A little-endian typed array. No hub pointer or buffer interface is exported.

    New allocations are zeroed by default. A supplied region is borrowed and
    preserved by default. Its caller must retain exclusive access until close.
    """

    def __init__(self, typecode, length, *, region=None, page_bytes=256, pages=2, zero=None):
        if typecode not in _FORMATS:
            raise ValueError("expected B b H h I i or f")
        width, self._lo, self._hi = _FORMATS[typecode]
        if not isinstance(length, int) or not 0 < length <= (32 << 20) // width:
            raise ValueError("invalid length")
        if (
            not isinstance(page_bytes, int)
            or not 32 <= page_bytes <= 4096
            or page_bytes & (page_bytes - 1)
        ):
            raise ValueError("page size must be a power of two in 32..4096")
        if not isinstance(pages, int) or not 1 <= pages <= 8 or pages * page_bytes > 16384:
            raise ValueError("cache exceeds 8 pages or 16 KiB")
        self._format = "<" + typecode
        if struct.calcsize(self._format) != width:
            raise ValueError("unsupported firmware format")
        if typecode == "f":
            struct.pack(self._format, 0)
        self.typecode, self.itemsize = typecode, width
        self._length, self._bytes = length, length * width
        self._page_bytes = page_bytes
        self._buffers = [bytearray(page_bytes) for _ in range(pages)]
        self._starts = [-1] * pages
        self._dirty = [False] * pages
        self._order = list(range(pages))
        self._busy = False
        self._region = None
        self._owned = region is None
        if region is None:
            region = PSRAM().alloc(self._bytes)
        elif region.capacity() < self._bytes:
            raise ValueError("backing region too small")
        try:
            initialize = self._owned if zero is None else zero
            if initialize:
                region.fill(0, self._bytes, 0)
        except BaseException:
            if self._owned:
                region.close()
            raise
        self._region = region

    def __len__(self):
        return self._length

    def _enter(self):
        if self._region is None:
            raise ValueError("array is closed")
        if self._busy:
            raise OSError(16)
        self._busy = True

    def _index(self, index, allow_end=False):
        if not isinstance(index, int):
            raise TypeError("integer index required")
        if index < 0:
            index += self._length
        if index < 0 or index > self._length or (index == self._length and not allow_end):
            raise IndexError("array index")
        return index * self.itemsize

    def _page_buffer(self, slot):
        start = self._starts[slot]
        count = min(self._bytes - start, self._page_bytes)
        if count == self._page_bytes:
            return self._buffers[slot]
        return memoryview(self._buffers[slot])[:count]

    def _save(self, slot):
        if self._dirty[slot]:
            self._region.write(self._starts[slot], self._page_buffer(slot))
            self._dirty[slot] = False

    def _page(self, pos):
        start = pos & -self._page_bytes
        # Sequential element access normally stays on the most recent page.
        # Its LRU position is already correct.
        slot = self._order[-1]
        if self._starts[slot] == start:
            return slot
        # The least recently used page is first. A failed replacement read
        # invalidates that tag because the transfer may have modified its bytes.
        slot = -1
        for i in self._order:
            if self._starts[i] == start:
                slot = i
                break
        if slot < 0:
            slot = self._order[0]
            self._save(slot)
            self._starts[slot] = start
            try:
                self._region.readinto(start, self._page_buffer(slot))
            except BaseException:
                self._starts[slot] = -1
                raise
        self._order.remove(slot)
        self._order.append(slot)
        return slot

    def __getitem__(self, index):
        self._enter()
        try:
            pos = self._index(index)
            slot = self._page(pos)
            return struct.unpack_from(self._format, self._buffers[slot], pos - self._starts[slot])[
                0
            ]
        finally:
            self._busy = False

    def __setitem__(self, index, value):
        self._enter()
        try:
            pos = self._index(index)
            if self._lo is not None:
                if not isinstance(value, int):
                    raise TypeError("integer value required")
                if value < self._lo or value > self._hi:
                    raise OverflowError("element out of range")
            slot = self._page(pos)
            struct.pack_into(self._format, self._buffers[slot], pos - self._starts[slot], value)
            self._dirty[slot] = True
        finally:
            self._busy = False

    def flush(self):
        self._enter()
        try:
            for i in range(len(self._starts)):
                self._save(i)
        finally:
            self._busy = False

    def _bulk(self, index, data, write):
        self._enter()
        try:
            if not isinstance(data, bytearray) and not (write and isinstance(data, bytes)):
                raise TypeError("use a hub bytearray or source bytes")
            pos = self._index(index, True)
            size = len(data)
            if size % self.itemsize or size > self._bytes - pos:
                raise ValueError("window outside array or partial element")
            if size == 0:
                return 0
            for i in range(len(self._starts)):
                start = self._starts[i]
                if start >= 0 and pos < start + self._page_bytes and start < pos + size:
                    self._save(i)
                    if write:
                        self._starts[i] = -1
            if write:
                self._region.write(pos, data)
            else:
                self._region.readinto(pos, data)
            return size // self.itemsize
        finally:
            self._busy = False

    def readinto(self, index, destination):
        """Copy whole elements into a hub bytearray. Return the element count."""
        return self._bulk(index, destination, False)

    def writefrom(self, index, source):
        """Copy little-endian packed elements directly to storage."""
        return self._bulk(index, source, True)

    def cache_bytes(self):
        return self._page_bytes * len(self._buffers)

    def close(self):
        if self._region is None:
            return
        self._enter()
        try:
            for i in range(len(self._starts)):
                self._save(i)
            if self._owned:
                self._region.close()
            self._region = None
            self._buffers = ()
        finally:
            self._busy = False

    def __enter__(self):
        if self._region is None:
            raise ValueError("array is closed")
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()
