"""Time checked FAT I/O inside an explicitly designated writable SD directory."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import secrets

from mpremote.transport_serial import SerialTransport


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--sd-directory", required=True, type=PurePosixPath)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not args.sd_directory.is_absolute() or ".." in args.sd_directory.parts:
        parser.error("use an absolute path on the designated SD card")
    path = str(args.sd_directory / ("P2" + secrets.token_hex(3).upper() + ".TMP"))
    board = SerialTransport(args.port)
    try:
        board.enter_raw_repl()
        board.exec(
            "import os,p2sd,time;assert p2sd.active(); path="
            + repr(path)
            + ";open(path,'xb').close()"
        )
        try:
            raw = board.exec("""
buf=bytes(range(256))*4
for trial in range(5):
    start=time.ticks_us()
    with open(path,'wb') as f:
        for _ in range(16):
            assert f.write(buf)==1024
        f.flush()
    write=time.ticks_diff(time.ticks_us(),start)
    start=time.ticks_us()
    with open(path,'rb') as f:
        for _ in range(16): assert f.read(1024)==buf
        assert f.read(1)==b''
    print(write,time.ticks_diff(time.ticks_us(),start))
""")
        finally:
            board.exec("os.remove(path)")
        times = [list(map(int, line.split())) for line in raw.splitlines()]
        assert len(times) == 5
        args.output.write_text(
            json.dumps(
                {
                    "image_sha256": hashlib.sha256(args.image.read_bytes()).hexdigest(),
                    "bytes_per_direction": 16384,
                    "write_flush_close_and_read_compare_us": times,
                },
                indent=2,
            )
            + "\n"
        )
    finally:
        board.close()


if __name__ == "__main__":
    main()
