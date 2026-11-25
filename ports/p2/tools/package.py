"""Package native ELF, flat image, host mpy-cross and section budgets from one build."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("builds", type=Path)
p.add_argument("--repo", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
args = p.parse_args()
args.output.mkdir(parents=True, exist_ok=True)

def run(*cmd):
    return subprocess.check_output(cmd, text=True).strip()

def copy(src, name):
    path = args.output / name
    shutil.copy2(src, path)
    return {"file":name, "bytes":path.stat().st_size,
            "sha256":hashlib.sha256(path.read_bytes()).hexdigest()}

def symbols(path):
    values = {}
    for line in path.read_text().splitlines():
        fields = line.split()
        if len(fields) >= 6 and fields[5] == "=" and fields[4].startswith("_"):
            values[fields[4]] = int(fields[0], 16)
    return values

commit = run("git", "-C", str(args.repo), "rev-parse", "HEAD")
manifest = {"source_commit":commit, "upstream_release":"v1.29.0", "profiles":{}}
for profile in ("edge", "lean", "threaded"):
    build = args.builds / profile
    s = symbols(build / "firmware.elf.map")
    parts = {"flat":copy(build / "firmware.bin", profile + ".bin"),
             "elf":copy(build / "firmware.elf", profile + ".elf")}
    parts["primary_stack_bytes"] = s["_stack_top"] - s["_stack_bottom"]
    parts["heap_start"] = s["_heap_start"]
    parts["heap_end"] = s["_stack_bottom"]
    parts["gc_arena_bytes"] = s["_stack_bottom"] - s["_heap_start"]
    parts["lut_bytes_per_c_cog"] = s["__p2_lut_load_end"] - s["__p2_lut_load_start"]
    manifest["profiles"][profile] = parts
mpy = args.repo / "mpy-cross/build/mpy-cross"
manifest["mpy_cross_linux_x86_64"] = copy(mpy, "mpy-cross-linux-x86_64")
manifest["mpy_cross_version"] = run(str(mpy), "--version")
(args.output/"manifest.json").write_text(json.dumps(manifest,indent=2) + "\n")
print(json.dumps(manifest,indent=2))
