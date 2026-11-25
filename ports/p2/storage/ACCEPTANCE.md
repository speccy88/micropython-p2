# Physical storage and boot acceptance

Use the Edge profile, a stable supply and the on-module SD socket. Connect with
the RAM relay so command-line clients can release the serial session without
resetting the board. Close ViperIDE, Thonny and other clients. Run from the
repository root with standard mpremote installed; substitute the image you
actually loaded. Each result path must be new.

## Files, reset and startup on SD

Select an expendable FAT volume or a designated writable directory. The file
test creates an exclusive 8.3 temporary file in that directory, writes across
a sector, flushes, modifies it, recovers from an exception, and leaves a
second write open across a raw soft reset. It then unmounts/remounts FAT,
checks the entire result and removes the test file.

```sh
python ports/p2/tests/scratch_media.py --port socket://127.0.0.1:8122 --image ports/p2/firmware/edge.bin --sd-directory / --startup --output sd-startup.json
```

`--startup` also exercises the root startup files. It moves existing
`boot.py` and `main.py` aside under unique 8.3 backup names on the card,
prints those names and restores them when the test finishes. It records that
the friendly reset executed both temporary files in order and that raw reset
bypassed the scripts. On an interrupted run, RAM-load the Edge with serial
override, enter raw mode and soft-reset. Use the printed filenames to restore
the two originals. If either original was absent, remove only the
corresponding temporary test script. For a directory-only test omit
`--startup`. Keep backups off the card for valuable data.

## Erase and program one NOR sector

The physical fixture for this audit designates only `0xFFF000–0xFFFFFF` on
its 16 MiB Winbond. On another board first establish which exact aligned
sector is expendable. The runner opens a 4096-byte partition, and the driver
excludes the bottom 1 MiB. SD and flash share pins, so the runner unmounts
the card before accessing NOR and soft-resets afterward to restore automount.

```sh
python ports/p2/tests/scratch_media.py --port socket://127.0.0.1:8122 --image ports/p2/firmware/edge.bin --flash-sector 0xFFF000 --backup scratch-fff000.json --output flash-result.json
```

The first read uses a read-only handle. Before opening a writable handle, the
runner writes the complete original sector, address, JEDEC ID and SHA-256 to
a new local file, flushes it to disk and checks it again. The test erases
the sector, scans every byte, programs across 256-byte page boundaries and
compares all 4096 bytes. It restores the original contents even after a
failed comparison and reopens the partition read-only to verify restoration.

If serial communication or power is lost, keep the backup. Reconnect the
**same physical board**, RAM-load the matching Edge firmware, then run:

```sh
python ports/p2/tests/scratch_media.py --port socket://127.0.0.1:8122 --image ports/p2/firmware/edge.bin --flash-sector 0xFFF000 --restore scratch-fff000.json --output flash-recovery.json
```

The JEDEC ID identifies a device model. Two boards of the same model can
have the same ID, so label the backup with its board. Restoration checks the
address, ID, length and SHA-256 and compares the result after reopening.
The [host NOR/LittleFS model](FLASH.md) separately covers write protection
and BUSY timeouts. A successful data-sector test does not validate SPI boot.

## Boot the interpreter from SD

Use a FAT32 card with an MBR and a FAT32 first primary partition (type
`0x0B` or `0x0C`). The ROM scans the first cluster of the root directory,
matches the short filename `_BOOT_P2.BIX` and reads contiguous sectors.
Its file window is 496 KiB. The helper checks the required FAT geometry,
FSInfo, directory position, cluster chain and full image SHA-256 computed
from those physical sectors. It leaves the boot sectors and partition table
alone. [Parallax ROM SD boot source](https://github.com/parallaxinc/propeller/blob/master/resources/FPGA%20Examples/ROM_Booter_v33k.spin2)

```sh
python ports/p2/tests/sd_boot.py --port socket://127.0.0.1:8122 --image ports/p2/firmware/edge.bin --install --output sd-layout.json
```

The helper sends the physical sectors as length-delimited binary frames and
hashes them on the host. On COM12 it verified the 403,960-byte Edge image
in 50.03 seconds of read-back. A new install writes `_P2BOOT.TMP` first.
Only after the hash matches does it rename that file to `_BOOT_P2.BIX` and
check its final directory entry. If power was interrupted during upload,
inspect the staging file before removing it and retrying. An existing
staging file is preserved. [Raw sector and FAT-chain verification](../validation/sd-kit2-raw.json)

An existing boot file is read and compared. If you want to replace a
different image, back it up under another name before running the command.
Without `--install` the helper only inspects the card. If the card is
fragmented or has the wrong partition type, prepare a separate FAT32 SD card
and put the boot file on it first. The `passed` field in this report covers
the bytes the ROM will see. Actual execution has a separate acceptance step.

To run the card immediately with the board still set for serial boot, close
the relay and select **Can I boot my SD card? → Boot SD & open ViperIDE**
in the workbench. The CLI can make the same check on a physical serial port.
Substitute `/dev/ttyUSB0` or your macOS `/dev/cu.*` port for `COM12` as needed.
Both use the P2 ROM monitor's `R_BOOT_P2.BIX` command. On the test Edge,
the resulting REPL reported 32 MiB of PSRAM and a mounted SD card.
[Workbench](https://speccy88.github.io/micropython-p2/) · [Physical ROM monitor run](../validation/sd-kit2-rom-monitor.json)

```sh
python ports/p2/tests/observe_boot.py --port COM12 --rom-monitor --timeout 15 --output sd-monitor.json
```

### Automatic power-on boot

1. Close the relay and serial tools. Power off with the SD card inserted.
   On the P2-EC32MB, select SD boot with serial fallback. P61 FLASH pull-up
   and both P59 mode pulls are off; the card provides the P60 pull-up. Match
   switch names and board revision to the guide. [Edge module guide](https://www.parallax.com/package/p2-edge-module-with-32mb-ram-product-guide/)
2. Power on and connect at 115200 without loading an image. At the friendly
   prompt run `import sys,p2; print(sys.platform,p2.PSRAM().capacity())`.
   Expect `p2 33554432`. Record this as a cold boot only after an actual
   power cycle. A DTR pulse or reset button verifies warm ROM restart.
3. To recover, power off, remove the card and select P59 serial override.
   Reset, RAM-load the verified image and fix or remove the SD boot file.
   The SD procedure never launches the SPI boot-flash programmer.

For a repeatable observation, leave the USB adapter connected to the host,
close the RAM relay and use a physically independent target supply:

```sh
python ports/p2/tests/observe_boot.py --port COM12 --pulse-reset --output sd-warm.json
python ports/p2/tests/observe_boot.py --port COM12 --await-power-cycle --output sd-cold.json
```

The second command prints when it is listening. Then switch the **target**
power off and on, leaving the host serial adapter powered. Both commands
require a fresh P2 banner and a working REPL with 32 MiB PSRAM and a mounted
SD. Select the SD boot straps to attribute that observation to the SD image.
