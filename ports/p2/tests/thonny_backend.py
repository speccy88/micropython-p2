"""Exercise Thonny 4.1.7's generic MicroPython backend against the local RAM relay."""

import argparse
import hashlib
import json
import os
from pathlib import Path
from queue import Empty, Queue
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlparse


def relay_serial_type():
    from serial.urlhandler.protocol_socket import Serial

    class RelaySerial(Serial):
        @property
        def out_waiting(self):
            # Socket.write hands all bytes to TCP before it returns; the
            # adapter has no additional userspace transmit queue.
            return 0

        def cancel_read(self):
            if self.is_open:
                try:
                    self._socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    return RelaySerial


def child(options):
    # The stock backend constructs serial.Serial(port=None) and sets port
    # later. Select pyserial's socket transport only for this isolated
    # process; Thonny still runs its own SerialConnection and entire backend.
    import serial
    from thonny.plugins.micropython.bare_metal_backend import (
        GenericBareMetalMicroPythonBackend,
        launch_bare_metal_backend,
    )

    serial.Serial = relay_serial_type()
    sys.argv = [__file__, options]
    launch_bare_metal_backend(GenericBareMetalMicroPythonBackend)


def session(args, report, directory):
    from thonny.common import (
        InlineCommand,
        MESSAGE_MARKER,
        PROCESS_ACK,
        ToplevelCommand,
        ToplevelResponse,
        parse_message,
        serialize_message,
    )

    options = dict(
        port=args.port,
        clean=True,
        sync_time=False,
        validate_time=False,
        local_rtc=False,
        submit_mode="raw_paste",
    )
    env = dict(os.environ, THONNY_USER_DIR=str(directory), PYTHONIOENCODING="utf-8")
    with (directory / "stderr.txt").open("wb") as err:
        proc = subprocess.Popen(
            [sys.executable, "-u", __file__, "--child", repr(options)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=err,
            env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        lines = Queue()

        def read_stdout():
            for line in proc.stdout:
                lines.put(line.decode("utf8", "replace").rstrip("\r\n"))
            lines.put(None)

        reader = threading.Thread(target=read_stdout, daemon=True)
        reader.start()
        output = []

        def receive(predicate, seconds):
            deadline = time.monotonic() + seconds
            while True:
                try:
                    line = lines.get(timeout=max(0, deadline - time.monotonic()))
                except Empty:
                    raise TimeoutError("Thonny response timeout")
                if line is None:
                    raise RuntimeError(f"Thonny backend ended ({proc.poll()})")
                if line == PROCESS_ACK:
                    report["backend_started"] = True
                    continue
                if not line.startswith(MESSAGE_MARKER):
                    continue
                msg = parse_message(line)
                if msg.get("event_type") == "ProgramOutput":
                    output.append(msg.data)
                if predicate(msg):
                    return msg

        def send(cmd):
            proc.stdin.write((serialize_message(cmd) + "\n").encode("ascii"))
            proc.stdin.flush()

        try:
            ready = receive(lambda m: isinstance(m, ToplevelResponse) and "welcome_text" in m, 40)
            report["welcome"] = ready.welcome_text.strip()
            report["cwd"] = ready.cwd
            nonce = secrets.token_hex(12)
            code = (
                "import machine, gc\nassert machine.freq() == 160000000 and gc.mem_free() > 16384\n"
                f"p2_ide_probe = {nonce!r}\nprint('TH_P2', p2_ide_probe)\n"
            )
            output.clear()
            send(ToplevelCommand("run", id="script", source=code))
            receive(lambda m: m.get("command_id") == "script", 15)
            report["stdout"] = "".join(output).strip()
            if report["stdout"] != "TH_P2 " + nonce:
                raise ValueError("backend did not return device output")
            send(InlineCommand("get_globals", id="inspect", module_name="__main__"))
            result = receive(lambda m: m.get("command_id") == "inspect", 15)
            value = result.globals["p2_ide_probe"].repr
            if value != repr(nonce):
                raise ValueError("incorrect variable-inspector reply")
            report["inspected_value"] = value
        finally:
            proc.kill()
            proc.wait(timeout=5)
            proc.stdin.close()
            proc.stdout.close()
            reader.join(timeout=1)


def main():
    import thonny

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    url = urlparse(args.port)
    if url.scheme != "socket" or url.hostname != "127.0.0.1" or not url.port:
        parser.error("use the local RAM session socket://127.0.0.1:<port>")
    report = {
        "thonny": thonny.get_version(),
        "backend": "GenericBareMetalMicroPythonBackend",
        "transport": "Thonny SerialConnection over pyserial socket transport",
        "serial_endpoint": args.port,
        "flat_image_sha256": hashlib.sha256(args.image.read_bytes()).hexdigest(),
        "passed": False,
    }
    with tempfile.TemporaryDirectory() as work:
        directory = Path(work)
        try:
            session(args, report, directory)
            report["passed"] = True
        except Exception as exc:
            report["error"] = repr(exc)
            for name in ("stderr.txt", "backend.log"):
                path = directory / name
                if path.exists():
                    report[name] = path.read_text(encoding="utf-8", errors="replace")[-3000:]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--child":
        child(sys.argv[2])
    else:
        raise SystemExit(main())
