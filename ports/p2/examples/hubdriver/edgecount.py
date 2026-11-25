"""Read a hardware rising-edge counter from either Python cog."""
# SPDX-License-Identifier: MIT

import p2
import time


class EdgeCounter:
    def __init__(self, image, pin, source=None):
        if source is None:
            source = pin
        if not isinstance(pin, int) or not isinstance(source, int):
            raise TypeError("pin and source must be integers")
        if not 0 <= pin < 40 or not 0 <= source < 40 or abs(source - pin) > 3:
            raise ValueError("use GPIO 0..39 and a source within three pins")
        self.driver = p2.Driver(image, pins=(pin,))
        try:
            self.driver.word(4, pin)
            self.driver.word(5, (source - pin) & 7)
            self.driver.word(1, 1)
            start = time.ticks_ms()
            while self.driver.word(2) != 1:
                if time.ticks_diff(time.ticks_ms(), start) >= 100:
                    raise OSError(110)
            if self.driver.word(3):
                raise ValueError("invalid counter setup")
        except BaseException:
            self.driver.stop()
            raise

    def count(self):
        """Return the latest unsigned 32-bit snapshot. Reading leaves it running."""
        return self.driver.word(6)

    def close(self):
        self.driver.stop()
