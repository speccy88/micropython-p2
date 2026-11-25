# Optional loopback: connect P0 to P1. No external signal generator is needed.
from machine import PWM
from p2signals import Frequency
pwm = PWM(0, freq=1000, duty_u16=32768)
try:
    capture = Frequency(1, 8)
    try:
        print(capture.read_hz(200), "Hz")
    finally:
        capture.deinit()
finally:
    pwm.deinit()
