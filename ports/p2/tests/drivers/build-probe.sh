#!/bin/sh
# Run under WSL from any directory. Does not open a serial port.
set -eu
cd "$(dirname "$0")/../.."
out=${1:-build-probe}
bin=${P2_BIN:-"$HOME/tinygo-p2-work/llvm15-build/bin"}
builtins=${P2_BUILTINS:-"$HOME/tinygo-p2-work/p2-builtins/lib/builtins/libcompiler_builtins.a"}
mkdir -p "$out"
for src in startup.c boot.S drivers/psram_bus.c drivers/psram_word.S drivers/counter.S tests/drivers/probe.c; do
    "$bin/clang" --target=p2 -Os -ffreestanding -fno-builtin -ffunction-sections -fdata-sections -c "$src" -o "$out/$(basename "$src").o"
done
"$bin/ld.lld" --gc-sections -T p2.ld -o "$out/drivers.elf" "$out/startup.c.o" "$out/boot.S.o" "$out/psram_bus.c.o" "$out/psram_word.S.o" "$out/counter.S.o" "$out/probe.c.o" "$builtins"
"$bin/llvm-objcopy" -O binary "$out/drivers.elf" "$out/drivers.bin"
