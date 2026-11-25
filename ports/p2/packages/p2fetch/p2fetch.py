"""Fetch a named resource through the host's p2_http.py serial session."""

import select
import sys
import time

PREFIX = "\x1eP2:"
MAX_BYTES = 8192
CHUNK = 48


def _line(poll):
    started = time.ticks_ms()
    line = bytearray()
    while len(line) <= CHUNK * 2:
        left = 20000 - time.ticks_diff(time.ticks_ms(), started)
        if left <= 0 or not poll.poll(left):
            raise OSError("host timed out")
        ch = sys.stdin.buffer.read(1)
        if ch == b"\n":
            return line.decode()
        if not ch:
            raise OSError("host disconnected")
        line.extend(ch)
    raise ValueError("malformed host reply")


def get(name):
    """Return up to 8192 bytes from a named HTTP(S) resource on the USB host."""
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    if not name or len(name) > 40 or any(c not in alphabet for c in name):
        raise ValueError("invalid resource name")
    poll = select.poll()
    poll.register(sys.stdin, select.POLLIN)
    print(PREFIX + "GET " + name)
    header = _line(poll)
    if not header.startswith("OK "):
        raise OSError("host fetch failed: " + header)
    length = int(header[3:])
    if not 0 <= length <= MAX_BYTES:
        raise ValueError("invalid response length")
    payload = bytearray(length)
    for offset in range(0, length, CHUNK):
        print(PREFIX + "READ")
        block = bytes.fromhex(_line(poll))
        if len(block) != min(length - offset, CHUNK):
            raise ValueError("short host reply")
        payload[offset : offset + len(block)] = block
    return payload
