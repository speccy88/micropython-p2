"""A harmless scheduled marker must run after a borrowed native transfer returns."""
import machine
import micropython
import p2
import time

def ordered(label, fn, *args):
    order = []
    def mark(_):
        order.append("scheduled")
    # No Python branches between scheduling, native call and returned marker.
    micropython.schedule(mark, 0)
    result = fn(*args)
    order.append("returned")
    time.sleep_ms(1)
    assert order == ["returned", "scheduled"], (label, order)
    return result

data = bytearray(1024)
region = p2.PSRAM().alloc(len(data))
try:
    assert ordered("PSRAM write", region.write, 0, data) == len(data)
    assert ordered("PSRAM read", region.readinto, 0, data) == len(data)
finally:
    region.close()

spi = machine.SoftSPI(baudrate=200000, sck=8, mosi=9, miso=9)
try:
    ordered("SPI", spi.write, data)
finally:
    spi.deinit()

uart = machine.UART(1, 115200, tx=6, rx=7, timeout=1000, timeout_char=4,
                    loopback=True)
try:
    # Longer than the native TX ring; the VM waits as the worker drains it.
    assert ordered("UART TX", uart.write, data) == len(data)
    uart.flush()
    while uart.any():
        uart.read(uart.any())
    # Empty ring, so a small timeout exercises the borrowed RX destination.
    assert ordered("UART RX", uart.readinto, bytearray(4)) is None
finally:
    uart.deinit()

import p2sd
card = p2sd.active()
if card:
    assert ordered("SD multi-block read", card.readblocks, 0, data) == 0
print("P2_BORROW_ORDER_PASS")
