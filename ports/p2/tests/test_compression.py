"""The first compressed error in a rebuilt C unit can come from a header."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class HeaderError(unittest.TestCase):
    def test_incremental_header_error(self):
        tool = Path(__file__).resolve().parents[3] / "py/makeqstrdefs.py"
        cpp = (
            '# 1 "service.c"\n# 1 "service.h" 1\n'
            'MP_COMPRESSED_ROM_TEXT("bad service")\n# 2 "service.c" 2\n'
            'MP_COMPRESSED_ROM_TEXT("invalid offset")\n'
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            pp = path / "qstr.i.last"
            subprocess.run(
                [
                    sys.executable,
                    tool,
                    "pp",
                    sys.executable,
                    "-c",
                    f"print({cpp!r})",
                    "output",
                    pp,
                    "sources",
                    "service.c",
                    "changed_sources",
                    "service.c",
                ],
                check=True,
            )
            subprocess.run([sys.executable, tool, "split", "compress", pp, path, "_"], check=True)
            self.assertEqual(
                (path / "service.c.compress").read_text().splitlines(),
                ["bad service", "invalid offset"],
            )
