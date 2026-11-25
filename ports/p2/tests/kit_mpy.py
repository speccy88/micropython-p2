"""Compile with the Linux compiler from a verified starter ZIP and optionally run on Edge."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from make_starter import HOST_COMPILER, PREFIX, verify_zip

SOURCE = """def total(n):
    return sum(i*i - i for i in range(n))
"""


def run_on_edge(port, bytecode):
    from mpremote.transport_serial import SerialTransport

    board = SerialTransport(port)

    def execute(source):
        output, error = board.exec_raw(source, timeout=30)
        if error:
            raise RuntimeError(error.decode())
        return output.decode().strip()

    try:
        board.enter_raw_repl(soft_reset=True)
        execute(
            """import vfs, p2, sys
from p2memory import BlockDevice
r = p2.PSRAM().alloc(262144)
try:
    d = BlockDevice(r)
    vfs.VfsLfs2.mkfs(d)
    vfs.mount(vfs.VfsLfs2(d), '/kitprobe')
except:
    r.close()
    raise"""
        )
        try:
            board.fs_writefile("/kitprobe/kit_probe.mpy", bytecode, chunk_size=512)
            result = execute(
                "sys.path.insert(0,'/kitprobe')\n"
                "try:\n import kit_probe\n print(kit_probe.__file__, kit_probe.total(19))\n"
                "finally:\n sys.path.remove('/kitprobe')\n sys.modules.pop('kit_probe',None)"
            )
        finally:
            execute("vfs.umount('/kitprobe'); r.close()")
    finally:
        board.close()
    if result != "/kitprobe/kit_probe.mpy 1938":
        raise ValueError(f"Unexpected on-device import or result: {result}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kit", type=Path)
    parser.add_argument("--wsl", action="store_true", help="Run the x86-64 Linux compiler in WSL")
    parser.add_argument("--port", help="Edge running matching firmware (RAM relay or serial)")
    parser.add_argument("--output", type=Path, help="Save JSON acceptance record")
    args = parser.parse_args()
    manifest = verify_zip(args.kit)
    with TemporaryDirectory() as workspace:
        tmp = Path(workspace)
        with zipfile.ZipFile(args.kit) as z:
            compiler = tmp / "mpy-cross"
            compiler.write_bytes(z.read(PREFIX + HOST_COMPILER))
        compiler.chmod(0o755)
        (tmp / "kit_probe.py").write_text(SOURCE, encoding="utf-8")
        target_dir = str(tmp)
        if args.wsl:
            target_dir = subprocess.check_output(
                ["wsl", "-e", "wslpath", "-a", target_dir], text=True
            ).strip()
        cmd = (["wsl", "-e"] if args.wsl else []) + [target_dir + "/mpy-cross"]
        version = subprocess.check_output(cmd + ["--version"], text=True).strip()
        if version != manifest["mpy_cross_version"]:
            raise ValueError(f"Unexpected compiler version: {version}")
        subprocess.run(cmd + ["-s", "kit_probe.py", target_dir + "/kit_probe.py"], check=True)
        bytecode = (tmp / "kit_probe.mpy").read_bytes()
    if bytecode[:2] != b"M\x06":
        raise ValueError("Compiled output lacks a .mpy v6 header")
    record = {
        "archive_sha256": hashlib.sha256(args.kit.read_bytes()).hexdigest(),
        "edge_image_sha256": manifest["profiles"]["edge"]["flat"]["sha256"],
        "mpy_cross_sha256": manifest["mpy_cross_linux_x86_64"]["sha256"],
        "mpy_cross_version": version,
        "module_sha256": hashlib.sha256(bytecode).hexdigest(),
        "device_result": run_on_edge(args.port, bytecode) if args.port else None,
    }
    result = json.dumps(record, indent=2)
    print(result)
    if args.output:
        args.output.write_text(result + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
