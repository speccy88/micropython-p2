"""Controlled Edge workload. Run on-board with the host measurement runner."""

import gc
import micropython
import p2
import time
from p2array import Array


def recur(n):
    return n * recur(n - 1) if n else 1


def alu():
    x = 0
    for i in range(400):
        x += (i * 31) // 7 if i & 1 else i
    return x


def calls():
    return sum(recur(7) for _ in range(60))


def floating():
    x = 0.5
    for _ in range(256):
        x = (x + 0.25) * 0.5
    assert abs(x - 0.25) < 0.00001
    return 256


def maps():
    a = list(range(80))
    d = dict((i, 3 * i) for i in a)
    s = set(a)
    for i in a[::2]:
        del d[i]
        s.remove(i)
    assert len(d) == len(s) == 40
    return sum(d[i] for i in s)


def parse():
    for _ in range(12):
        ns = {}
        exec("def f(n):\n return n * n\nr=f(7)", ns)
        assert ns["r"] == 49
    return 12


def collect():
    for _ in range(8):
        a = [bytearray(i) for i in range(32)]
        assert len(a[-1]) == 31
        gc.collect()
    return 8


def raw_transfer():
    for i in range(16):
        region.write(0, block)
        region.readinto(0, output)
    assert block == output
    return 16 * 8192


def array_seq():
    for i in range(256):
        array[i] = i
    return sum(array[i] for i in range(256))


def array_random():
    for i in range(160):
        array[(i * 311) & 2047] = i
    return sum(array[(i * 311) & 2047] for i in range(160))


gc.collect()
start_heap = gc.mem_free()
array = Array("I", 2 * 1024 * 1024)
gc.collect()
array_cost = start_heap - gc.mem_free()
region = p2.PSRAM().alloc(4096)
block = bytearray(bytes(range(256)) * 16)
output = bytearray(4096)
cases = (
    (alu, 216858),
    (calls, 302400),
    (floating, 256),
    (maps, 4800),
    (parse, 12),
    (collect, 8),
    (raw_transfer, 131072),
    (array_seq, 32640),
    (array_random, 12720),
)
try:
    print("space", start_heap, array_cost, micropython.stack_use())
    for name, (fn, expected) in zip(
        ("alu", "calls", "float", "maps", "parse", "gc", "raw", "sequential", "random"), cases
    ):
        for rep in range(5):
            gc.collect()
            tic = time.ticks_us()
            ans = fn()
            dt = time.ticks_diff(time.ticks_us(), tic)
            assert ans == expected, (name, ans, expected)
            print("sample", name, rep, dt)
finally:
    region.close()
    array.close()
