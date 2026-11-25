"""Overwrite and verify a fresh, full-capacity volatile PSRAM allocation."""
import struct
import time
from p2 import PSRAM


def tag(tile, offset):
    # Address tags within each transfer distinguish identical offsets in
    # different chips, even when the bulk of a tile is copied correctly.
    for pos in range(0, len(tile), 1024):
        struct.pack_into("<I", tile, pos, offset + pos)
    struct.pack_into("<I", tile, len(tile) - 4, offset + len(tile) - 1)


def run():
    ram = PSRAM()
    size = ram.capacity()
    assert size == 32 << 20
    block = 4096
    expected = bytearray(block)
    observed = bytearray(block)
    # A maximal-period 16-bit LFSR gives adjacent addresses different data
    # throughout each tile. Generate the pattern once to keep Python overhead low.
    state = 0xACE1
    for i in range(block):
        state = (state >> 1) ^ (0xB400 if state & 1 else 0)
        expected[i] = state & 255
    region = ram.alloc(size)
    try:
        assert region.capacity() == size
        start = time.ticks_ms()
        for offset in range(0, size, block):
            tag(expected, offset)
            assert region.write(offset, expected) == block
        written = time.ticks_ms()
        print("P2_PSRAM_FULL_WRITTEN", size, "write_ms", time.ticks_diff(written, start))
        for offset in range(0, size, block):
            tag(expected, offset)
            assert region.readinto(offset, observed) == block
            if observed != expected:
                for i in range(block):
                    if observed[i] != expected[i]:
                        raise AssertionError((offset + i, expected[i], observed[i]))
            if offset == 0:
                first = bytes(observed[:8]).hex()
        end = time.ticks_ms()
        print("P2_PSRAM_FULL_PASS", "bytes", size, "tile_bytes", block, "tiles", size // block,
              "first8", first, "last8", bytes(observed[-8:]).hex(),
              "write_ms", time.ticks_diff(written, start), "read_ms", time.ticks_diff(end, written),
              "elapsed_ms", time.ticks_diff(end, start))
    finally:
        region.close()


run()
