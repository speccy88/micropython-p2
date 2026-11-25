"""Host-only regression for the binary pyboard socket:// transport."""

from pathlib import Path
import socket
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
from pyboard import Pyboard


class PyboardSocketTest(unittest.TestCase):
    def test_binary_roundtrip(self):
        # Control bytes used by raw REPL plus a telnet escape byte.
        payload = b"\x00\x03\x04\xff\n\r"
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.settimeout(3)
            listener.listen(1)
            port = listener.getsockname()[1]
            board = Pyboard("socket://127.0.0.1:%d" % port, timeout=2)
            peer, _ = listener.accept()
            with peer:
                peer.settimeout(2)
                try:
                    board.serial.write(payload)
                    received = b""
                    while len(received) < len(payload):
                        chunk = peer.recv(512)
                        if not chunk:
                            break
                        received += chunk
                    self.assertEqual(received, payload)
                    peer.sendall(payload)
                    self.assertEqual(board.serial.read(len(payload)), payload)
                finally:
                    board.close()


if __name__ == "__main__":
    unittest.main()
