from p2signals import Encoder
from time import sleep_ms

encoder = Encoder(2, 3)
try:
    for _ in range(50):
        print(encoder.position())
        sleep_ms(100)
finally:
    encoder.deinit()
