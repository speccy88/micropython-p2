"""Differential tests for dirty eviction, partial pages, bulk coherence and retry."""

import random
import struct
import unittest
from types import SimpleNamespace
from test_packages import load


class Backing:
    def __init__(self, n):
        self.buf = bytearray(n)
        self.closed = False
        self.fail_read = self.fail_write = False

    def capacity(self):
        return len(self.buf)

    def alloc(self, n):
        return Backing(n)

    def fill(self, off, size, value):
        self.buf[off : off + size] = bytes([value]) * size

    def readinto(self, off, buf):
        if off + len(buf) > len(self.buf):
            raise ValueError("bounds")
        buf[:] = self.buf[off : off + len(buf)]
        if self.fail_read:
            buf[0] = 47
            raise OSError("injected short read")
        return len(buf)

    def write(self, off, buf):
        if off + len(buf) > len(self.buf):
            raise ValueError("bounds")
        if self.fail_write:
            self.buf[off : off + 1] = buf[:1]
            raise OSError("injected short write")
        self.buf[off : off + len(buf)] = buf
        return len(buf)

    def close(self):
        self.closed = True


mod = load("p2array", p2=SimpleNamespace(PSRAM=lambda: Backing(0)))


class Arrays(unittest.TestCase):
    def test_eviction_and_bulk(self):
        backing = Backing(174)
        a = mod.Array("H", 87, region=backing, pages=2, page_bytes=32)
        ref = [0] * len(a)
        randomizer = random.Random(115200)
        for _ in range(760):
            pos = randomizer.randrange(87)
            if randomizer.randrange(3):
                ref[pos] = randomizer.randrange(65536)
                a[pos] = ref[pos]
            else:
                self.assertEqual(a[pos], ref[pos])
            if randomizer.randrange(12) == 3:
                pos = randomizer.randrange(84)
                values = [randomizer.randrange(65536) for _ in range(4)]
                blob = struct.pack("<4H", *values)
                a.writefrom(pos, blob)
                ref[pos : pos + 4] = values
            if randomizer.randrange(8) == 1:
                pos = randomizer.randrange(84)
                dest = bytearray(8)
                a.readinto(pos, dest)
                self.assertEqual(dest, struct.pack("<4H", *ref[pos : pos + 4]))
        a.close()
        self.assertEqual(backing.buf, struct.pack("<87H", *ref))
        self.assertFalse(backing.closed)
        a.close()
        with self.assertRaises(ValueError):
            a[0]

    def test_failed_eviction(self):
        b = Backing(128)
        a = mod.Array("I", 32, region=b, pages=1, page_bytes=32)
        a[0] = 0x12345678
        b.fail_write = True
        with self.assertRaises(OSError):
            a[8]
        self.assertEqual(a[0], 0x12345678)
        with self.assertRaises(OSError):
            a.close()
        b.fail_write = False
        b.fail_read = True
        with self.assertRaises(OSError):
            a[8]
        b.fail_read = False
        self.assertEqual(a[8], 0)
        self.assertEqual(a[0], 0x12345678)
        a.close()

    def test_bounds_and_formats(self):
        for code, value in (
            ("b", -128),
            ("B", 255),
            ("h", -32000),
            ("H", 65535),
            ("i", -0x80000000),
            ("I", 0xFFFFFFFF),
            ("f", 1.25),
        ):
            a = mod.Array(code, 17)
            self.assertEqual(a[0], 0)
            a[-1] = value
            self.assertEqual(a[16], value)
            with self.assertRaises(IndexError):
                a[-18]
            with self.assertRaises(IndexError):
                a[17] = value
            self.assertEqual(a.readinto(17, bytearray()), 0)
            with self.assertRaises(ValueError):
                a.writefrom(17, b"x")
            with self.assertRaises(TypeError):
                a.readinto(0, bytes(a.itemsize))
            a.close()
        a = mod.Array("B", 8)
        with self.assertRaises(OverflowError):
            a[0] = 256
        for kw in [dict(pages=0), dict(page_bytes=35), dict(pages=8, page_bytes=4096)]:
            with self.assertRaises(ValueError):
                mod.Array("B", 8, **kw)
        with self.assertRaises(ValueError):
            mod.Array("H", 5, region=Backing(8))

    def test_8_mib_random_offsets(self):
        b = Backing(8 << 20)
        a = mod.Array("I", len(b.buf) // 4, region=b, pages=2, page_bytes=64)
        for k in range(1024):
            a[(k * 65537) % len(a)] = k
        for k in reversed(range(1024)):
            self.assertEqual(a[(k * 65537) % len(a)], k)
        self.assertEqual(a.cache_bytes(), 128)
        a.close()


if __name__ == "__main__":
    unittest.main()
