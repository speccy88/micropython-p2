"""TMP102 normal mode and SSD1306 128x64 SPI page output."""

# SPDX-License-Identifier: MIT
from time import sleep_ms


class TMP102:
    """12-bit device, default address 0x48 with ADD0 tied to ground."""

    def __init__(self, bus, address=0x48):
        self.bus = bus
        self.address = address

    def millicelsius(self):
        self.bus.writeto(self.address, b"\x00", False)
        data = self.bus.readfrom(self.address, 2)
        value = ((data[0] << 8) | data[1]) >> 4
        if value & 0x800:
            value -= 4096
        return value * 625 // 10


class SSD1306Pages:
    """128x64 four-wire SPI panel using its internal charge pump, eight pages."""

    def __init__(self, spi, cs, dc, reset):
        self.spi, self.cs, self.dc = spi, cs, dc
        cs.on()
        reset.off()
        sleep_ms(10)
        reset.on()
        sleep_ms(10)
        self._send(
            False,
            bytes(
                (
                    0xAE,
                    0xD5,
                    0x80,
                    0xA8,
                    0x3F,
                    0xD3,
                    0,
                    0x40,
                    0x8D,
                    0x14,
                    0x20,
                    0x02,
                    0xA1,
                    0xC8,
                    0xDA,
                    0x12,
                    0x81,
                    0x7F,
                    0xD9,
                    0xF1,
                    0xDB,
                    0x40,
                    0xA4,
                    0xA6,
                    0xAF,
                )
            ),
        )

    def _send(self, data_mode, data):
        self.dc.value(data_mode)
        self.cs.off()
        try:
            self.spi.write(data)
        finally:
            self.cs.on()

    def page(self, n, pixels):
        if not 0 <= n <= 7 or len(pixels) != 128:
            raise ValueError("one 128-byte page required")
        self._send(False, bytes((0xB0 + n, 0, 0x10)))
        self._send(True, pixels)

    def sleep(self):
        self._send(False, b"\xae")
