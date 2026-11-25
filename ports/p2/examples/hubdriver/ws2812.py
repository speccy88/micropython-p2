"""One native cog, one GPIO, 1..32 WS2812B-V5/W pixels, 160 MHz only."""

import p2
import time


class Strip:
    """One producer per strip. Serialize show() calls when sharing across threads."""

    def __init__(self, image, pin):
        if not isinstance(pin, int) or not 0 <= pin < 40 or p2.CLOCK_HZ != 160000000:
            raise ValueError("requires GPIO 0..39 and 160 MHz")
        self.driver = p2.Driver(image, pins=(pin,))
        self.driver.word(4, pin)

    def show(self, colors):
        """Send up to 32 packed 0xGGRRBB colors and wait for the latch interval."""
        count = len(colors)
        if not 1 <= count <= 32:
            raise ValueError("expected 1..32 pixels")
        last = self.driver.word(1)
        if self.driver.word(2) != last:
            raise OSError(16)
        for i in range(count):
            value = colors[i]
            if not isinstance(value, int) or not 0 <= value <= 0xFFFFFF:
                raise ValueError("expected 24-bit GRB")
            self.driver.word(6 + i, value)
        self.driver.word(5, count)
        sequence = (last + 1) & 0xFFFFFFFF
        self.driver.word(1, sequence)
        start = time.ticks_ms()
        while self.driver.word(2) != sequence:
            if time.ticks_diff(time.ticks_ms(), start) > 100:
                raise OSError(110)
        if self.driver.word(3):
            raise OSError(22)

    def close(self):
        self.driver.stop()
