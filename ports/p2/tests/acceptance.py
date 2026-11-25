"""Record raw-paste, interruption, resets and script results from a physical P2."""

import argparse
import hashlib
import json
import secrets
import time
from pathlib import Path
from mpremote.transport_serial import SerialTransport

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--port", required=True)
p.add_argument("--image", required=True, type=Path)
p.add_argument("--output", type=Path, required=True)
p.add_argument("--scripts", nargs="*")
args = p.parse_args()
port = Path(__file__).resolve().parents[1]
checks = {}
report = {
    "flat_image_sha256": hashlib.sha256(args.image.read_bytes()).hexdigest(),
    "serial_endpoint": args.port,
    "checks": checks,
}


def save():
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


board = SerialTransport(args.port)
try:
    board.enter_raw_repl()
    nonce = secrets.token_hex(12)
    script = (
        "# abcdefghijklmnopqrstuvwxyz0123456789\n" * 1024 + "print('" + nonce + "')"
    ).encode()
    reply = board.exec(script).decode().strip()
    checks["large_raw_paste"] = {
        "bytes": len(script),
        "reply": reply,
        "nonce": nonce,
        "passed": reply == nonce and board.use_raw_paste,
    }
    # An intact raw prompt can follow a damaged output stream. Check every
    # byte in more than sixty TX ring lengths, including ordered line IDs.
    payload = nonce * 3
    expected = "".join("%04x %s\r\n" % (i, payload) for i in range(1024)).encode()
    received = board.exec(f"for i in range(1024):\n print('%04x ' % i + {payload!r})")
    checks["large_serial_output"] = {
        "expected_bytes": len(expected),
        "received_bytes": len(received),
        "expected_sha256": hashlib.sha256(expected).hexdigest(),
        "received_sha256": hashlib.sha256(received).hexdigest(),
        "passed": received == expected,
    }
    board.exec_raw_no_follow("while True:\n pass")
    time.sleep(0.1)
    board.serial.write(b"\x03")
    _, err = board.follow(4)
    checks["interrupt_loop"] = {"passed": b"KeyboardInterrupt" in err, "exception": err.decode()}
    for i in range(4):
        board.enter_raw_repl(soft_reset=True)
        print_id = board.exec("import gc;print(gc.mem_free())").strip()
        checks[f"soft_reset_{i}"] = {"passed": int(print_id) > 16384, "heap_free": int(print_id)}
    for script in args.scripts or []:
        board.enter_raw_repl(soft_reset=True)
        source = (port / script).read_bytes()
        start = time.monotonic()
        board.exec_raw_no_follow(source)
        output, error = board.follow(180)
        checks[script] = {
            "sha256": hashlib.sha256(source).hexdigest(),
            "seconds": time.monotonic() - start,
            "passed": not error,
            "stdout": output.decode("utf8", "replace").strip(),
            "stderr": error.decode("utf8", "replace").strip(),
        }
        save()
        print(script, checks[script]["passed"], checks[script]["stderr"], flush=True)
    report["passed"] = all(c["passed"] for c in checks.values())
except Exception as exc:
    report["passed"] = False
    report["error"] = repr(exc)
finally:
    board.close()
    save()
raise SystemExit(0 if report["passed"] else 1)
