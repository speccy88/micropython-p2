from p2signals import Servo
from time import sleep_ms

servo = Servo(0)
try:
    for width in (1500, 1600, 1500):
        servo.pulse_us(width)
        sleep_ms(500)
finally:
    servo.deinit()
