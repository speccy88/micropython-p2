"""Test-only file-backed PSRAM surrogate for an unmodified Unix MicroPython VM.

Run in an isolated temporary directory created by host_mpy_array.sh.
"""

import os

sequence = 0


class Region:
    def __init__(self, size):
        global sequence
        sequence += 1
        self.name = "external-%d.bin" % sequence
        self.file = open(self.name, "w+b")
        self.size = size
        self.file.seek(size - 1)
        self.file.write(b"\x00")

    def capacity(self):
        return self.size

    def _seek(self, offset, size):
        if self.file is None or offset < 0 or size > self.size - offset:
            raise ValueError("invalid backing access")
        self.file.seek(offset)

    def readinto(self, offset, buf):
        self._seek(offset, len(buf))
        if self.file.readinto(buf) != len(buf):
            raise OSError("short read")
        return len(buf)

    def read(self, offset, size):
        self._seek(offset, size)
        return self.file.read(size)

    def write(self, offset, data):
        self._seek(offset, len(data))
        if self.file.write(data) != len(data):
            raise OSError("short write")
        return len(data)

    def fill(self, offset, size, value):
        self._seek(offset, size)
        page = bytes((value,)) * 256
        while size:
            n = min(size, len(page))
            self.file.write(page[:n])
            size -= n

    def close(self):
        if self.file is not None:
            self.file.close()
            os.remove(self.name)
            self.file = None


class PSRAM:
    def alloc(self, size):
        return Region(size)
