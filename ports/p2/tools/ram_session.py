"""Keep COM open across stock mpremote calls when DTR is wired to P2 reset."""
import argparse
import json
import select
import socket
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("image", type=Path)
parser.add_argument("--loader-dir", default=Path(__file__).resolve().parent, type=Path)
parser.add_argument("--port", required=True)
parser.add_argument("--listen", type=int, default=8122)
parser.add_argument("--baud", type=int, default=921600)
args = parser.parse_args()
sys.path.insert(0, str(args.loader_dir.resolve()))
from p2ram import P2Serial, read_image

image, meta = read_image(args.image)
with socket.socket() as server, P2Serial(args.port, baud=args.baud) as board:
    server.bind(("127.0.0.1", args.listen))
    server.listen(1)
    rom = board.identify()
    download = board.load(image)
    board.serial.baudrate = 115200
    captured = bytearray()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not captured.endswith(b">>> "):
        captured.extend(board.read())
    print(json.dumps(dict(rom=rom, image=meta, download=download,
                          console=captured.decode("ascii", "backslashreplace"),
                          endpoint=f"socket://127.0.0.1:{args.listen}")), flush=True)
    while True:
        peer, _ = server.accept()
        with peer:
            peer.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            try:
                while True:
                    readable, _, _ = select.select([peer], [], [], 0.002)
                    if readable:
                        data = peer.recv(4096)
                        if not data:
                            break
                        board.send(data)
                    size = board.serial.in_waiting
                    if size:
                        peer.sendall(board.serial.read(size))
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
