"""Run on an Edge or lean image using mpremote run."""

import gc
import micropython
import time
from machine import Timer


def wait_for(predicate):
    started = time.ticks_ms()
    while not predicate():
        if time.ticks_diff(time.ticks_ms(), started) > 1500:
            raise AssertionError("timer callback timed out")


seen = []
once = Timer(-1, mode=Timer.ONE_SHOT, period=25, callback=lambda t: seen.append(t))
wait_for(lambda: seen)
time.sleep_ms(35)
assert seen == [once]


# The timer and its callback must survive collection with no Python reference.
def arm_unreferenced():
    Timer(period=35, mode=Timer.ONE_SHOT, callback=lambda _: seen.append("retained"))


arm_unreferenced()
gc.collect()
wait_for(lambda: len(seen) == 2)
assert seen[-1] == "retained"


def periodic(t):
    seen.append(t)
    if len(seen) == 6:
        t.deinit()


once.init(freq=50, callback=periodic)
wait_for(lambda: len(seen) == 6)
time.sleep_ms(70)
assert len(seen) == 6 and all(t is once for t in seen[2:])
once.deinit()
once.deinit()

once.init(period=3, tick_hz=100, mode=Timer.ONE_SHOT, callback=lambda _: seen.append("old"))
try:
    once.init(period=10, tick_hz=0)
except ValueError:
    pass
else:
    raise AssertionError("invalid tick_hz accepted")
wait_for(lambda: seen[-1] == "old")

for invalid in ({"freq": 0}, {"period": 0}, {"hard": True}, {"mode": 19}):
    try:
        once.init(**invalid)
    except ValueError:
        pass
    else:
        raise AssertionError(invalid)

once.init(period=10, callback=lambda _: seen.append("cancelled"))
once.deinit()
time.sleep_ms(40)
assert seen[-1] == "old"


def cancel_queued(_):
    once.init(mode=Timer.ONE_SHOT, period=5, callback=lambda _: seen.append("stale"))
    time.sleep_ms(20)  # pending timer cannot dispatch from inside this callback
    once.deinit()
    seen.append("cancelled queued")


micropython.schedule(cancel_queued, None)
wait_for(lambda: seen[-1] == "cancelled queued")
time.sleep_ms(25)
assert "stale" not in seen


def fill_queue(_):
    filler = lambda _: None
    while True:
        try:
            micropython.schedule(filler, None)
        except RuntimeError:
            break
    once.init(mode=Timer.ONE_SHOT, period=5, callback=lambda _: seen.append("retry"))
    time.sleep_ms(20)


micropython.schedule(fill_queue, None)
wait_for(lambda: seen[-1] == "retry")
print("Timer passed one-shot, periodic, cancellation, GC, queue and argument checks")
