"""Prepend p2events.py. Leave P0 and P1 free; P1 observes P0's driven pad."""

import gc
import time
import machine
import p2

events = []
pwm = machine.PWM(0, freq=1000, duty_u16=32768)
try:
    watch = globals()["RisingEdges"](1, events.append, period_ms=25, source_pin=0)
    try:
        gc.collect()
        start = time.ticks_ms()
        while len(events) < 4:
            if time.ticks_diff(time.ticks_ms(), start) > 1500:
                raise RuntimeError("event timeout")
        assert all(1 <= n <= 100 for n in events)
    finally:
        watch.deinit()
    n = len(events)
    time.sleep_ms(60)
    assert len(events) == n and p2.pin_owner(1) == "free"
finally:
    pwm.deinit()
print("EDGE_EVENTS_PASS", events)
