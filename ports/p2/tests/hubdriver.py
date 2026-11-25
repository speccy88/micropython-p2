"""Record the physical HUBEXEC checksum, GC, pin and full-cog soft-reset tests."""

import argparse
import hashlib
import json
from pathlib import Path

from mpremote.transport_serial import SerialTransport


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument(
        "--image", type=Path, required=True, help="running flat MicroPython firmware"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    port = Path(__file__).resolve().parents[1]
    example = port / "examples/hubdriver"
    image = (example / "checksum.p2d").read_bytes()
    source = (example / "checksum.py").read_bytes()
    never_ready = (port / "tests/drivers/neverready.p2d").read_bytes()
    checks = {}
    report = {
        "flat_image_sha256": hashlib.sha256(args.image.read_bytes()).hexdigest(),
        "driver_sha256": hashlib.sha256(image).hexdigest(),
        "neverready_sha256": hashlib.sha256(never_ready).hexdigest(),
        "example_sha256": hashlib.sha256(source).hexdigest(),
        "serial_endpoint": args.port,
        "checks": checks,
        "passed": False,
    }
    setup = b"import p2\nDRIVER_IMAGE = " + repr(image).encode() + b"\n"
    occupy = """
assert p2.pin_owner(5) == 'free'
all_drivers = [p2.Driver(DRIVER_IMAGE, pins=(5,))]
for i in range(5):
    all_drivers.append(p2.Driver(DRIVER_IMAGE))
ids = sorted(d.id() for d in all_drivers)
assert ids == [2, 3, 4, 5, 6, 7], ids
try:
    p2.Driver(DRIVER_IMAGE, pins=(4,))
except OSError as exc:
    assert exc.args[0] == 16, exc
else:
    raise AssertionError('expected cog exhaustion')
assert p2.pin_owner(4) == 'free' and p2.pin_owner(5) == 'driver'
print(ids)
"""
    board = None
    try:
        board = SerialTransport(args.port)
        board.enter_raw_repl(soft_reset=True)
        reply = board.exec(setup + source).decode().strip()
        checks["checksum_gc"] = reply
        if not reply.startswith("P2_HUBDRIVER_PASS "):
            raise AssertionError(reply)
        board.exec(
            setup
            + b"T = "
            + repr(never_ready).encode()
            + b"""
try:
    p2.Driver(T, pins=(5,))
except OSError as exc:
    assert exc.args[0] == 110, exc
else:
    raise AssertionError('expected ready timeout')
assert p2.pin_owner(5) == 'free'
"""
        )
        checks["ready_timeout_released_pin"] = True
        checks["cogs_before_reset"] = json.loads(board.exec(occupy))
        # All six cogs are active while the old Python heap is discarded.
        board.enter_raw_repl(soft_reset=True)
        checks["cogs_after_reset"] = json.loads(board.exec(setup + occupy.encode()))
        board.exec("for d in all_drivers:\n d.stop()\nassert p2.pin_owner(5) == 'free'")
        report["passed"] = True
    except Exception as exc:
        report["error"] = repr(exc)
    finally:
        if board:
            try:
                board.enter_raw_repl(soft_reset=True)
            except Exception as exc:
                report["cleanup_error"] = repr(exc)
                report["passed"] = False
            finally:
                board.close()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
