"""Build a verified starter ZIP from Git, or verify an existing kit."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import zipfile

PREFIX = "micropython-p2/"
FIRMWARE = "ports/p2/firmware/"
HOST_COMPILER = FIRMWARE + "mpy-cross-linux-x86_64"
ARCHIVE = "micropython-p2-starter.zip"
REQUIRED = (
    "README.md",
    "README-upstream.md",
    "LICENSE",
    "ports/p2/README.md",
    "ports/p2/tools/load_ram.py",
    "ports/p2/tools/p2ram.py",
    "ports/p2/tools/ram_session.py",
    "ports/p2/storage/ACCEPTANCE.md",
    "ports/p2/tests/fat_directory.py",
    "ports/p2/tests/sd_boot.py",
    "ports/p2/tests/observe_boot.py",
    "ports/p2/tools/flash_boot.py",
    "ports/p2/tools/loadp2/LICENSE",
    "ports/p2/tools/loadp2/flash_loader.spin2",
)
LOADER = "ports/p2/tools/loadp2/flash_loader.bin"
LOADER_SHA256 = "ca938b18576dc94f3b26911aab8c527d9f8fb787d928380223263abd7085f436"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def check_artifacts(read):
    """Use the same file and manifest checks on disk and on the ZIP members."""
    manifest = json.loads(read(FIRMWARE + "manifest.json"))
    profiles = manifest["profiles"]
    missing = {"edge", "lean", "threaded"} - profiles.keys()
    if missing:
        raise ValueError("Missing firmware profiles: " + ", ".join(sorted(missing)))
    records = {}
    for name, profile in profiles.items():
        if not name.isidentifier():
            raise ValueError(f"Invalid firmware profile name: {name!r}")
        records[name + ".bin"] = profile["flat"]
        records[name + ".elf"] = profile["elf"]
    records["mpy-cross-linux-x86_64"] = manifest["mpy_cross_linux_x86_64"]
    for name, record in records.items():
        if record["file"] != name:
            raise ValueError(f"Expected {name} in the manifest, found {record['file']!r}")
        data = read(FIRMWARE + name)
        actual = sha256(data)
        if len(data) != record["bytes"] or actual != record["sha256"]:
            raise ValueError(
                f"{name}: expected {record['bytes']} bytes, SHA-256 {record['sha256']}; "
                f"found {len(data)} bytes, SHA-256 {actual}"
            )
    patch = "ports/p2/toolchain/p2-codegen.patch"
    if sha256(read(patch)) != manifest["compiler_patch_sha256"]:
        raise ValueError(f"{patch}: differs from release manifest")
    if sha256(read(LOADER)) != LOADER_SHA256:
        raise ValueError(f"{LOADER}: unexpected flash programmer")
    for path in REQUIRED:
        if not read(path):
            raise ValueError(f"{path}: empty required file")
    return manifest


def verify_zip(path):
    with zipfile.ZipFile(path) as kit:
        names = kit.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate entries in starter ZIP")
        bad = kit.testzip()
        if bad is not None:
            raise ValueError(f"{bad}: ZIP CRC mismatch")
        manifest = check_artifacts(lambda name: kit.read(PREFIX + name))
        info = kit.getinfo(PREFIX + HOST_COMPILER)
        if info.create_system != 3 or info.external_attr >> 16 != 0o100755:
            raise ValueError(f"{HOST_COMPILER}: missing Unix executable mode in ZIP")
        return manifest


def build(repo, output):
    git = ["git", "-C", str(repo)]
    # A file whose worktree is good but whose staged blob was normalized
    # passes the first check and fails the independent check inside the ZIP.
    local_manifest = check_artifacts(lambda name: (repo / name).read_bytes())
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output) as tmp:
        archive = Path(tmp).resolve() / ARCHIVE
        subprocess.run(
            [
                *git,
                "archive",
                "--format=zip",
                "--prefix=" + PREFIX,
                "-o",
                str(archive),
                "HEAD",
                "README.md",
                "README-upstream.md",
                "LICENSE",
                "ports/p2",
            ],
            check=True,
        )
        if verify_zip(archive) != local_manifest:
            raise ValueError("Committed release manifest differs from the checkout")
        sums = archive.with_name("SHA256SUMS.txt")
        sums.write_bytes(f"{sha256(archive.read_bytes())}  {ARCHIVE}\n".encode("ascii"))
        archive.replace(output / ARCHIVE)
        sums.replace(output / sums.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("output", type=Path, nargs="?", help="Directory for the ZIP and SHA256SUMS")
    group.add_argument("--verify", type=Path, metavar="ZIP", help="Check a downloaded kit")
    group.add_argument(
        "--check-files", action="store_true", help="Verify this extracted checkout or kit"
    )
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[3]
    try:
        if args.verify:
            verify_zip(args.verify)
        elif args.check_files:
            check_artifacts(lambda name: (repo / name).read_bytes())
        else:
            build(repo, args.output)
    except (
        KeyError,
        OSError,
        ValueError,
        zipfile.BadZipFile,
        subprocess.CalledProcessError,
    ) as exc:
        parser.exit(1, f"Starter verification failed: {exc}\n")
    print("Starter kit integrity verified.")


if __name__ == "__main__":
    main()
