#!/bin/sh
# Unix MicroPython semantic check. The temporary backing is a file, not a P2.
set -eu
port=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
vm=$(realpath "${1:?supply the Unix MicroPython executable}")
tmp=$(mktemp -d)
cd "$tmp"
trap 'cd /; rmdir "$tmp"' EXIT
export MICROPYPATH="$port/tests/drivers/host_backing:$port/modules"
"$vm" -X heapsize=96K "$port/tests/drivers/array_smoke.py"
"$vm" -X heapsize=96K "$port/examples/external_array.py"
