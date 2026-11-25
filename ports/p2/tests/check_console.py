"""Verify the bootstrap and full-duplex console using the pinned TinyGo ROM loader."""
import argparse
import hashlib
import json
import secrets
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--loader-dir", required=True, type=Path)
parser.add_argument("--port", required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("elf", type=Path)
args = parser.parse_args()
sys.path.insert(0, str(args.loader_dir.resolve()))
from p2ram import P2Serial, read_image

payload, details = read_image(args.elf)
nonce = secrets.token_bytes(32)
pattern = hashlib.shake_256(nonce).digest(16384)
with P2Serial(args.port) as dev:
    rom = dev.identify()
    download = dev.load(payload)
    greeting = dev.line().strip()
    if greeting != b"P2 console ready":
        raise RuntimeError(repr(greeting))
    # Pipeline one USB transaction at a time and verify wraparound in both rings.
    start = time.monotonic()
    for pos in range(0, len(pattern), 512):
        packet = pattern[pos:pos + 512]
        dev.send(packet)
        echoed = bytearray()
        deadline = time.monotonic() + 3
        while len(echoed) < len(packet) and time.monotonic() < deadline:
            echoed.extend(dev.read(len(packet) - len(echoed)))
        if echoed != packet:
            raise RuntimeError(f"echo mismatch at chunk {pos}, received {len(echoed)} bytes")
    elapsed = time.monotonic() - start
result = dict(port=args.port, rom=rom, elf_sha256=details["sha256"], download=download,
              nonce=nonce.hex(), echo_bytes=len(pattern), seconds=elapsed, passed=True)
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result))
