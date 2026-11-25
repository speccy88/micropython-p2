"""Fixed-clock Edge PSRAM benchmark. Only writes newly allocated regions."""

import gc
import micropython
import time

from p2 import PSRAM
from p2array import Array


def run():
    src = bytearray(4096)
    dst = bytearray(4096)
    for i in range(len(src)):
        src[i] = (i * 37 + (i >> 8)) & 255
    region = PSRAM().alloc(len(src))
    gc.collect()
    before = gc.mem_free()
    arr = Array("I", 2 << 20, zero=False)
    gc.collect()
    print("array_retained_hub_bytes", before - gc.mem_free(), "cache_bytes", arr.cache_bytes())
    try:
        for repeat in range(5):
            gc.collect()
            t = time.ticks_us()
            for _ in range(16):
                region.write(0, src)
            write = time.ticks_diff(time.ticks_us(), t)
            t = time.ticks_us()
            for _ in range(16):
                region.readinto(0, dst)
            read = time.ticks_diff(time.ticks_us(), t)
            assert src == dst
            t = time.ticks_us()
            for i in range(1024):
                arr[i] = i
            total = 0
            for i in range(1024):
                total += arr[i]
            assert total == 523776
            scalar = time.ticks_diff(time.ticks_us(), t)
            print(
                "psram_us",
                repeat,
                write,
                read,
                scalar,
                "stack",
                micropython.stack_use(),
                "max_cycles",
                region.diagnostics()["max_cycles"],
            )
    finally:
        arr.close()
        region.close()


run()
