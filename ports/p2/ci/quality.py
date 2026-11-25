"""Run the project's pinned style tools on the maintained port and fork changes."""

import argparse
import filecmp
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

UPSTREAM = "0fd6c573ea815774668bbb16b8e197c8822368b2"  # MicroPython v1.29.0
ROOT = Path(__file__).resolve().parents[3]


def git_paths(command, *args):
    data = subprocess.check_output(["git", command, "-z", *args], cwd=ROOT)
    return [Path(p.decode()) for p in data.split(b"\0") if p]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix", action="store_true", help="Apply C and Python formatting")
    args = parser.parse_args()
    shared = ("py", "extmod", "shared", "lib", "tools", "tests", "mpy-cross")
    changes = git_paths(
        "diff", "--name-only", "--diff-filter=ACMR", UPSTREAM, "HEAD", "--", *shared
    )
    maintained = set(git_paths("ls-files", "--", "ports/p2", ".github/workflows"))
    maintained.update(changes)
    maintained.add(Path("README.md"))
    paths = sorted(
        p.as_posix()
        for p in maintained
        if (ROOT / p).is_file()
        and not {"loadp2", "notices", "firmware"} & set(p.parts)
        and p.suffix in {".py", ".c", ".h", ".md", ".sh", ".yml", ".mjs", ".html", ".css"}
    )

    def run(cmd):
        subprocess.run(cmd, cwd=ROOT, check=True)

    py = [p for p in paths if p.endswith(".py")]
    c = [p for p in paths if p.endswith((".c", ".h"))]
    if not c or not py:
        sys.exit("Maintained source file inventory is empty")
    run(["ruff", "check", "--force-exclude", *py])
    run(["ruff", "format", "--force-exclude", *([] if args.fix else ["--check"]), *py])
    formatter = [sys.executable, str(ROOT / "tools/codeformat.py"), "-c"]
    if args.fix:
        run([*formatter, *c])
    else:
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            for path in c:
                (work / path).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / path, work / path)
            subprocess.run([*formatter, *c], cwd=work, check=True)
            changed = [
                path for path in c if not filecmp.cmp(ROOT / path, work / path, shallow=False)
            ]
            if changed:
                sys.exit("C files need formatting (run quality.py --fix):\n" + "\n".join(changed))
    run(["codespell", *paths])


if __name__ == "__main__":
    main()
