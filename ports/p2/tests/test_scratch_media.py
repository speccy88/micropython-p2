"""Host tests for scratch selection, NOR backup/restore and ROM FAT layout checks."""

import argparse
from contextlib import redirect_stdout
import hashlib
import io
import struct
import unittest

import scratch_media as media
import sd_boot


class Nor:
    def __init__(self):
        self.data = bytearray(b"\x00" * media.SECTOR)

    def readblocks(self, index, buf):
        assert index == 0
        buf[:] = self.data
        return 0

    def ioctl(self, op, arg):
        assert arg == 0 and op in (3, 6)
        if op == 6:
            self.data[:] = b"\xff" * media.SECTOR
        return 0

    def writeblocks(self, i, data, offset):
        assert i == 0 and 0 <= offset <= media.SECTOR - len(data)
        for j, value in enumerate(data, offset):
            self.data[j] &= value
        return 0


class Board:
    def __init__(self):
        self.globals = {"flash": Nor()}

    def exec(self, code):
        out = io.StringIO()
        with redirect_stdout(out):
            exec(code, self.globals)
        return out.getvalue().encode()


class MediaTests(unittest.TestCase):
    def test_scratch_bounds(self):
        for addr in ("0", "0xFF000", "0x100001", "0x1000000", "-4096"):
            with self.assertRaises(argparse.ArgumentTypeError):
                media.scratch_address(addr)
        self.assertEqual(media.scratch_address("0xFFF000"), 0xFFF000)
        with self.assertRaises(argparse.ArgumentTypeError):
            media.sd_directory("/test/../boot.py")

    def test_backup_rejection_and_restore(self):
        s = media.SECTOR
        data = bytes(range(256)) * (s // 256)
        record = dict(
            start=0xFFF000, jedec=0xEF7018, sha256=hashlib.sha256(data).hexdigest(), hex=data.hex()
        )
        self.assertEqual(media.backup_content(record, 0xFFF000, 0xEF7018), data)
        for addr, jedec, r in [
            (0xFFA000, 0xEF7018, record),
            (0xFFF000, 0xEF4018, record),
            (0xFFF000, 0xEF7018, dict(record, sha256="bad")),
        ]:
            with self.assertRaises(ValueError):
                media.backup_content(r, addr, jedec)
        target = Board()
        media.restore_sector(target, data)
        self.assertEqual(media.flash_read(target), data)

    def test_rom_contiguity(self):
        vol = dict(sectors_per_cluster=1, data_start=24, fat_start=3, clusters=70000)
        directory = bytearray(512)
        directory[:11] = b"_BOOT_P2BIX"
        struct.pack_into("<H", directory, 26, 5)
        struct.pack_into("<I", directory, 28, 700)
        fat = bytearray(512)
        struct.pack_into("<II", fat, 20, 6, 0x0FFFFFFF)
        sectors = {24: directory, 3: fat}
        self.assertEqual(sd_boot.locate(sectors.__getitem__, vol, 700), 27)
        struct.pack_into("<I", fat, 20, 10)
        with self.assertRaisesRegex(ValueError, "fragmented"):
            sd_boot.locate(sectors.__getitem__, vol, 700)
        directory[0] = 0
        with self.assertRaisesRegex(ValueError, "absent"):
            sd_boot.locate(sectors.__getitem__, vol, 700)


if __name__ == "__main__":
    unittest.main()
