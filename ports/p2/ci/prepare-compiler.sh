#!/usr/bin/env bash
# Build in a private Linux runner directory. Cache just the executable SDK.
set -euo pipefail
bundle=$(realpath "${1:?path to the pinned tinygo-p2 modern directory}")
dest=$(realpath -m "${2:?empty SDK destination}")
test ! -e "$dest"
mkdir -p "$dest"/{bin,lib}
port=$(cd "$(dirname "$0")/.." && pwd)
scratch=$(mktemp -d "$(dirname "$dest")/p2-build.XXXXXXXX")
export P2_WORK="$scratch"

# Use the SDK's own source lock and patch preparation, without building Go or
# populating sources unused by this C port.
python3 - "$bundle" "$scratch" <<'PY'
import importlib.util
from pathlib import Path
import sys

bundle, work = map(Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location("p2_sources", bundle / "prepare-sources.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.checkout("p2llvm", work / "p2llvm")
module.patch(work / "p2llvm", "p2llvm-tools.patch")
module.checkout("llvm", work / "p2llvm/llvm15")
PY

bash "$port/toolchain/build-overlay.sh" "$bundle" "$scratch/overlay"
build="$scratch/overlay/build"
cmake --build "$build" --target clang-resource-headers
for tool in clang ld.lld llvm-{mc,objcopy,objdump,readelf,nm,ar,ranlib}; do
    cp -L "$build/bin/$tool" "$dest/bin/$tool"
done
ln -s clang "$dest/bin/clang++"
cp -a "$build/lib"/libLLVM*.so* "$dest/lib/"
resources=$("$build/bin/clang" -print-resource-dir)
mkdir -p "$dest/lib/clang"
cp -a "$resources" "$dest/lib/clang/"
mkdir -p "$dest/p2llvm"
cp -a "$scratch/p2llvm/"{libc,libp2} "$dest/p2llvm/"
python3 "$port/toolchain/check-overlay.py" "$dest/bin"
