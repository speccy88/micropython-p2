"""Smart Pin helpers for servo pulses, frequency capture and encoders."""
# SPDX-License-Identifier: MIT
from machine import PWM, Pin
from p2 import CLOCK_HZ, SmartPin
from time import ticks_ms, ticks_diff

class Servo:
    def __init__(self, pin, minimum_us=1000, maximum_us=2000):
        if not 0 < minimum_us < maximum_us < 20000:
            raise ValueError("invalid pulse limits")
        self.minimum_us = minimum_us
        self.maximum_us = maximum_us
        self.pwm = PWM(pin, freq=50, duty_u16=0)

    def pulse_us(self, pulse):
        if not self.minimum_us <= pulse <= self.maximum_us:
            raise ValueError("pulse outside configured limits")
        self.pwm.duty_u16((pulse * 65535 + 10000) // 20000)

    def deinit(self):
        self.pwm.deinit()

class Frequency:
    def __init__(self, pin, periods=1, source_pin=None):
        if not 1 <= periods <= 65535:
            raise ValueError("periods outside 1..65535")
        mode = SmartPin.PERIODS_TICKS
        if source_pin is not None:
            delta = source_pin - pin
            if not 0 <= source_pin < 64 or not -3 <= delta <= 3:
                raise ValueError("source must be within three pins")
            # Both A and B watch the same pad for rise-to-rise measurements.
            selector = delta & 7
            mode |= (selector << 28) | (selector << 24)
        self.periods = periods
        self.pin = SmartPin(pin, mode, periods)

    def read_hz(self, timeout_ms=1000):
        if timeout_ms < 0:
            raise ValueError("negative timeout")
        start = ticks_ms()
        while not self.pin.ready():
            if ticks_diff(ticks_ms(), start) >= timeout_ms:
                raise OSError(110)
        cycles = self.pin.read()
        if not 0 < cycles < 0x80000000:
            raise ValueError("period measurement overflow")
        return (CLOCK_HZ * self.periods + cycles // 2) // cycles

    def deinit(self):
        self.pin.deinit()

class Encoder:
    """A/B encoder on adjacent GPIOs. Read signed 32-bit position modulo 2**32."""
    def __init__(self, a, b):
        if b == a + 1:
            selector = SmartPin.PLUS1_B
        elif b == a - 1:
            selector = SmartPin.MINUS1_B
        else:
            raise ValueError("A/B must be adjacent")
        self.b = Pin(b, Pin.IN)
        try:
            self.a = SmartPin(a, SmartPin.QUADRATURE | selector, 0)
        except BaseException:
            self.b.deinit()
            raise

    def position(self):
        value = self.a.peek()
        return value if value < 0x80000000 else value - 0x100000000

    def deinit(self):
        self.a.deinit()
        self.b.deinit()

class Counter:
    """Count rising edges on one input, modulo 2**32."""
    def __init__(self, pin):
        self.pin = SmartPin(pin, SmartPin.COUNT_RISES, 0)

    def count(self):
        return self.pin.peek()

    def deinit(self):
        self.pin.deinit()
