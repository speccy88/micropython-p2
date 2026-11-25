"""Run a P2 script with named read-only HTTP resources supplied by its USB host."""

import argparse
import http.client
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

MAX_BYTES = 8192
CHUNK = 48
PREFIX = b"\x1eP2:"


class SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old = urllib.parse.urlsplit(req.full_url)
        new = urllib.parse.urlsplit(newurl)
        if (old.scheme, old.netloc.lower()) != (new.scheme, new.netloc.lower()):
            raise ValueError("configure the redirected URL explicitly")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url):
    opener = urllib.request.build_opener(SameOriginRedirect())
    deadline = time.monotonic() + 12
    data = bytearray()
    with opener.open(url, timeout=5) as response:
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError("resource download timed out")
            block = response.read1(MAX_BYTES + 1 - len(data))
            if not block:
                break
            data.extend(block)
            if len(data) > MAX_BYTES:
                raise ValueError("resource exceeds 8192 bytes")
    return data


def run(port, script, resources, idle_timeout):
    from mpremote.transport_serial import SerialTransport

    if not math.isfinite(idle_timeout) or idle_timeout <= 0:
        raise ValueError("idle timeout must be finite and positive")
    board = SerialTransport(port, timeout=5)
    data = b""
    offset = 0
    try:
        board.enter_raw_repl(soft_reset=False)
        board.exec_raw_no_follow(script)
        serial = board.serial
        serial.timeout = min(idle_timeout, 0.25)
        line = bytearray()
        deadline = time.monotonic() + idle_timeout
        while True:
            ch = serial.read(1)
            if not ch:
                if time.monotonic() > deadline:
                    raise TimeoutError("board output timed out")
                continue
            deadline = time.monotonic() + idle_timeout
            if ch == b"\x04":
                sys.stdout.buffer.write(line)
                break
            line.extend(ch)
            if len(line) > 65536:
                raise ValueError("board emitted an overlong output line")
            if ch != b"\n":
                continue
            cmd = bytes(line).rstrip(b"\r\n")
            # A print(..., end="") may precede the device control frame.
            # Only a complete reserved frame with an explicitly configured
            # resource name can request data; the board never supplies a URL.
            text, marker, tail = cmd.rpartition(PREFIX)
            if marker and (tail.startswith(b"GET ") or tail == b"READ"):
                if text:
                    sys.stdout.buffer.write(text)
                    sys.stdout.buffer.flush()
                cmd = marker + tail
            if cmd.startswith(PREFIX + b"GET "):
                name = cmd[len(PREFIX) + 4 :].decode("ascii", "replace")
                data, offset = b"", 0
                try:
                    data = fetch(resources[name])
                except (KeyError, OSError, ValueError, http.client.HTTPException) as exc:
                    print(f"Fetch {name!r} failed: {exc}", file=sys.stderr)
                    serial.write(b"ERR unavailable\n")
                else:
                    serial.write(f"OK {len(data)}\n".encode())
            elif cmd == PREFIX + b"READ":
                if offset >= len(data):
                    serial.write(b"ERR no-data\n")
                else:
                    block = data[offset : offset + CHUNK]
                    serial.write(block.hex().encode() + b"\n")
                    offset += len(block)
            else:
                sys.stdout.buffer.write(line)
                sys.stdout.buffer.flush()
            line.clear()
        error = board.read_until(1, b"\x04", timeout=5)
        if not error.endswith(b"\x04"):
            raise OSError("incomplete raw REPL response")
        if error[:-1]:
            raise RuntimeError(error[:-1].decode("utf-8", "replace"))
    except BaseException:
        # Interrupt a board left polling stdin after cancellation, protocol
        # errors or a stalled host. Preserve the original error on unplug.
        try:
            board.enter_raw_repl(soft_reset=False, timeout_overall=3)
        except Exception:
            pass
        raise
    finally:
        board.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", required=True)
    p.add_argument("--resource", action="append", required=True, metavar="NAME=URL")
    p.add_argument("--idle-timeout", type=float, default=30)
    p.add_argument("script", type=Path)
    args = p.parse_args()
    resources = {}
    for arg in args.resource:
        name, sep, url = arg.partition("=")
        parsed = urllib.parse.urlsplit(url)
        if (
            not 1 <= len(name) <= 40
            or not name.isascii()
            or not name.replace("_", "a").replace("-", "a").isalnum()
            or not sep
            or parsed.scheme not in ("http", "https")
            or not parsed.hostname
        ):
            p.error("Use --resource NAME=https://host/path")
        if name in resources:
            p.error(f"Duplicate resource {name}")
        resources[name] = url
    run(args.port, args.script.read_bytes(), resources, args.idle_timeout)


if __name__ == "__main__":
    main()
