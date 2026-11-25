"""Exercise a physical Edge for a configurable duration using private PSRAM storage."""

import argparse
import hashlib
import json
import time
from pathlib import Path

from mpremote.transport_serial import SerialTransport

SETUP = """
import gc,time,p2,vfs
from machine import Timer
from p2memory import BlockDevice
ram=p2.PSRAM()
disk=ram.alloc(512*1024)
region=ram.alloc(65536)
vol=BlockDevice(disk)
vfs.VfsLfs2.mkfs(vol)
vfs.mount(vfs.VfsLfs2(vol),'/soak')
worker=p2.Cog(1000)
ticks=[0]
def tick(timer):
    ticks[0]+=1
timer=Timer(period=50,callback=tick)
buf=bytearray(256)
rx=bytearray(256)
def batch(seq):
    for j in range(24):
        x=(seq*24+j)&255
        for k in range(256): buf[k]=(k^x)
        region.write(x*256,buf)
        region.readinto(x*256,rx)
        assert rx==buf
        with open('/soak/check','wb') as f:
            assert f.write(buf)==len(buf)
            f.flush()
        with open('/soak/check','rb') as f: assert f.read()==buf
        garbage=[bytearray(31+i) for i in range(24)]
        del garbage
        gc.collect()
    print(seq, gc.mem_free(), worker.count(), ticks[0], sum(rx), p2.pin_owner(62))
"""
CLOSE = """
timer.deinit()
worker.stop()
vfs.umount('/soak')
region.close()
disk.close()
gc.collect()
print(gc.mem_free())
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument(
        "--seconds", type=int, default=30, help="duration in seconds (3600 for an hour)"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.seconds < 1:
        parser.error("duration must be positive")
    report = {
        "image_sha256": hashlib.sha256(args.image.read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "requested_seconds": args.seconds,
        "samples": [],
        "passed": False,
    }
    board = SerialTransport(args.port)

    def save():
        args.output.write_text(json.dumps(report, indent=2) + "\n")

    try:
        board.enter_raw_repl()
        report["start"] = (
            board.exec("import gc,machine;gc.collect();print(machine.freq(),gc.mem_free())")
            .decode()
            .strip()
        )
        board.exec(SETUP)
        start = time.monotonic()
        seq = 0
        low = None
        last_cog = last_timer = 0
        while time.monotonic() - start < args.seconds:
            before = time.monotonic()
            out = board.exec("batch(%d)" % seq).split()
            n, free, cog, timer, checksum = map(int, out[:5])
            if (
                n != seq
                or checksum != 32640
                or cog <= last_cog
                or timer <= last_timer
                or out[5] != b"console"
            ):
                raise RuntimeError("Unexpected board response: %r" % out)
            last_cog, last_timer = cog, timer
            low = free if low is None else min(low, free)
            elapsed = time.monotonic() - start
            report.update(
                seconds=round(elapsed, 2),
                batches=seq + 1,
                min_free=low,
                max_roundtrip_s=max(report.get("max_roundtrip_s", 0), time.monotonic() - before),
            )
            if not report["samples"] or elapsed - report["samples"][-1]["seconds"] >= 60:
                report["samples"].append(
                    dict(
                        seconds=int(elapsed),
                        heap=free,
                        worker_count=cog,
                        timer_callbacks=timer,
                        batch=seq,
                    )
                )
                save()
            seq += 1
        report["cleanup_heap"] = int(board.exec(CLOSE))
        board.enter_raw_repl()
        report["reset_heap"] = int(board.exec("import gc;gc.collect();print(gc.mem_free())"))
        report["passed"] = True
    except Exception as exc:
        report["error"] = repr(exc)
        raise
    finally:
        try:
            board.enter_raw_repl()
        finally:
            board.close()
            save()


if __name__ == "__main__":
    main()
