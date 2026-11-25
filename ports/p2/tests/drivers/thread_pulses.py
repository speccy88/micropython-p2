"""Run with tests/thread_peripheral.py on the threaded profile. Keep P0 and P1 free."""

import _thread
import gc
import p2
import time


def wait(predicate):
    start = time.ticks_ms()
    while not predicate():
        if time.ticks_diff(time.ticks_ms(), start) > 3000:
            raise RuntimeError("worker timeout")
        time.sleep_ms(1)


def rejected(errno, function, *args):
    try:
        function(*args)
    except OSError as exc:
        assert exc.args[0] == errno, exc
    else:
        raise AssertionError("expected driver error")


class PausedFrame:
    def __len__(self):
        return 1

    def __getitem__(self, index):
        assert index == 0
        state[0] = True
        wait(lambda: state[1])
        return 0x005531


def worker():
    try:
        strip.show(PausedFrame())
        wait(lambda: ((counter.count() - initial) & 0xFFFFFFFF) == 24)
        rejected(1, strip.close)
        state[2] = 24
    except BaseException as exc:
        state[2] = repr(exc)


state = [False, False, None]
strip = globals()["Strip"](globals()["WS_IMAGE"], 0)
try:
    counter = globals()["EdgeCounter"](globals()["COUNT_IMAGE"], 1, 0)
    try:
        assert p2.pin_owner(0) == p2.pin_owner(1) == "driver"
        initial = counter.count()
        _thread.start_new_thread(worker, ())
        try:
            wait(lambda: state[0] or state[2] is not None)
            assert state[0], state[2]
            rejected(16, strip.show, [0xFFFFFF])
            rejected(16, strip.close)
            gc.collect()
        finally:
            state[1] = True
        wait(lambda: state[2] is not None)
        assert state[2] == 24, state[2]
        try:
            strip.show([1, -1])
        except ValueError:
            pass
        else:
            raise AssertionError("invalid GRB accepted")
        strip.show([0, 0xFFFFFF])
        wait(lambda: ((counter.count() - initial) & 0xFFFFFFFF) == 72)
    finally:
        counter.close()
    rejected(19, counter.count)
finally:
    strip.close()
assert p2.pin_owner(0) == p2.pin_owner(1) == "free"
print("P2_THREADED_PULSES_PASS", p2.CLOCK_HZ, state[2], 72 - state[2])
