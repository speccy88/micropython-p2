"""Check directory names/identities across multiple FAT sectors on fresh PSRAM."""

import os
import p2
import vfs
from p2memory import BlockDevice

region = p2.PSRAM().alloc(512 * 1024)
block = BlockDevice(region)
vfs.VfsFat.mkfs(block)
volume = vfs.VfsFat(block)
vfs.mount(volume, "/names-test")
try:
    expected = []
    for i in range(40):
        if i % 3 == 0:
            name = "FILE%04d.BIN" % i
        elif i % 3 == 1:
            name = "lower%03d.bin" % i
        else:
            name = "Sample Capture %03d - Long Filename.bin" % i
        expected.append(name)
        with open("/names-test/" + name, "wb") as f:
            f.write(bytes([i]))
    actual = os.listdir("/names-test")
    assert sorted(actual) == sorted(expected), (actual, expected)
    assert len(set(actual)) == len(expected)
    assert sorted(os.listdir(b"/names-test")) == sorted(n.encode() for n in expected)
    for i, name in enumerate(expected):
        with open("/names-test/" + name, "rb") as f:
            assert f.read() == bytes([i])
    print("FAT directory verified 40 unique short, lowercase and long entries")
finally:
    vfs.umount("/names-test")
    region.close()
