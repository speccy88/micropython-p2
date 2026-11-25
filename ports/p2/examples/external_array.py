# 8 MiB typed data, full-extent bulk write/read plus widely spaced dirty evictions.
# Run with mpremote run. No wires. Reads every byte from external RAM.
import gc
import struct
from time import ticks_us, ticks_diff
from p2array import Array

def run():
    gc.collect()
    initial = gc.mem_free()
    words = 2 * 1024 * 1024
    a = Array("I", words, pages=2, page_bytes=256, zero=False)
    try:
        chunk = bytearray(2048)
        expected = bytearray(len(chunk))
        tile_words = len(chunk) // a.itemsize
        for i in range(tile_words):
            struct.pack_into("<I", expected, i * 4, (i * 0x1010101) & 0xffffffff)
        low = gc.mem_free()
        start = ticks_us()
        # Each tile has a distinctive index sentinel on both ends.
        for pos in range(0, words, tile_words):
            struct.pack_into("<I", expected, 0, pos)
            struct.pack_into("<I", expected, len(expected) - 4, pos ^ 0xABCDEF01)
            a.writefrom(pos, expected)
            if pos % (tile_words * 128) == 0:
                low = min(low, gc.mem_free())
                gc.collect()
        write_us = ticks_diff(ticks_us(), start)

        start = ticks_us()
        for pos in range(0, words, tile_words):
            struct.pack_into("<I", expected, 0, pos)
            struct.pack_into("<I", expected, len(expected) - 4, pos ^ 0xABCDEF01)
            assert a.readinto(pos, chunk) == tile_words
            assert chunk == expected
            if pos % (tile_words * 128) == 0:
                low = min(low, gc.mem_free())
                gc.collect()
        read_us = ticks_diff(ticks_us(), start)

        start = ticks_us()
        # 512 distinct, widely spaced pages force write-back eviction.
        for j in range(512):
            index = ((j * 137) % 512) * 4096 + 1
            a[index] = 0xE0000000 + j
        a.flush()
        for j in range(511, -1, -1):
            index = ((j * 137) % 512) * 4096 + 1
            assert a[index] == 0xE0000000 + j
        random_us = ticks_diff(ticks_us(), start)
        low = min(low, gc.mem_free())
        gc.collect()
        print("P2_EXT_ARRAY_PASS", "bytes", words * a.itemsize, "cache", a.cache_bytes(),
              "initial_free", initial, "live_hub_delta", initial - gc.mem_free(),
              "observed_peak_hub_delta", initial - low, "write_us", write_us,
              "read_us", read_us, "random_us", random_us)
    finally:
        a.close()
run()
