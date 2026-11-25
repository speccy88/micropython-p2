"""Build the downloadable kit from a committed checkout."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[3]
    args.output.mkdir(parents=True, exist_ok=True)
    archive = args.output / "micropython-p2-starter.zip"
    # git archive preserves licenses, binary contents, commit timestamps and
    # Unix executable permissions. The same relative paths work in a checkout.
    subprocess.run(["git", "-C", str(repo), "archive", "--format=zip",
                    "--prefix=micropython-p2/", "-o", str(archive.resolve()),
                    "HEAD", "README.md", "README-upstream.md", "LICENSE", "ports/p2"], check=True)
    with zipfile.ZipFile(archive) as kit:
        required = ["README.md", "ports/p2/tools/p2ram.py", "ports/p2/tools/flash_boot.py",
                    "ports/p2/tools/loadp2/flash_loader.bin", "ports/p2/firmware/edge.bin"]
        for path in required:
            kit.getinfo("micropython-p2/" + path)
        if kit.testzip():
            raise ValueError("ZIP integrity check failed")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (args.output / "SHA256SUMS.txt").write_bytes(f"{digest}  {archive.name}\n".encode("ascii"))


if __name__ == "__main__":
    main()
