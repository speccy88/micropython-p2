# Explicitly create a new filesystem in a freshly allocated volatile region.
import vfs
import p2
from p2memory import BlockDevice
region = p2.PSRAM().alloc(512 * 1024)
try:
    block = BlockDevice(region)
    vfs.VfsLfs2.mkfs(block)
    vfs.mount(vfs.VfsLfs2(block), "/ram")
    try:
        with open("/ram/probe.txt", "w") as f:
            f.write("P2 PSRAM volume\n")
        with open("/ram/probe.txt") as f:
            print(f.read())
    finally:
        vfs.umount("/ram")
finally:
    region.close()
