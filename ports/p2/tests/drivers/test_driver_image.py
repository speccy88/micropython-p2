"""Portable header checks; additionally assemble and check ELF when Clang/P2 is installed."""

import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

PORT = Path(__file__).resolve().parents[2]
EXAMPLE = PORT / "examples/hubdriver"
SPEC = importlib.util.spec_from_file_location("cog_image", PORT / "tools/cog_image.py")
image_tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(image_tool)


class DriverImage(unittest.TestCase):
    def test_image(self):
        self.assertEqual(image_tool.verify((EXAMPLE / "ws2812.p2d").read_bytes()), (216, 0, 38))
        self.assertEqual(image_tool.verify((EXAMPLE / "edgecount.p2d").read_bytes()), (124, 0, 7))
        image = (EXAMPLE / "checksum.p2d").read_bytes()
        self.assertEqual(image_tool.verify(image), (140, 0, 64))
        for offset in (0, 4, 5, 6, 8, 12, 16, 20, len(image) - 1):
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                altered = bytearray(image)
                altered[offset] ^= 1
                image_tool.verify(altered)
        for truncated in (image[:4], image[:24], image[:-1], image + b"\0"):
            with self.assertRaises(ValueError):
                image_tool.verify(truncated)

    def test_elf(self):
        binary = (
            Path(os.getenv("P2_BIN", Path.home() / "tinygo-p2-work/llvm15-build/bin")) / "clang"
        )
        if not binary.exists():
            self.skipTest("P2 Clang unavailable")
        source = (EXAMPLE / "checksum.S").read_text()
        with tempfile.TemporaryDirectory() as path:
            asm, obj = Path(path) / "test.S", Path(path) / "test.o"

            def assemble(contents):
                asm.write_text(contents)
                subprocess.run([binary, "--target=p2", "-c", asm, "-o", obj], check=True)
                return obj.read_bytes()

            valid = assemble(source)
            self.assertEqual(image_tool.pack(valid, 64), (EXAMPLE / "checksum.p2d").read_bytes())
            for name, words in (("ws2812", 38), ("edgecount", 7)):
                self.assertEqual(
                    image_tool.pack(assemble((EXAMPLE / (name + ".S")).read_text()), words),
                    (EXAMPLE / (name + ".p2d")).read_bytes(),
                )
            idle = Path(__file__).resolve().with_name("neverready.S")
            self.assertEqual(
                image_tool.pack(assemble(idle.read_text()), 4),
                idle.with_suffix(".p2d").read_bytes(),
            )
            for words in (0, 3, 257):
                with self.assertRaises(ValueError):
                    image_tool.pack(valid, words)
            for changed in (
                source + "\n.long p2_driver_entry\n",
                source + "\n.data\n.long 42\n",
                source.replace("p2_driver_entry", "other"),
                source + "\n.space 4096\n",
            ):
                with self.assertRaises(ValueError):
                    image_tool.pack(assemble(changed), 64)
