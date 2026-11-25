"""Package native ELF, flat image, host mpy-cross and section budgets from one build."""
import argparse
import hashlib
import json
import os
import re
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
    return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT).strip()

def copy(src, name):
    path = args.output / name
    shutil.copy2(src, path)
    return {"file":name, "bytes":path.stat().st_size,
            "sha256":hashlib.sha256(path.read_bytes()).hexdigest()}

def symbols(elf):
    values = {}
    for line in run(readelf, "-sW", elf).splitlines():
        fields = line.split()
        if len(fields) == 8 and fields[0][:-1].isdigit() and fields[-1].startswith("_"):
            values[fields[-1]] = int(fields[1], 16)
    return values

def section_sizes(elf):
    pattern = r"^\s*\[\s*\d+\]\s+(\.\S+)\s+\S+\s+[\da-fA-F]+\s+[\da-fA-F]+\s+([\da-fA-F]+)\s+\S+\s+(\S+)"
    return {name: int(size, 16) for name, size, flags in
            re.findall(pattern, run(readelf, "-SW", elf), re.MULTILINE) if "A" in flags}

commit = run("git", "-C", str(args.repo), "rev-parse", "HEAD")
readelf = str(Path(os.environ["P2_BIN"]) / "llvm-readelf") if "P2_BIN" in os.environ else "readelf"
manifest = {"source_commit":commit, "upstream_release":"v1.29.0",
            "tinygo_p2_commit": "fc631f268080135e7c13ad27783ee6e1bb6a1c35",
            "compiler_patch_sha256":hashlib.sha256((args.repo / "ports/p2/toolchain/p2-codegen.patch").read_bytes()).hexdigest(),
            "profiles":{}}
for profile in ("edge", "lean", "threaded"):
    build = args.builds / profile
    elf = build / "firmware.elf"
    s = symbols(elf)
    parts = {"flat":copy(build / "firmware.bin", profile + ".bin"),
             "elf":copy(build / "firmware.elf", profile + ".elf")}
    parts["primary_stack_bytes"] = s["_stack_top"] - s["_stack_bottom"]
    parts["alloc_sections_bytes"] = section_sizes(elf)
    parts["heap_start"] = s["_heap_start"]
    parts["heap_end"] = s["_heap_end"]
    parts["gc_arena_bytes"] = s["_heap_end"] - s["_heap_start"]
    parts["lut_bytes_per_c_cog"] = s["__p2_lut_load_end"] - s["__p2_lut_load_start"]
    manifest["profiles"][profile] = parts
mpy = args.repo / "mpy-cross/build/mpy-cross"
manifest["mpy_cross_linux_x86_64"] = copy(mpy, "mpy-cross-linux-x86_64")
manifest["mpy_cross_version"] = run(str(mpy), "--version")
(args.output/"manifest.json").write_text(json.dumps(manifest,indent=2) + "\n")
print(json.dumps(manifest,indent=2))
