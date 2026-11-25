"""Exercise the host bridge protocol and its error paths without a serial device."""

import io
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import p2_http as bridge


class Link:
    def __init__(self, data):
        self.input = io.BytesIO(data)
        self.writes = []

    def write(self, packet):
        self.writes.append(packet)
        return len(packet)

    def read(self, size):
        assert self.timeout is not None
        return self.input.read(size)


class BridgeTests(unittest.TestCase):
    def run_script(self, output, data, idle):
        self.transport = Mock()
        self.transport.serial = Link(data)
        self.transport.read_until.return_value = b"\x04"
        factory = Mock(return_value=self.transport)
        module = SimpleNamespace(SerialTransport=factory)
        with patch.dict(sys.modules, {"mpremote.transport_serial": module}), patch(
            "sys.stdout", output
        ):
            bridge.run("test", b"test", {"item": "https://test.example/item"}, idle)

    def test_mixed_output_and_exact_resource_lookup(self):
        prefix = bridge.PREFIX
        data = b"phase one: " + prefix + b"GET item\r\n" + prefix + b"READ\n"
        data += b"ignored " + prefix + b"GET https://unconfigured.example/\r\n"
        data += b"finished\n\x04"
        output = io.TextIOWrapper(io.BytesIO())
        with patch("p2_http.fetch", return_value=b"hello") as fetch:
            self.run_script(output, data, 3)
        fetch.assert_called_once_with("https://test.example/item")
        self.assertEqual(output.buffer.getvalue(), b"phase one: ignored finished\n")
        self.assertEqual(
            self.transport.serial.writes, [b"OK 5\n", b"68656c6c6f\n", b"ERR unavailable\n"]
        )
        self.transport.close.assert_called_once()

    def test_idle_board_interrupts_and_closes(self):
        with self.assertRaisesRegex(TimeoutError, "output timed out"):
            self.run_script(io.TextIOWrapper(io.BytesIO()), b"", 0.002)
        self.assertEqual(self.transport.enter_raw_repl.call_count, 2)
        self.transport.close.assert_called_once()

    def test_cross_origin_redirect_requires_explicit_configuration(self):
        old = urllib.request.Request("https://example.com/start")
        handler = bridge.SameOriginRedirect()
        with self.assertRaises(ValueError):
            handler.redirect_request(old, None, 302, "", {}, "https://elsewhere.example/file")


if __name__ == "__main__":
    unittest.main()
