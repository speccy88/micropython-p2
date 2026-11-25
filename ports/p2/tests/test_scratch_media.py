"""Host tests for scratch selection, NOR backup/restore and ROM FAT layout checks."""

import argparse
from contextlib import ExitStack, redirect_stdout
import hashlib
import io
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

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
    def test_sector_read_retries_only_the_serial_frame(self):
        class Card:
            reads = 0

            def readblocks(self, index, buf):
                self.reads += 1
                buf[:] = bytes(range(256)) * (len(buf) // 256)
                return 0

        class TruncatingBoard(Board):
            def __init__(self, truncations):
                self.globals = {"sd": Card()}
                self.truncations = truncations
                self.resyncs = 0

            def exec_raw_no_follow(self, code):
                out = io.BytesIO()
                with redirect_stdout(io.TextIOWrapper(out)) as stdout:
                    exec(code, self.globals)
                    stdout.flush()
                frame = out.getvalue() + b"\x04\x04"
                if self.truncations:
                    self.truncations -= 1
                    frame = frame[:-4]
                self.serial = io.BytesIO(frame)

            def enter_raw_repl(self, soft_reset):
                assert not soft_reset
                self.resyncs += 1

        target = TruncatingBoard(1)
        self.assertEqual(sd_boot.read_sectors(target, 900, 8), bytes(range(256)) * 16)
        self.assertEqual(target.globals["sd"].reads, 1)
        self.assertEqual(target.resyncs, 1)
        target = TruncatingBoard(3)
        with self.assertRaisesRegex(ValueError, "LBA 900.*received"):
            sd_boot.read_sectors(target, 900)
        self.assertEqual(target.globals["sd"].reads, 1)
        self.assertEqual(target.resyncs, 2)

    def test_scratch_bounds(self):
        for addr in ("0", "0xFF000", "0x100001", "0x1000000", "-4096"):
            with self.assertRaises(argparse.ArgumentTypeError):
                media.scratch_address(addr)
        self.assertEqual(media.scratch_address("0xFFF000"), 0xFFF000)
        with self.assertRaises(argparse.ArgumentTypeError):
            media.sd_directory("/test/../boot.py")

    def test_install_only_publishes_verified_bytes(self):
        class FileBoard(Board):
            fs_stat = staticmethod(os.stat)

            def enter_raw_repl(self, soft_reset):
                if "staged" in self.globals:
                    self.globals["staged"].close()

        image = bytes(range(256)) * 2 + b"tail"
        board = FileBoard()
        sd = SimpleNamespace(ioctl=lambda op, arg: {3: 0, 4: 8192, 5: 512}[op])
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            boot = Path(folder) / "_BOOT_P2.BIX"
            stage = Path(folder) / "_P2BOOT.TMP"
            stack.enter_context(patch.object(sd_boot, "BOOTFILE", str(boot)))
            stack.enter_context(patch.object(sd_boot, "STAGING_FILE", str(stage)))
            stack.enter_context(
                patch.dict(sys.modules, {"p2sd": SimpleNamespace(active=lambda: sd)})
            )
            stack.enter_context(patch.object(sd_boot, "geometry", return_value={}))
            stack.enter_context(patch.object(sd_boot, "locate", return_value=400))
            read = stack.enter_context(patch.object(sd_boot, "read_sectors"))
            report = {"sha256": hashlib.sha256(image).hexdigest()}

            stage.write_bytes(b"previous upload")
            with self.assertRaises(FileExistsError):
                sd_boot.verify_boot_file(board, image, True, report)
            self.assertEqual(stage.read_bytes(), b"previous upload")
            stage.unlink()

            def raw_bytes(_board, first, count):
                self.assertEqual((first, count), (400, 2))
                self.assertFalse(boot.exists())
                return stage.read_bytes().ljust(count * 512, b"\xff")

            read.return_value = bytes(1024)
            with self.assertRaisesRegex(ValueError, "sectors differ"):
                sd_boot.verify_boot_file(board, image, True, report)
            self.assertFalse(boot.exists() or stage.exists())
            read.side_effect = raw_bytes
            sd_boot.verify_boot_file(board, image, True, report)
            self.assertEqual(boot.read_bytes(), image)
            self.assertFalse(stage.exists())
            self.assertTrue(report["created"])

            read.side_effect = None
            read.return_value = bytes(1024)
            with self.assertRaisesRegex(ValueError, "sectors differ"):
                sd_boot.verify_boot_file(board, image, True, report)
            self.assertEqual(boot.read_bytes(), image)

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
