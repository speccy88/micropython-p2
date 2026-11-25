"""Prepare a checksum-guarded loadp2 SPI programmer and optionally send it to an Edge."""

import argparse
import base64
import hashlib
import json
import struct
import time
from pathlib import Path

from p2ram import P2Serial

PORT = Path(__file__).resolve().parents[1]


def programmer(profile, *, web=False):
    fw = PORT / "firmware"
    info = json.loads((fw / "manifest.json").read_text())["profiles"][profile]["flat"]
    app = (fw / info["file"]).read_bytes()
    if hashlib.sha256(app).hexdigest() != info["sha256"]:
        raise ValueError("firmware differs from the release manifest")
    if web:
        filename = "flash_loader_2m.bin"
        expected = "2d7a36a4e694f2d721f2c2a439370ebff504e1a4193dd64f7f91c822ff17f9f8"
    else:
        filename = "flash_loader.bin"
        expected = "ca938b18576dc94f3b26911aab8c527d9f8fb787d928380223263abd7085f436"
    stub = (PORT / "tools/loadp2" / filename).read_bytes()
    if hashlib.sha256(stub).hexdigest() != expected:
        raise ValueError("unexpected flash programmer")
    image = bytearray(stub + app)
    if len(image) % 4 or len(image) + 1024 > 512 * 1024:
        raise ValueError("image cannot fit the flash programmer's hub layout")
    struct.pack_into("<II", image, 4, 0, 0)
    checksum = sum(word for (word,) in struct.iter_unpack("<I", image))
    struct.pack_into("<I", image, 4, -checksum & 0xFFFFFFFF)
    return image


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--profile", choices=["edge", "lean", "threaded"], default="edge")
    p.add_argument("--port", help="serial port connected to the P2")
    p.add_argument("--baud", type=int, default=2000000, help="ROM upload baud rate")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--check", action="store_true", help="check the image without accessing hardware"
    )
    mode.add_argument(
        "--write-boot-flash", action="store_true", help="overwrite the boot area at offset zero"
    )
    args = p.parse_args()
    image = programmer(args.profile)
    print(
        f"{args.profile}: {len(image)} programmer and firmware bytes, SHA256 {hashlib.sha256(image).hexdigest()}"
    )
    if args.check:
        return
    if not args.port:
        p.error("supply --port when programming flash")
    with P2Serial(args.port, baud=args.baud) as target:
        print(target.identify(), flush=True)
        print(
            "Sending SPI programmer. Keep power connected until the firmware starts.", flush=True
        )
        target.send(b"> Prop_Txt 0 0 0 0 ")
        # Match loadp2's single-image flash mode. The stub checks its own
        # checksum and uses the ROM download length to locate the application.
        for start in range(0, len(image), 3072):
            target.send(base64.b64encode(image[start : start + 3072]).rstrip(b"=") + b"\n")
        target.send(b"~")
        target.serial.baudrate = 115200
        tail = bytearray()
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            tail.extend(target.read())
            del tail[:-2048]
            if b"MicroPython v1.29.0" in tail and b">>> " in tail:
                print("Application started. Power-cycle and check the REPL to verify cold boot.")
                return
        raise SystemExit(
            "No startup banner confirmed. Keep the original recovery image and try the RAM session."
        )


if __name__ == "__main__":
    main()
