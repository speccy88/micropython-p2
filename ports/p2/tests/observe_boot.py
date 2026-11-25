"""Observe a P2 ROM boot on a physical port without sending another image."""

import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from p2ram import P2Serial


def until(board, marker, timeout):
    result = bytearray()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result.extend(board.read())
        if marker in result:
            return bytes(result)
        del result[:-16384]
    raise TimeoutError(f"No {marker!r} in {timeout:g} s; captured {bytes(result[-180:])!r}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", required=True, help="physical port, after the RAM relay closes")
    triggers = p.add_mutually_exclusive_group(required=True)
    triggers.add_argument(
        "--pulse-reset",
        dest="trigger",
        action="store_const",
        const="DTR warm reset",
        help="pulse DTR for a warm ROM restart",
    )
    triggers.add_argument(
        "--rom-monitor",
        dest="trigger",
        action="store_const",
        const="ROM monitor SD run",
        help="ask the serial ROM monitor to run _BOOT_P2.BIX from SD",
    )
    triggers.add_argument(
        "--await-power-cycle",
        dest="trigger",
        action="store_const",
        const="operator power cycle",
        help="operator powers the target off/on after listening starts",
    )
    p.add_argument("--timeout", type=float, default=180)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.timeout <= 0 or args.output.exists():
        p.error("choose a positive timeout and a new result path")
    record = {
        "trigger": args.trigger,
        "port": args.port,
        "passed": False,
    }
    try:
        with P2Serial(args.port) as board:
            board.serial.reset_input_buffer()
            if args.trigger == "ROM monitor SD run":
                record["rom"] = board.identify()
                board.send(b"\x04")
                until(board, b"P2-MONITOR ", 3)
                board.send(b"R_BOOT_P2.BIX\r")
                record["command"] = "R_BOOT_P2.BIX"
            elif args.trigger == "DTR warm reset":
                board.serial.dtr = True
                time.sleep(0.02)
                board.serial.dtr = False
            else:
                print(
                    "Listening. Power-cycle the P2 carrier now; keep the USB adapter powered.",
                    flush=True,
                )
            banner = until(board, b">>> ", args.timeout)
            if b"MicroPython " not in banner or b" with Propeller 2" not in banner:
                raise ValueError("expected a fresh P2 startup banner")
            board.send(
                b"import sys,p2,p2sd;print('P2ROM',sys.platform,p2.PSRAM().capacity(),p2sd.active() is not None)\r"
            )
            result = until(board, b">>> ", 10)
            if b"\r\nP2ROM p2 33554432 True\r\n" not in result:
                raise ValueError(f"Edge REPL/SD check failed: {result[-220:]!r}")
            record.update(
                passed=True,
                startup=banner.decode(errors="replace"),
                device="p2",
                psram_bytes=33554432,
                sd_mounted=True,
            )
    except Exception as exc:
        record["error"] = repr(exc)
        raise
    finally:
        with args.output.open("x", encoding="utf-8") as report:
            json.dump(record, report, indent=2)
        print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
