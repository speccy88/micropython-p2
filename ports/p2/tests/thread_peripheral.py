"""Exercise shared WS2812 and edge-counter drivers on the running threaded image."""

import argparse
import hashlib
import json
from pathlib import Path

from mpremote.transport_serial import SerialTransport


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--image", type=Path, required=True, help="running threaded flat image")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    port = Path(__file__).resolve().parents[1]
    example = port / "examples/hubdriver"
    probe = port / "tests/drivers/thread_pulses.py"
    record = {"flat_image_sha256": hashlib.sha256(args.image.read_bytes()).hexdigest()}
    digests = {}
    board = SerialTransport(args.port)
    try:
        board.enter_raw_repl(soft_reset=True)
        for name, image_var in (("ws2812", "WS_IMAGE"), ("edgecount", "COUNT_IMAGE")):
            image = (example / (name + ".p2d")).read_bytes()
            source = (example / (name + ".py")).read_bytes()
            digests[name + ".p2d"] = hashlib.sha256(image).hexdigest()
            digests[name + ".py"] = hashlib.sha256(source).hexdigest()
            board.exec(f"{image_var} = {image!r}")
            board.exec(source)
        fixture = probe.read_bytes()
        digests[probe.name] = hashlib.sha256(fixture).hexdigest()
        out, err = board.exec_raw(fixture, timeout=20)
        if err or out.strip() != b"P2_THREADED_PULSES_PASS 160000000 24 48":
            raise RuntimeError((out, err))
        record.update(inputs_sha256=digests, output=out.decode().strip(), pins_released=[0, 1])
    finally:
        board.close()
    args.output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(record["output"])


if __name__ == "__main__":
    main()
