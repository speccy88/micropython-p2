"""Verify the capture from a native RAM-load probe."""

import argparse
import json
from pathlib import Path
import re


def check(report):
    lines = report["output"]
    if report["download"]["checksum_ack"] != "." or len(lines) != 5 or lines[-1] != "END":
        raise ValueError("missing ROM acknowledgement or incomplete output")
    if lines[0] != "RAM_ID 0d0d0d0d 5d5d5d5d" or lines[2] != "SMART 8321badc":
        raise ValueError("part IDs or Smart Pin round trip failed")
    ram = re.fullmatch(r"RAM_DATA fca75123 1352c7ba TICKS ([0-9a-f]{8}) ([0-9a-f]{8})", lines[1])
    if not ram:
        raise ValueError("striped words mismatch")
    write, read = (int(v, 16) for v in ram.groups())
    if not (0 < write < 1280 and 0 < read < 1280):
        raise ValueError("8 us tCEM bound exceeded")
    cog = re.fullmatch(r"COG ([0-9a-f]{8}) 00000001 ([0-9a-f]{8})", lines[3])
    if not cog:
        raise ValueError("native driver startup failed")
    cog_id, count = (int(v, 16) for v in cog.groups())
    if not (2 <= cog_id < 8 and 90 <= count <= 105):
        raise ValueError("counter outside expected 10 ms interval")
    return dict(write_cycles=write, read_cycles=read, driver_cog=cog_id, counter=count)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    print(json.dumps(check(json.loads(parser.parse_args().capture.read_text()))))
