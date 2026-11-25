"""Load a native P2 ELF or flat image into RAM, then switch to console speed."""
import argparse
import json
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("image", type=Path)
parser.add_argument("--port", required=True)
parser.add_argument("--loader-dir", type=Path, required=True)
parser.add_argument("--baud", type=int, default=921600, help="ROM baud rate")
parser.add_argument("--receipt", type=Path)
args = parser.parse_args()
sys.path.insert(0, str(args.loader_dir.resolve()))
from p2ram import P2Serial, read_image

image, metadata = read_image(args.image)
receipt = dict(image=metadata)
with P2Serial(args.port, baud=args.baud) as board:
    receipt["device"] = board.port_info
    receipt["rom"] = board.identify()
    receipt["download"] = board.load(image)
    board.serial.baudrate = 115200
    deadline = time.monotonic() + 5
    captured = bytearray()
    while time.monotonic() < deadline and not captured.endswith(b">>> "):
        captured.extend(board.read())
    receipt["console"] = captured.decode("utf8", "backslashreplace")
receipt["friendly_prompt"] = captured.endswith(b">>> ")
print(json.dumps(receipt, indent=2))
if args.receipt:
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
sys.exit(0 if receipt["friendly_prompt"] else 1)
