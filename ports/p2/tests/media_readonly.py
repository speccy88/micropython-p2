"""Check existing media without writing sectors or formatting filesystems."""
import os
import time
import vfs
import p2
import p2sd

sd = p2sd.active()
if sd is not None:
    count = sd.ioctl(4, 0)
    buf = bytearray(512)
    again = bytearray(512)
    for i in (0, 1, count // 2, count - 1):
        sd.readblocks(i, buf)
        sd.readblocks(i, again)
        assert buf == again
    buf = bytearray(4096)
    t = time.ticks_us()
    for i in range(4):
        sd.readblocks(i * 8, buf)
    print("SD_READ", count, 512, 16384, time.ticks_diff(time.ticks_us(), t))
    names = os.listdir("/")
    print("FAT_ROOT_COUNTS", len(names), len(set(names)))
    distinct = []
    for name in names:
        if name not in distinct:
            distinct.append(name)
    assert len(distinct) == len(set(names)), "name equality and set count disagree"
    vfs.umount("/")
    if p2sd.active() is not None:
        sd.ioctl(2, 0)
else:
    print("SD_NOT_MOUNTED")
print("JEDEC", hex(p2.Flash.probe()))
flash = p2.Flash()
try:
    assert flash.ioctl(4, 0) == 256
    assert flash.ioctl(5, 0) == 4096
    first = bytearray(32)
    second = bytearray(32)
    for sector in (0, 1, 255):
        flash.readblocks(sector, first, 17)
        flash.readblocks(sector, second, 17)
        assert first == second
    print("FLASH_READ_PASS", 256, 4096)
finally:
    flash.deinit()
