#!/usr/bin/env bash
# Build a private native LLVM toolchain from the pinned TinyGo/P2 sources.
set -euo pipefail
if [[ $# -ne 2 ]]; then
    echo "Usage: bash build-overlay.sh /path/to/tinygo-p2/modern /path/to/private-work" >&2
    exit 2
fi
here=$(cd "$(dirname "$0")" && pwd)
bundle=$(cd "$1" && pwd)
mkdir -p "$2"
out=$(cd "$2" && pwd)
base=8dfdcc7b7bf66834a761bd8de445840ef68e4d1a
baseline="$bundle/patches/llvm15-p2.patch"
expected=ef20925ea64d7e9633e2457c6d47658808491ec47e9a0bddbafd44bec5a09e51
actual=$(sha256sum "$baseline" | cut -d' ' -f1)
[[ "$actual" == "$expected" ]] || { echo "TinyGo/P2 LLVM baseline digest differs" >&2; exit 1; }
digest=$(sha256sum "$here/p2-codegen.patch" | cut -d' ' -f1)
src="$out/src"
if [[ ! -e "$src" ]]; then
    # A local clone shares the baseline Git objects and owns its worktree.
    git clone --local --no-checkout "${P2_WORK:-$HOME/tinygo-p2-work}/p2llvm/llvm15" "$src"
    git -C "$src" checkout --detach "$base"
    git -C "$src" apply --whitespace=nowarn "$baseline"
    git -C "$src" apply "$here/p2-codegen.patch"
    printf '%s\n' "$digest" > "$out/p2-patch.sha256"
elif [[ ! -f "$out/p2-patch.sha256" || $(cat "$out/p2-patch.sha256") != "$digest" ]]; then
    echo "Choose a fresh private work directory for this patch revision" >&2
    exit 1
fi
git -C "$src" apply --reverse --check "$here/p2-codegen.patch"
cmake -S "$src/llvm" -B "$out/build" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
    -DCMAKE_C_FLAGS_RELEASE=-O1 -DCMAKE_CXX_FLAGS_RELEASE=-O1 \
    -DLLVM_ENABLE_PROJECTS='clang;lld' -DLLVM_TARGETS_TO_BUILD=X86 \
    -DLLVM_EXPERIMENTAL_TARGETS_TO_BUILD=P2 -DLLVM_ENABLE_ASSERTIONS=ON \
    -DLLVM_ENABLE_BINDINGS=OFF -DCLANG_ENABLE_ARCMT=OFF -DCLANG_ENABLE_STATIC_ANALYZER=OFF \
    -DCLANG_LINK_CLANG_DYLIB=OFF -DLLVM_BUILD_LLVM_DYLIB=ON -DLLVM_LINK_LLVM_DYLIB=ON \
    -DLLVM_ENABLE_TERMINFO=OFF -DLLVM_ENABLE_ZLIB=ON -DLLVM_ENABLE_ZSTD=OFF \
    -DLLVM_ENABLE_LIBXML2=OFF -DLLVM_USE_LINKER=lld -DLLVM_PARALLEL_LINK_JOBS=1
cmake --build "$out/build" -j "${JOBS:-3}" --target clang lld llc opt LLVM \
    llvm-mc llvm-objdump llvm-objcopy llvm-readelf llvm-nm llvm-ar llvm-ranlib \
    llvm-as llvm-dis llvm-config FileCheck not count split-file
python3 "$here/check-overlay.py" "$out/build/bin"
echo "Use P2_BIN=$out/build/bin for the MicroPython profile builds"
