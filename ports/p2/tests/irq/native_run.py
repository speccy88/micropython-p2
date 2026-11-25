"""RAM load the CT/context fixture and capture every result line."""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from p2ram import P2Serial, read_image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    image, meta = read_image(args.image)
    report = {
        "image_sha256": meta["sha256"],
        "image_bytes": len(image),
        "lines": [],
        "passed": False,
    }
    try:
        with P2Serial(args.port, baud=2000000) as board:
            report["rom"] = board.identify()
            report["load"] = board.load(image)
            board.serial.baudrate = 115200
            time.sleep(0.2)
            board.send(b"?")
            for _ in range(32):
                line = board.line(timeout=3).decode("ascii")
                report["lines"].append(line)
                print(line, flush=True)
                if line == "IRQ_NATIVE_PASS":
                    report["passed"] = True
                    return
                if line == "IRQ_NATIVE_FAIL":
                    break
            raise RuntimeError("native fixture failed")
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
