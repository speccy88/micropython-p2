"""HIL check: sync dirty native files before soft reset using private PSRAM volumes."""

import argparse
import json
from mpremote.transport_serial import SerialTransport


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    args = parser.parse_args()
    board = SerialTransport(args.port)
    try:
        board.enter_raw_repl(soft_reset=True)
        for fs in ("VfsFat", "VfsLfs2"):
            # A newly reset allocator returns the same first 512 KiB region.
            # Only that volatile region is formatted. The test never opens an
            # existing SD/flash filesystem or uses an absolute PSRAM offset.
            prepare = (
                """
import p2, vfs
from p2memory import BlockDevice
ram = p2.PSRAM()
region = ram.alloc(512 * 1024)
marker = ram.alloc(16)
armed = False
class CheckedVolume(BlockDevice):
    def ioctl(self, op, arg):
        if armed and op == 3:
            try:
                unexpected = p2.Cog(1000)
            except OSError as exc:
                marker.write(0, b'blocked!' if exc.args[0] == 16 else b'baderrno')
            else:
                unexpected.stop()
                marker.write(0, b'launched')
        return super().ioctl(op, arg)
volume = CheckedVolume(region)
fs = getattr(vfs, %r)
"""
                % fs
            )
            mount = """
vfs.mount(fs(volume), '/resetcheck')
"""
            board.exec(
                prepare
                + "marker.write(0, b'untested')\nfs.mkfs(volume)\n"
                + mount
                + """
f = open('/resetcheck/dirty', 'wb')
assert f.write(b'reset-preserved:' + bytes(range(251)) * 3) == 769
armed = True
# Leave f, region and filesystem live. No flush, close or unmount here.
"""
            )
            board.enter_raw_repl(soft_reset=True)
            board.exec(
                prepare
                + mount
                + """
with open('/resetcheck/dirty', 'rb') as f:
    assert f.read() == b'reset-preserved:' + bytes(range(251)) * 3
assert marker.read(0, 8) == b'blocked!', marker.read(0, 8)
vfs.umount('/resetcheck')
region.close()
marker.close()
"""
            )
            print(json.dumps({"test": "dirty_file_soft_reset", "filesystem": fs, "passed": True}))
            board.enter_raw_repl(soft_reset=True)
    finally:
        board.close()


if __name__ == "__main__":
    main()
