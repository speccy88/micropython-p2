"""Regression tests for the Git-to-starter binary boundary. Run from a checkout."""

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "ports/p2/tools"))
import make_starter as kit


class StarterTests(unittest.TestCase):
    def test_binary_attributes(self):
        files = sorted(
            p.relative_to(ROOT).as_posix()
            for p in (ROOT / "ports/p2").glob("firmware/*")
            if p.suffix != ".json"
        )
        files += ["ports/p2/examples/hubdriver/checksum.p2d", kit.LOADER]
        attrs = subprocess.check_output(
            ["git", "-C", str(ROOT), "check-attr", "--cached", "text", "--", *files], text=True
        )
        self.assertEqual(attrs.splitlines(), [f"{p}: text: unset" for p in files])

    def test_normalized_elf(self):
        def read(path):
            data = (ROOT / path).read_bytes()
            return data.replace(b"\r\n", b"\n") if path.endswith("edge.elf") else data

        # Simulate the original kit's one-way CRLF conversion.
        with self.assertRaisesRegex(ValueError, r"edge\.elf: expected"):
            kit.check_artifacts(read)

    def test_modified_compiler_same_size(self):
        def read(path):
            data = (ROOT / path).read_bytes()
            return data[:-1] + bytes([data[-1] ^ 1]) if path == kit.HOST_COMPILER else data

        with self.assertRaisesRegex(ValueError, r"mpy-cross-linux-x86_64: expected"):
            kit.check_artifacts(read)

    def test_missing_profile(self):
        def read(path):
            manifest = json.loads((ROOT / path).read_bytes())
            del manifest["profiles"]["lean"]
            return json.dumps(manifest).encode()

        with self.assertRaisesRegex(ValueError, "Missing firmware profiles: lean"):
            kit.check_artifacts(read)

    def test_archive_executable_mode(self):
        with TemporaryDirectory() as tmp:
            archive = Path(tmp) / "fixture.zip"
            files = list(kit.REQUIRED) + [
                kit.LOADER,
                "ports/p2/toolchain/p2-codegen.patch",
            ]
            files += [p.relative_to(ROOT).as_posix() for p in (ROOT / kit.FIRMWARE).iterdir()]
            with zipfile.ZipFile(archive, "w") as out:
                for path in files:
                    out.writestr(kit.PREFIX + path, (ROOT / path).read_bytes())
            with self.assertRaisesRegex(ValueError, "missing Unix executable mode"):
                kit.verify_zip(archive)


if __name__ == "__main__":
    unittest.main()
