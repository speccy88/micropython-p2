#!/usr/bin/env bash
# Invoke in a Linux checkout whose path has no spaces. Outputs stay under BUILD_ROOT.
set -euo pipefail
port=$(cd "$(dirname "$0")/.." && pwd)
repo=$(cd "$port/../.." && pwd)
P2_WORK=${P2_WORK:-"$HOME/tinygo-p2-work"}
export P2_WORK
sdk=${P2_BIN:-"$P2_WORK/llvm15-build/bin"}
buildroot=${BUILD_ROOT:-"$port/build-delivery"}
mkdir -p "$buildroot"
buildroot=$(cd "$buildroot" && pwd)
export SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-$(git -C "$repo" log -1 --format=%ct)}
export MICROPY_GIT_TAG=${MICROPY_GIT_TAG:-v1.29.0-p2.1}
export MICROPY_GIT_HASH=${MICROPY_GIT_HASH:-$(git -C "$repo" rev-parse --short=12 HEAD)}
jobs=${JOBS:-4}
test -x "$sdk/clang" || { echo "Set P2_WORK to the prepared P2 LLVM 15.0.7 SDK" >&2; exit 1; }
make -C "$repo/mpy-cross" -j"$jobs"
for profile in "${@:-edge}"; do
    case "$profile" in
        edge|threaded) board=P2_EC32MB ;;
        lean) board=P2_EDGE ;;
        *) echo "Unknown profile $profile" >&2; exit 1 ;;
    esac
    make -C "$port" -j"$jobs" PROFILE="$profile" BOARD="$board" BUILD="$buildroot/$profile"
    "$sdk/llvm-readelf" -SW "$buildroot/$profile/firmware.elf" >"$buildroot/$profile/sections.txt"
    sha256sum "$buildroot/$profile/firmware.bin"
done
