"""Install optional packages in volatile LittleFS2 and exercise their public APIs."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from mpremote.transport_serial import SerialTransport


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    report = {"image_sha256": hashlib.sha256(args.image.read_bytes()).hexdigest()}
    target = SerialTransport(args.port)
    try:
        target.enter_raw_repl()
        target.exec("""
import p2,vfs,os,sys
from p2memory import BlockDevice
region=p2.PSRAM().alloc(524288)
block=BlockDevice(region)
vfs.VfsLfs2.mkfs(block)
vfs.mount(vfs.VfsLfs2(block),'/work')
os.mkdir('/work/lib')
sys.path.insert(0,'/work/lib')
""")
    finally:
        target.close()
    try:
        for pkg in ("p2edit", "p2midi"):
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mpremote",
                    "connect",
                    args.port,
                    "resume",
                    "mip",
                    "install",
                    "--target",
                    "/work/lib",
                    (root / "packages" / pkg / "package.json").as_posix(),
                ],
                check=True,
                timeout=90,
            )
        target = SerialTransport(args.port)
        try:
            target.enter_raw_repl(soft_reset=False)
            result = target.exec("""
import p2edit,p2midi
from machine import UART
assert p2edit.__file__.startswith('/work/lib/')
assert p2midi.__file__.startswith('/work/lib/')
def session(*commands):
    it=iter(commands)
    p2edit._readline=lambda _:next(it)
    return p2edit.edit('/work/hello.py')
assert session('a print(7)', 'w')
assert not session('a invalid', 'q')
assert session('r 1 print(3*4)', 'a pass', 'd 2', 'w')
with open('/work/hello.py') as f: assert f.read()=='print(3*4)\\n'
exec(open('/work/hello.py').read())
uart=UART(1,31250,tx=6,rx=7,loopback=True,timeout=1000)
try:
    midi=p2midi.MidiOut(uart, 16)
    midi.note_on(60,100)
    midi.control(7,80)
    midi.note_off(60)
    uart.flush()
    assert uart.read(9)==bytes((159,60,100,191,7,80,143,60,0))
    assert uart.overruns()==0
finally:
    uart.deinit()
assert p2.pin_owner(6)=='free'
print('EDITOR_MIDI_PASS')
""")
            report["output"] = result.decode().splitlines()
            assert b"EDITOR_MIDI_PASS" in result
            report["passed"] = True
        finally:
            target.close()
    finally:
        target = SerialTransport(args.port)
        try:
            target.enter_raw_repl()
        finally:
            target.close()
            args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
