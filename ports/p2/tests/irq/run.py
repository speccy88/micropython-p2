"""Run the opt-in IRQ acceptance on a P2 with P0/P1 and bus test pads unconnected."""

import argparse
import hashlib
import json
import time
from pathlib import Path

from mpremote.transport_serial import SerialTransport


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="running P2 RAM relay or serial port")
    parser.add_argument("--image", required=True, type=Path, help="running IRQ-enabled .bin")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--io", action="store_true", help="Edge: also check buses and read-only media"
    )
    args = parser.parse_args()
    port = Path(__file__).resolve().parents[2]
    here = Path(__file__).resolve().parent
    source = (here / "device.py").read_bytes()
    blob = (here / "stimulus.p2d").read_bytes()
    report = {
        "image_sha256": hashlib.sha256(args.image.read_bytes()).hexdigest(),
        "fixture_sha256": hashlib.sha256(source).hexdigest(),
        "stimulus_sha256": hashlib.sha256(blob).hexdigest(),
        "checks": {},
        "passed": False,
    }
    board = SerialTransport(args.port)

    def check(name, script):
        out, err = board.exec_raw(script, timeout=12)
        report["checks"][name] = {"stdout": out.decode().strip(), "stderr": err.decode().strip()}
        if err:
            raise RuntimeError(f"{name}: {err!r}")
        print(name, out.decode().strip(), flush=True)
        return out

    def setup():
        board.exec(f"IRQ_STIMULUS = {blob!r}")
        board.exec(source)
        board.exec("setup()")

    try:
        board.enter_raw_repl(soft_reset=True)
        if args.io:
            probe = (here / "bus_probe.p2d").read_bytes()
            bus_source = (here / "bus_timing.py").read_bytes()
            report["bus_probe_sha256"] = hashlib.sha256(probe).hexdigest()
            report["bus_fixture_sha256"] = hashlib.sha256(bus_source).hexdigest()
            board.exec(f"BUS_PROBE = {probe!r}")
            check("bus_timing", bus_source)
            board.enter_raw_repl(soft_reset=True)
        setup()
        if args.io:
            check("i2c_timeout", "i2c_timeout()")
        for name in (
            "edges",
            "roots",
            "reentry",
            "masking",
            "loaded_latency",
            "queue",
            "callback_lifecycle",
        ):
            out = check(name, name + "()")
            if name == "callback_lifecycle" and b"IRQ_CALLBACK_PASS" not in out:
                raise AssertionError(out)
        board.exec("driver.stop()")
        for reset in ("raw", "friendly", "raw"):
            board.enter_raw_repl(soft_reset=True)
            setup()
            board.exec("storm()")
            if args.io and reset == "friendly":
                for path in ("tests/bus/loopback.py", "tests/media_readonly.py", "tests/timer.py"):
                    check(path, (port / path).read_bytes())
            board.exec_raw_no_follow("while True:\n pass")
            time.sleep(0.04)
            start = time.monotonic()
            board.serial.write(b"\x03")
            _, err = board.follow(timeout=4)
            if b"KeyboardInterrupt" not in err:
                raise AssertionError(err)
            elapsed = round((time.monotonic() - start) * 1000, 2)
            calls = int(board.exec("print(storm_calls)"))
            assert calls > 0
            board.exec(
                "drive(0); pin.irq(handler=lambda _: print('IRQ_STALE'),trigger=Pin.IRQ_RISING); "
                "machine.disable_irq(); drive(1)"
            )
            if reset == "friendly":
                board.exit_raw_repl()
                assert board.read_until(1, b">>> ", timeout_overall=4).endswith(b">>> ")
                board.serial.write(b"\x04")
                banner = board.read_until(1, b">>> ", timeout_overall=5)
                assert b"MicroPython" in banner and b"IRQ_STALE" not in banner, banner
            board.enter_raw_repl(soft_reset=reset == "raw")
            assert board.exec("import p2;print(p2.pin_owner(0))").strip() == b"free"
            board.exec(
                "import machine; t=machine.disable_irq(); machine.enable_irq(t); assert t == 0"
            )
            report.setdefault("resets_with_active_source", []).append(
                {"mode": reset, "callbacks": calls, "ctrl_c_ms": elapsed}
            )
        report["passed"] = True
    except Exception as exc:
        report["error"] = repr(exc)
        raise
    finally:
        try:
            board.enter_raw_repl(soft_reset=True)
        finally:
            board.close()
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
