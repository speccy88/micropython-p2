# Which device does this Edge try first?

On November 25, 2026, the P2-EC32MB on COM12 returned `P59 P61 P60: 01-` on two independent RAM loads. P59 stayed low after release. P61 rose, selecting the ROM's SPI flash branch before it would check P60 for SD. The dash marks the untested pin. If the ROM rejects the flash header, it can still check P60 and try SD. The port reserves the first MiB of flash, including the header, so the probe leaves that later decision open. [ROM boot code](https://github.com/parallaxinc/propeller/blob/master/resources/FPGA%20Examples/ROM_Booter_v33k.spin2)

The RAM probe runs before the 160 MHz PLL starts. At RCFAST it uses the ROM's drive-low, wait 30, float, wait 150, and sample sequence. It stops on the first high input. This samples the electrical state after a serial ROM load. It cannot observe an earlier power-on transient or prove that an image ran. Both transfers received the ROM checksum acknowledgement from `Prop_Ver G`. The loaded image was 3,448 bytes, and its ELF had SHA-256 `40dd01fb77f1f8003ffa5b592f82589c4a450297875f9c6c4a1f45502d2f487c`. The final ROM monitor command `R_BOOT_P2.BIX` started the existing SD image, which reported a mounted card and 33,554,432 bytes of PSRAM. [Boot and recovery procedure](../storage/ACCEPTANCE.md)

To repeat the measurement, run this in Bash from `ports/p2` with the prepared P2 SDK. Use the Python interpreter that can access the physical serial port for the final command.

```sh
sdk=${P2_WORK:-"$HOME/tinygo-p2-work"}
bin=${P2_BIN:-"$sdk/llvm15-build/bin"}
out=build-boot-straps
mkdir -p "$out"
for src in boot.S startup.c tests/boot_straps.c; do
    "$bin/clang" --target=p2 -Os -ffreestanding -fno-builtin \
        -ffunction-sections -fdata-sections -c "$src" -o "$out/$(basename "$src").o"
done
"$bin/ld.lld" --wrap=p2_primary_entry --gc-sections -T p2.ld -o "$out/straps.elf" \
    "$out"/{boot.S,startup.c,boot_straps.c}.o "$sdk/p2-builtins/lib/builtins/libcompiler_builtins.a"
python tools/p2ram.py --port COM12 "$out/straps.elf" --monitor 2
```

A high P59 selects serial, a high P61 selects the SPI flash check, and `001` selects SD directly. If all three are low, the ROM proceeds to its P59 pull-down check. For an independent SD cold-boot observation, set the module's switches as described in the boot procedure before applying power.
