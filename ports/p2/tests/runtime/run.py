"""RAM-load the native C foundation and verify its challenge and every check."""

import argparse
import json
import secrets
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("image", type=Path)
parser.add_argument("--loader-dir", required=True, type=Path)
parser.add_argument("--port", required=True)
parser.add_argument("--output", required=True, type=Path)
args = parser.parse_args()
sys.path.insert(0, str(args.loader_dir.resolve()))
from p2ram import P2Serial, read_image

checks = ["setjmp_registers", "memory", "varargs", "aggregate", "integer_bool", "libm"]
challenge = secrets.token_bytes(4)
while 3 in challenge:
    challenge = secrets.token_bytes(4)
payload, details = read_image(args.image)
result = dict(port=args.port, image=details, challenge=challenge.hex(), passed=False)
try:
    with P2Serial(args.port) as target:
        result["rom"] = target.identify()
        result["download"] = target.load(payload)
        greeting = target.line().strip()
        if greeting != b"P2CRT ready":
            raise RuntimeError(f"unexpected greeting {greeting!r}")
        start = time.monotonic()
        target.send(challenge)
        response = target.line(timeout=30).decode("ascii").strip()
        result["observed"] = response
        result["seconds"] = time.monotonic() - start
        header, echoed, mask = response.split()
        if header != "P2CRT" or echoed != challenge.hex():
            raise RuntimeError("fixture did not return this run's challenge")
        bits = int(mask, 16)
        result["checks"] = {name: bool(bits & (1 << i)) for i, name in enumerate(checks)}
        result["passed"] = bits == (1 << len(checks)) - 1
except Exception as exc:
    result["error"] = str(exc)
finally:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
sys.exit(0 if result["passed"] else 1)
