"""Run checked benchmark batches on an existing RAM relay and save exact inputs."""

import argparse
import hashlib
import json
import time
from pathlib import Path

from mpremote.transport_serial import SerialTransport


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("scripts", nargs="+", type=Path)
    args = parser.parse_args()
    data = {
        "image_sha256": hashlib.sha256(args.image.read_bytes()).hexdigest(),
        "image_bytes": args.image.stat().st_size,
        "scripts": {},
    }
    target = SerialTransport(args.port)
    try:
        target.enter_raw_repl()
        data["board"] = (
            target.exec(
                "import sys,gc\ntry:\n import machine; clock=machine.freq()"
                "\nexcept ImportError:\n clock=None\ngc.collect();print(sys.implementation,clock,gc.mem_free())"
            )
            .decode()
            .strip()
        )
        for path in args.scripts:
            target.enter_raw_repl()
            code = path.read_bytes()
            start = time.monotonic()
            target.exec_raw_no_follow(code)
            out, err = target.follow(180)
            data["scripts"][path.name] = {
                "sha256": hashlib.sha256(code).hexdigest(),
                "seconds": time.monotonic() - start,
                "output": out.decode().splitlines(),
                "error": err.decode(),
            }
            print(path.name, out.decode()[-150:], err.decode(), flush=True)
            if err:
                raise RuntimeError("Device assertion or exception")
        data["passed"] = True
    finally:
        target.close()
        args.output.write_text(json.dumps(data, indent=2) + "\n")


if __name__ == "__main__":
    main()
