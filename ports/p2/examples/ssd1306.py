from machine import Pin, SoftSPI
from p2devices import SSD1306Pages

spi = SoftSPI(sck=8, mosi=9, miso=10, baudrate=1000000, polarity=0, phase=0)
pins = []
try:
    for pin in (11, 12, 13):
        pins.append(Pin(pin, Pin.OUT, value=1))
    display = SSD1306Pages(spi, *pins)
    for n in range(8):
        display.page(n, bytes((0x55 if n & 1 else 0xAA,)) * 128)
finally:
    for pin in pins:
        pin.deinit()
    spi.deinit()
