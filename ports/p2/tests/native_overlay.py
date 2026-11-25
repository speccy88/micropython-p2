"""Compare keeping two native services in hub with staging them in a PSRAM region."""

import argparse
import hashlib
import json
from pathlib import Path

from mpremote.transport_serial import SerialTransport


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--port", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    examples = Path(__file__).resolve().parents[1] / "examples/hubdriver"
    images = [(examples / name).read_bytes() for name in ("checksum.p2d", "ws2812.p2d")]
    report = {
        "image_sha256": hashlib.sha256(args.image.read_bytes()).hexdigest(),
        "driver_bytes": list(map(len, images)),
        "modes": {},
    }
    target = SerialTransport(args.port)
    try:
        for external in (False, True):
            target.enter_raw_repl()
            target.exec("import gc,p2,time\ndef free():\n gc.collect()\n return gc.mem_free()")
            # Each raw exec releases its source and code constants before the next measurement.
            target.exec("baseline=free();images=[]")
            if external:
                target.exec("region=p2.PSRAM().alloc(%d)" % sum(map(len, images)))
            offset = 0
            for blob in images:
                if external:
                    target.exec(
                        "region.write(%d,%r);images.append((%d,%d))"
                        % (offset, blob, offset, len(blob))
                    )
                else:
                    target.exec("images.append(%r)" % blob)
                offset += len(blob)
            stored = int(target.exec("print(baseline-free())"))
            target.exec(
                "def launch():\n "
                + ("off,n=images[0];image=region.read(off,n)" if external else "image=images[0]")
                + "\n return p2.Driver(image)"
            )
            samples = []
            for _ in range(5):
                line = target.exec("""
gc.collect()
start=time.ticks_us()
d=launch()
latency=time.ticks_diff(time.ticks_us(),start)
d.word(4,0)
d.word(1,1)
start=time.ticks_ms()
while d.word(2)!=1:
    assert time.ticks_diff(time.ticks_ms(),start)<1000
assert d.word(3)==0 and d.word(5)==0
d.stop()
print(latency)
""")
                samples.append(int(line))
            report["modes"]["psram" if external else "hub"] = {
                "retained_hub_bytes": stored,
                "launch_us": samples,
            }
            if external:
                target.exec("region.close()")
        report["passed"] = True
    finally:
        target.enter_raw_repl()
        target.close()
        args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
