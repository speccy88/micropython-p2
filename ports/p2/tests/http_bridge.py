"""Exercise HTTP through Windows/Linux/macOS host loopback and a real P2 serial link."""

import argparse
import functools
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", required=True)
    p.add_argument("--image", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        packet = bytes(range(251)) * 3
        (folder / "packet").write_bytes(packet)
        (folder / "empty").write_bytes(b"")
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0), functools.partial(SimpleHTTPRequestHandler, directory=folder)
        )
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        endpoint = "http://127.0.0.1:" + str(server.server_port)
        script = folder / "app.py"
        source = (root / "packages/p2fetch/p2fetch.py").read_text()
        script.write_text(
            source
            + """
try:
    get("unknown")
except OSError:
    pass
else:
    raise AssertionError("unknown resource")
assert get("empty") == b""
assert get("example") == bytes(range(251))*3
print("HTTP_BRIDGE_PASS")
"""
        )
        start = time.monotonic()
        try:
            proc = subprocess.run(
                [
                    sys.executable,
                    str(root / "tools/p2_http.py"),
                    "--port",
                    args.port,
                    "--resource",
                    "example=" + endpoint + "/packet",
                    "--resource",
                    "empty=" + endpoint + "/empty",
                    str(script),
                ],
                capture_output=True,
                text=True,
                timeout=90,
            )
            report = {
                "image_sha256": hashlib.sha256(args.image.read_bytes()).hexdigest(),
                "packet_bytes": len(packet),
                "sha256": hashlib.sha256(packet).hexdigest(),
                "seconds": time.monotonic() - start,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "passed": proc.returncode == 0 and "HTTP_BRIDGE_PASS" in proc.stdout,
            }
            args.output.write_text(json.dumps(report, indent=2) + "\n")
            if not report["passed"]:
                raise RuntimeError(proc.stderr or proc.stdout)
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


if __name__ == "__main__":
    main()
