"""Run in RAM with mpremote connect COM12 run tests/vm.py."""
import gc
import json
import micropython
import sys
import time


def require(condition, description):
    if not condition:
        raise AssertionError(description)


def outer(n):
    if n:
        try:
            return outer(n - 1)
        except ValueError as exc:
            return exc.args[0] + n
    raise ValueError(17)


class Receiver:
    def take(self, *args, **kwargs):
        # Exercise both successful and exceptional bound-method temporary
        # lifetimes while allocation and GC run in a nested Python frame.
        gc.collect()
        if kwargs["fail"]:
            raise IndexError(args[-1])
        return args


def recurse(n):
    return recurse(n + 1)


def main():
    gc.collect()
    initial = gc.mem_free()
    require(outer(4) == 18, "nested exception payload or return")
    method = Receiver().take
    for i in range(30):
        try:
            method(0, 1, 2, 3, 4, i, fail=True)
        except IndexError as exc:
            require(exc.args == (i,), "exception argument")
        else:
            raise AssertionError("method did not raise")
        require(method(0, 1, 2, 3, 4, i, fail=False)[-1] == i, "bound method")

    # The temporary argument vector exceeds the configured 8 KiB pystack.
    # The exception must rewind its cursor so the next call still succeeds.
    try:
        method(*([0] * 3072), fail=False)
    except RuntimeError as exc:
        require("pystack" in str(exc), "unexpected allocation failure")
    else:
        raise AssertionError("oversized temporary argument vector")
    require(method(4, 2, fail=False) == (4, 2), "pystack recovery")

    try:
        recurse(0)
    except RuntimeError:
        pass
    else:
        raise AssertionError("recursion limit")

    blocks = []
    try:
        while True:
            blocks.append(bytearray(256))
    except MemoryError:
        pass
    blocks = None
    gc.collect()
    require(len(bytearray(2048)) == 2048, "allocation after OOM")

    require((1 << 90) // (1 << 60) == 1 << 30, "MPZ division")
    require(-17 // 5 == -4 and -17 % 5 == 3, "signed division")
    require(list(i * i for i in range(4)) == [0, 1, 4, 9], "generator")
    require(json.loads('{"test":true}')["test"], "json import")
    durations = []
    for i in range(20):
        start = time.ticks_us()
        gc.collect()
        durations.append(time.ticks_diff(time.ticks_us(), start))
    start = time.ticks_us()
    acc = 0
    for i in range(1000):
        acc += i
    elapsed = time.ticks_diff(time.ticks_us(), start)
    require(acc == 499500, "VM arithmetic benchmark")
    durations.sort()
    print(json.dumps({
        "test": "vm", "passed": True, "platform": sys.platform,
        "mpy": sys.implementation._mpy, "initial_heap_free": initial,
        "heap_free_after": gc.mem_free(), "gc_us_min": durations[0],
        "gc_us_median": durations[len(durations) // 2], "gc_us_max": durations[-1],
        "integer_loop_1000_us": elapsed, "c_stack_used": micropython.stack_use(),
    }))


main()
