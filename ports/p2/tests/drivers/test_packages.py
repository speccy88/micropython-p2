"""Host tests for package semantics and the local mpremote installation path."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

PORT = Path(__file__).resolve().parents[2]


def load(name, path=None, **modules):
    spec = importlib.util.spec_from_file_location(name, path or PORT / "modules" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(mod)
    return mod


class Region:
    def __init__(self):
        self.data = bytearray(1536)

    def capacity(self):
        return len(self.data)

    def readinto(self, start, buffer):
        if start + len(buffer) > len(self.data):
            raise ValueError
        buffer[:] = self.data[start : start + len(buffer)]

    def write(self, start, buffer):
        if start + len(buffer) > len(self.data):
            raise ValueError
        self.data[start : start + len(buffer)] = buffer

    def fill(self, start, size, value):
        self.data[start : start + size] = bytes([value]) * size


class Pin:
    IN = 0
    OUT = 1

    def __init__(self, *args, **kwargs):
        self.active = True
        self.level = False

    def value(self, level):
        self.level = level

    def on(self):
        self.value(True)

    def off(self):
        self.value(False)

    def deinit(self):
        self.active = False


class SmartPin(Pin):
    PLUS1_B, MINUS1_B, QUADRATURE, PERIODS_TICKS, COUNT_RISES = 1 << 24, 7 << 24, 22, 38, 28

    def __init__(self, pin, mode, x):
        super().__init__()
        self.mode, self.x, self.z = mode, x, 0

    def ready(self):
        return True

    def read(self):
        return self.z

    peek = read


class PWM(Pin):
    def duty_u16(self, value):
        self.duty = value


class Packages(unittest.TestCase):
    def test_simple_extended_block_io(self):
        block = load("p2memory").BlockDevice(Region())
        block.writeblocks(1, b"a" * 512)
        self.assertEqual(block.ioctl(4, 0), 3)
        self.assertEqual(block.ioctl(5, 0), 512)
        block.writeblocks(1, b"bc", 17)
        output = bytearray(4)
        block.readblocks(1, output, 16)
        self.assertEqual(output, b"abca")
        self.assertEqual(block.ioctl(6, 1), 0)
        block.readblocks(1, output, 15)
        self.assertEqual(output, b"\xff" * 4)
        for args in [
            (-1, bytearray(512)),
            (3, bytearray()),
            (2, bytearray(1024)),
            (0, bytearray(1)),
            (0, bytearray(1), -1),
        ]:
            with self.assertRaises(ValueError):
                block.readblocks(*args)

    def test_install_payloads(self):
        for manifest in sorted((PORT / "packages").glob("*/package.json")):
            package = json.loads(manifest.read_text())
            self.assertEqual(package["version"], "0.1.0")
            for dest, src in package["urls"]:
                payload = (manifest.parent / src).resolve()
                self.assertEqual(payload.name, dest)
                self.assertTrue(payload.is_file())
                self.assertIn(PORT, payload.parents)

    def test_legacy_pin_and_pwm(self):
        legacy = load(
            "p2legacy",
            PORT / "packages/p2legacy/p2legacy.py",
            machine=SimpleNamespace(Pin=Pin, PWM=PWM),
            time=SimpleNamespace(sleep_ms=lambda t: None),
        )
        legacy.pinl(0)
        legacy.pint(0)
        self.assertEqual(legacy._outputs[0][1], 1)
        legacy.freepin(0)
        legacy.startled(0, 2)
        legacy.setled(0, 128)
        self.assertEqual(legacy._leds[0].duty, 32896)
        with self.assertRaises(ValueError):
            legacy.setled(0, 256)
        legacy.freepin(0)
        self.assertFalse(legacy._leds)

    def test_sensor_and_display(self):
        devices = load("p2devices", time=SimpleNamespace(sleep_ms=lambda t: None))
        calls = []
        bus = SimpleNamespace(
            writeto=lambda *args: calls.append(args), readfrom=lambda a, n: b"\xff\x80"
        )
        self.assertEqual(devices.TMP102(bus).millicelsius(), -500)
        self.assertEqual(calls, [(0x48, b"\x00", False)])
        cs, dc = Pin(), Pin()
        spi = SimpleNamespace(write=lambda b: calls.append((cs.level, dc.level, bytes(b))))
        panel = devices.SSD1306Pages(spi, cs, dc, Pin())
        panel.page(3, b"x" * 128)
        self.assertEqual(calls[-2:], [(False, False, b"\xb3\x00\x10"), (False, True, b"x" * 128)])
        with self.assertRaises(ValueError):
            panel.page(8, bytes(128))

        def fail(buf):
            raise OSError

        spi.write = fail
        with self.assertRaises(OSError):
            panel.page(0, bytes(128))
        self.assertTrue(cs.level)

    def test_signals(self):
        signals = load(
            "p2signals",
            p2=SimpleNamespace(CLOCK_HZ=160000000, SmartPin=SmartPin),
            machine=SimpleNamespace(PWM=PWM, Pin=Pin),
            time=SimpleNamespace(ticks_ms=lambda: 0, ticks_diff=lambda a, b: a - b),
        )
        servo = signals.Servo(0)
        servo.pulse_us(1500)
        self.assertEqual(servo.pwm.duty, 4915)
        with self.assertRaises(ValueError):
            servo.pulse_us(999)
        capture = signals.Frequency(1, 4)
        capture.pin.z = 640000
        self.assertEqual(capture.read_hz(), 1000)
        capture.pin.ready = lambda: False
        with self.assertRaises(OSError):
            capture.read_hz(0)
        encoder = signals.Encoder(3, 2)
        self.assertEqual(encoder.a.mode, SmartPin.QUADRATURE | SmartPin.MINUS1_B)
        encoder.a.z = 0xFFFFFFFE
        self.assertEqual(encoder.position(), -2)
        encoder.deinit()
        self.assertFalse(encoder.b.active)
        with self.assertRaises(ValueError):
            signals.Encoder(2, 4)


if __name__ == "__main__":
    unittest.main()
