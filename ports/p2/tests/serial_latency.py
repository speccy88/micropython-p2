"""Time exact-output transfers and Ctrl-C at 115200 baud through a RAM relay."""

import argparse
import hashlib
import json
from pathlib import Path
import time

from mpremote.transport_serial import SerialTransport


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    board = SerialTransport(args.port)
    output = b"abcdef0123456789" * 8
    expect = (output + b"\r\n") * 48
    samples = []
    try:
        board.enter_raw_repl()
        for _ in range(5):
            start = time.monotonic()
            assert board.exec("for i in range(48):print('abcdef0123456789'*8)") == expect
            transfer = time.monotonic() - start
            board.exec_raw_no_follow("while True:\n pass")
            time.sleep(0.05)
            start = time.monotonic()
            board.serial.write(b"\x03")
            _, err = board.follow(3)
            assert b"KeyboardInterrupt" in err
            samples.append(
                {
                    "bytes_per_second": round(len(expect) / transfer),
                    "interrupt_to_traceback_ms": round((time.monotonic() - start) * 1000, 2),
                }
            )
    finally:
        board.close()
    args.output.write_text(
        json.dumps(
            {
                "image_sha256": hashlib.sha256(args.image.read_bytes()).hexdigest(),
                "bytes_per_batch": len(expect),
                "samples": samples,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
