"""Run upstream language suites and relevant extmod tests, preserving each outcome."""
import argparse
import ast
import collections
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--port", required=True)
p.add_argument("--image", type=Path, required=True)
p.add_argument("--out", type=Path, required=True)
p.add_argument("--quick", action="store_true")
args = p.parse_args()
tests = Path(__file__).resolve().parents[3] / "tests"
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=True)
patterns = ["basics/*.py", "float/*.py", "extmod/json*.py", "extmod/asyncio_basic*.py",
            "extmod/vfs_fat*.py", "extmod/vfs_lfs2*.py", "micropython/heapalloc*.py"]
if args.quick:
    patterns = ["basics/int_divmod.py", "basics/try_finally*.py", "basics/generator*.py",
                "basics/bytes*.py", "basics/fun_*arg*.py", "basics/bignum*.py",
                "extmod/json*.py", "extmod/asyncio_basic*.py", "float/float_divmod.py"]
files = sorted({f.relative_to(tests).as_posix() for glob in patterns for f in tests.glob(glob)})
env = dict(os.environ, MICROPY_CPYTHON3=sys.executable, PYTHONUNBUFFERED="1")
cmd = [sys.executable, "run-tests.py", "-j1", "-t", "port:" + args.port,
       "-r", str(out), *files]
with (out / "upstream.log").open("w", encoding="utf8") as log:
    result = subprocess.run(cmd, cwd=tests, env=env, stdout=log, stderr=subprocess.STDOUT)
raw = json.loads((out / "_results.json").read_text())

def guarded_features(path):
    """List candidate guards, preserving source line numbers for multi-guard skips."""
    source = path.read_text(encoding="utf8")
    try:
        tree = ast.parse(source)
    except SyntaxError:  # MicroPython-specific syntax may be newer than host Python.
        return []
    guards = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            body = node.handlers
            feature = node.body[0]
        elif isinstance(node, ast.If):
            body = node.body
            feature = node.test
        else:
            continue
        if any(isinstance(v, ast.Constant) and v.value == "SKIP"
               for statement in body for v in ast.walk(statement)):
            guards.append({"line": feature.lineno, "source": source.splitlines()[feature.lineno - 1].strip()})
    return guards

outcomes = {}
counts = collections.Counter()
for name, status, detail in raw["results"]:
    counts[status] += 1
    entry = {"outcome": status}
    if detail:
        entry["detail"] = detail
    if status == "skip" and detail == "target test emitted SKIP":
        entry["source_guards"] = guarded_features(tests / name)
    outcomes[name] = entry
report = {"image_sha256": hashlib.sha256(args.image.read_bytes()).hexdigest(),
          "suite": patterns, "requested_files": len(files), "exitcode": result.returncode,
          "counts": counts, "target": raw["args"]["platform"], "outcomes": outcomes}
(out / "receipt.json").write_text(json.dumps(report, indent=2) + "\n")
print("\n".join((out/"upstream.log").read_text(errors="replace").splitlines()[-5:]))
sys.exit(result.returncode)
