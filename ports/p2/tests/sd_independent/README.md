# Independent SD sector diagnostic

This RAM-only program links the pinned P2LLVM SDK's `libc/drivers/sdmmc.c` directly. It uses that driver's P2 Smart Pin clock, TX, RX, initialization and block-receive paths. The normal MicroPython firmware uses a separate bit-banged SPI driver. The diagnostic shares only the native bootstrap, serial console and C support with the firmware.

The SDK default inputs match the Edge wiring, with P61 clock, P60 chip select, P59 MOSI and P58 MISO. The compatibility header supplies the bootstrap's actual 160 MHz clock for SDK timeouts. After card initialization the diagnostic issues only single-sector reads (CMD17). The linker discards the SDK's data-block write function.

From `ports/p2`, build with a fresh output directory.

```sh
make -f tests/sd_independent/Makefile BUILD=build-sd-independent P2_LLVM_BIN="$P2_BIN"
```

The Windows host command below downloads into hub RAM and writes a JSON report. Pass `--compare previous.json` to compare the SHA-256 hashes against the host-side FAT diagnostic's `sector_sha256` entries.

```sh
python tests/sd_independent/run.py build-sd-independent/diagnostic.bin --port COM12 --loader-dir /path/to/tinygo-p2/modern/hil --output validation/sd-independent.json
```

LBAs 0, 2048, 31916, 31917 and 31918 are read twice, with four other sector reads between consecutive reads of the same LBA. The program compares all 512 bytes, computes SHA-256 on the P2, and reports the number of active short aliases and the number of distinct 11-byte aliases using byte comparisons. Filenames and sector contents stay in P2 RAM. Those three directory LBAs are specific to the volume being investigated. `root_terminator_seen` distinguishes a complete root from an observed prefix.

Each 16-character slot map uses `E` for the FAT end marker, `-` for slots beyond the first end marker, `D` for deleted, `L` for long-name, `V` for volume label, `P` for dot entry and `S` for an active short entry.
