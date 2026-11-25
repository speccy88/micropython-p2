"""Build a larger-than-hub bytecode program and verify its execution on the P2.

The work directory and the /p2test mount must be private to this run.
mpy-cross may be a host executable or called via --wsl in a Windows session.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--port", required=True)
parser.add_argument("--mpy-cross", required=True)
parser.add_argument("--wsl", action="store_true")
parser.add_argument("--groups", type=int, default=36)
parser.add_argument("--ops", type=int, default=640)
parser.add_argument("--output", required=True, type=Path)
args = parser.parse_args()
from mpremote.transport_serial import SerialTransport

def board_exec(board, source):
    result, error = board.exec_raw(source, timeout=120)
    if error:
        raise RuntimeError(error.decode())
    return result.decode().strip()

seed = 74139
rng = random.Random(seed)
expected = 1825
names = []
total = 0
digest = hashlib.sha256()
port_dir = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    for n in range(args.groups):
        name = f"p2stage{n:02d}"
        names.append(name)
        source = ["def run(x):"]
        for i in range(args.ops):
            k = rng.randrange(11, 32767)
            if i % 2 == 0:
                source.append(f" x=(x+{k})&65535")
                expected = (expected + k) & 65535
            else:
                source.append(f" x=x^{k}")
                expected ^= k
        source.append(" return x")
        file = root / (name + ".py")
        file.write_text("\n".join(source) + "\n")
    if args.wsl:
        subprocess.run(["wsl", "-e", "sh", "-ec",
                        'for f in p2stage*.py; do "$1" "$f"; done',
                        "p2-overlay", args.mpy_cross], cwd=root, check=True)
    else:
        for name in names:
            subprocess.run([args.mpy_cross, name + ".py"], cwd=root, check=True)
    for name in names:
        data = (root / (name + ".mpy")).read_bytes()
        total += len(data)
        digest.update(data)

    board = SerialTransport(args.port)
    try:
        board.enter_raw_repl(soft_reset=True)
        # All subsequent filesystem operations use this freshly allocated external region.
        board_exec(board, """import gc,vfs,sys,os,p2,p2memory
r=p2.PSRAM().alloc(2*1024*1024)
dev=p2memory.BlockDevice(r)
vfs.VfsLfs2.mkfs(dev)
vfs.mount(vfs.VfsLfs2(dev),'/p2test')
os.mkdir('/p2test/lib')
sys.path.insert(0,'/p2test/lib')
gc.collect()""")
        heap = int(board_exec(board, "print(gc.mem_free())"))
        if total <= heap:
            raise RuntimeError(f"program {total} must exceed free heap {heap}")
        start = time.monotonic()
        board.fs_writefile("/p2test/lib/p2overlay.py", (port_dir / "modules" / "p2overlay.py").read_bytes())
        for name in names:
            board.fs_writefile("/p2test/" + name + ".mpy", (root / (name + ".mpy")).read_bytes(), chunk_size=1024)
        upload_seconds = time.monotonic() - start
        code = "import p2overlay,time\np=p2overlay.Program('/p2test'," + repr(names) + ")\nt=time.ticks_ms()\nv=p.run(1825)\nprint(v,time.ticks_diff(time.ticks_ms(),t),gc.mem_free())"
        actual, runtime_ms, free_after = map(int, board_exec(board, code).split())
        result = dict(seed=seed, modules=len(names), operations=len(names)*args.ops,
                      mpy_bytes=total, mpy_sha256=digest.hexdigest(), initial_free_heap=heap,
                      upload_seconds=upload_seconds, run_ms=runtime_ms, free_after=free_after,
                      actual=actual, expected=expected, passed=actual==expected)
        print(json.dumps(result), flush=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
        if actual != expected:
            raise RuntimeError("independent output mismatch")
    finally:
        board.close()
