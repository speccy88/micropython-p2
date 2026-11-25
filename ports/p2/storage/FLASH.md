# Winbond flash and LittleFS2

The [physical acceptance and recovery guide](ACCEPTANCE.md) covers a designated single-sector erase/program test, SD startup scripts and ROM boot from FAT32.

The Edge firmware exposes `p2.Flash` when LittleFS2 is compiled in. Run `p2.Flash.probe()` to read the three-byte JEDEC ID. A supported W25Q128 returns `0xef4018` or `0xef7018`. A successful probe briefly claims P58–P61 and releases them. The flash and onboard SD share data lines and exchange clock and select pins. Flash uses mode 3 and moves P61 only with P60 high, so the SD select is inactive on each SD clock edge. If the SD driver owns these pins, opening flash fails with `OSError(EBUSY)`. Close files and unmount the SD VFS before explicitly deinitialising the SD block device with `sd.ioctl(2, 0)`.

| Byte addresses | Default use |
| --- | --- |
| `0x000000–0x0fffff` | Reserved. The boot image fits in the first 512 KiB. The driver excludes the entire first MiB from block-device access. |
| `0x100000–0xefffff` | Available for other data, outside the default partition. |
| `0xf00000–0xffffff` | Default 1 MiB LittleFS2 partition, 256 × 4 KiB sectors. Existing data in these sectors is preserved on open. |

`Flash(start=..., size=..., writable=False)` takes aligned byte offsets and byte lengths. Partitions must fit in the detected 16 MiB device. Opening and ordinary boot never format flash. The non-destructive physical probe is `mpremote connect COM12 run tests/bus/flash_probe.py` from this port. It reads the ID and checks repeatable partial reads at three offsets.

Mount a partition already containing LittleFS2:

```python
import p2, vfs
flash = p2.Flash()
vfs.mount(vfs.VfsLfs2(flash), "/flash", readonly=True)
print(__import__("os").listdir("/flash"))
vfs.umount("/flash")
flash.deinit()
```

The following is an explicit provisioning example. Formatting erases user data in the selected partition. Use it only after selecting a disposable or backed-up partition. It is not executed during build or acceptance.

```python
import p2, vfs
flash = p2.Flash(start=0xf00000, size=0x100000, writable=True)
vfs.VfsLfs2.mkfs(flash)
vfs.mount(vfs.VfsLfs2(flash), "/flash")
with open("/flash/hello.txt", "w") as f:
    f.write("P2 Edge\n")
vfs.umount("/flash")
flash.deinit()
```

The extended block protocol separates 4 KiB erase and offset-based page programming. Ordinary whole-sector writes erase each sector first. Programs split on 256-byte boundaries, check the write-enable latch, wait up to two seconds for BUSY to clear, then read the data back. Erases likewise verify every byte. Hardware write protection is respected. An error or interruption can leave a multi-page request partially written. A future call starts by checking BUSY. No command changes protection settings or erases the whole chip.

The host model compiles the actual NOR command engine into a test with the pinned upstream LittleFS2, checks data after unmount/remount, and injects protected program/erase and stuck BUSY faults. From `ports/p2`:

```sh
cc -std=c11 -O2 -Wall -Wextra -DLFS2_NO_DEBUG -DLFS2_NO_WARN -DLFS2_NO_ERROR -I../../lib/littlefs \
  tests/bus/flash_model.c ../../lib/littlefs/lfs2.c ../../lib/littlefs/lfs2_util.c -o /tmp/flash_model
/tmp/flash_model
```

Hardware references: [Parallax Edge flash reader](https://obex.parallax.com/docs/quick-bytes/propeller-2/p2-edge-16-mb-flash-reader-and-explorer-utility/) and [Winbond W25Q128JV datasheet](https://cdn.sparkfun.com/assets/9/d/7/a/d/w25q128jv_revf_03272018_plus.pdf).
