# Replicate Roger Loh's published 10-second factorial(10) workload at 160 MHz.
from machine import freq
from time import ticks_ms, ticks_diff

def factorial(n):
    if not n:
        return 1
    return n * factorial(n - 1)

def run():
    assert freq() == 160000000 and factorial(10) == 3628800
    count = 0
    start = ticks_ms()
    while ticks_diff(ticks_ms(), start) < 10000:
        factorial(10)
        count += 1
    print("P2_FACTORIAL", count, ticks_diff(ticks_ms(), start), freq())
run()
