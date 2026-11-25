"""Run through mpremote on a bare P2 Edge with P2_ENABLE_BUSES=1."""
import gc
import machine
import p2

def raises(exc, fn):
    try:
        fn()
    except exc:
        return
    raise AssertionError("exception was not raised")

# The P2 RX input mux reads the actual driven TX pad on its adjacent pin.
uart = machine.UART(1, 115200, tx=6, rx=7, timeout=1000, loopback=True)
assert p2.pin_owner(6) == "uart"
raises(OSError, lambda: machine.Pin(6))
packet = bytes(range(192))
assert uart.write(packet) == len(packet)
gc.collect()
uart.flush()
assert uart.read(len(packet)) == packet
assert uart.txdone() and uart.overruns() == 0
uart.deinit()
raises(OSError, uart.any)
assert p2.pin_owner(6) == "free"

# Read the driven MOSI pad for a wire-free local SPI loopback in all modes.
for pol in (0, 1):
    for phase in (0, 1):
        for first in (0, 1):
            spi = machine.SoftSPI(baudrate=200000, sck=8, mosi=9, miso=9,
                                  polarity=pol, phase=phase, firstbit=first)
            rx = bytearray(17)
            tx = packet[3:20]
            spi.write_readinto(tx, rx)
            assert rx == tx
            spi.deinit()
            raises(OSError, lambda: spi.write(b"x"))
assert p2.pin_owner(9) == "free"
raises(ValueError, lambda: machine.SoftSPI(baudrate=0, sck=3, mosi=4, miso=5))

# No external pull-ups or target are assumed here.
i2c = machine.SoftI2C(scl=10, sda=11, timeout=250)
assert p2.pin_owner(10) == "i2c"
raises(OSError, lambda: machine.Pin(11))
raises(OSError, lambda: i2c.writeto(128, b"x"))
i2c.deinit()
raises(OSError, i2c.start)
assert p2.pin_owner(10) == "free"
raises(OSError, lambda: machine.SoftI2C(scl=4, sda=62))
assert p2.pin_owner(4) == "free"
print("P2 bus loopbacks and ownership OK")
