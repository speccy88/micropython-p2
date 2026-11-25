# Wire a 3.3 V logic pulse source to P1 and connect grounds.
from p2signals import Counter
from time import sleep_ms
counter = Counter(1)
try:
    for _ in range(10):
        sleep_ms(100)
        print(counter.count())
finally:
    counter.deinit()
