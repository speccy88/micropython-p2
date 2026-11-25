from machine import SoftI2C
from p2devices import TMP102
bus = SoftI2C(scl=6, sda=7, freq=100000)
try:
    print(TMP102(bus).millicelsius(), "milli-C")
finally:
    bus.deinit()
