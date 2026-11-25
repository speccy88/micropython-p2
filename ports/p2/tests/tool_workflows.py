"""Use stock mpremote commands with a fresh PSRAM volume and verify files."""

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--port", required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--image", type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
log = {"image_sha256": hashlib.sha256(args.image.read_bytes()).hexdigest(), "commands": []}


def run(*commands):
    cmd = [sys.executable, "-m", "mpremote", "connect", args.port, *commands]
    result = subprocess.run(cmd, text=True, capture_output=True, timeout=150)
    log["commands"].append(
        {
            "args": commands,
            "returncode": result.returncode,
            "output": result.stdout.strip(),
            "error": result.stderr.strip(),
        }
    )
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    return result.stdout.strip()


try:
    run(
        "exec",
        "import gc,os,vfs,p2;from p2memory import BlockDevice;"
        "r=p2.PSRAM().alloc(1048576);d=BlockDevice(r);vfs.VfsLfs2.mkfs(d);"
        "vfs.mount(vfs.VfsLfs2(d),'/p2tools');os.mkdir('/p2tools/lib')",
    )
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "probe.dat"
        copy = Path(tmp) / "roundtrip.dat"
        data = hashlib.shake_256(b"p2-mpremote-fs").digest(4103)
        src.write_bytes(data)
        run("resume", "fs", "cp", str(src), ":/p2tools/probe.dat")
        run("resume", "fs", "cp", ":/p2tools/probe.dat", str(copy))
        if data != copy.read_bytes():
            raise ValueError("filesystem copy mismatch")
        log["roundtrip_sha256"] = hashlib.sha256(data).hexdigest()
    package = root / "packages" / "p2array" / "package.json"
    run("resume", "mip", "install", "--target", "/p2tools/lib", package.as_posix())
    expected = (root / "modules/p2array.py").read_bytes()
    with tempfile.TemporaryDirectory() as tmp:
        result = Path(tmp) / "p2array.py"
        run("resume", "fs", "cp", ":/p2tools/lib/p2array.py", str(result))
        # mpremote copies manifests as binary, including the source line endings.
        if result.read_bytes() != expected:
            raise ValueError("installed package content mismatch")
    out = run(
        "resume",
        "exec",
        "import sys;sys.path.insert(0,'/p2tools/lib');"
        "import p2array;print(p2array.__file__);"
        "a=p2array.Array('I',40000);a[-1]=123456;print(a[-1]);a.close()",
    )
    if "/p2tools/lib/p2array.py" not in out or "123456" not in out:
        raise ValueError("package origin or external array result mismatch")
    log["passed"] = True
except Exception as exc:
    log.update(passed=False, reason=repr(exc))
finally:
    args.output.write_text(json.dumps(log, indent=2) + "\n")
print(log.get("reason", "mpremote copy and mip install passed"))
sys.exit(0 if log["passed"] else 1)
