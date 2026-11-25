# Non-destructive 32 MiB alias/offset check. Standalone raw REPL, no live regions.
from p2 import PSRAM
from time import sleep_ms

ram = PSRAM()
size = ram.capacity()
assert size == 32 << 20
positions = [
    0,
    0x3FD,
    0xFFD,
    0x1FFFFD,
    0x3FFFFD,
    0x7FFFFD,
    0xFFFFFD,
    0x17FFFFD,
    0x1BFFFFD,
    size - 7,
]
original = [ram.read(p, 7) for p in positions]
expected = [bytes(((i * 73 + j * 97 + 11) & 255 for j in range(7))) for i in range(len(positions))]
try:
    for p, value in zip(positions, expected):
        assert ram.write(p, value) == 7
    sleep_ms(100)
    for i in range(len(positions) - 1, -1, -1):
        assert ram.read(positions[i], 7) == expected[i]
finally:
    for p, value in zip(positions, original):
        ram.write(p, value)
assert all(ram.read(p, 7) == value for p, value in zip(positions, original))
region = ram.alloc(32)
saved = region.read(0, 32)
try:
    # Cover all hub staging alignments independently from the external address.
    for lane in range(4):
        src = bytearray((i * 31 + lane for i in range(8)))
        src.extend(b"\xab" * 12)
        dest = bytearray(b"U" * 21)
        for offset in range(4):
            window = memoryview(src)[lane : lane + 16]
            assert region.write(offset, window) == 16
            read_window = memoryview(dest)[lane + 1 : lane + 17]
            assert region.readinto(offset, read_window) == 16
            assert bytes(window) == bytes(read_window)
            assert dest[lane] == 85 and dest[lane + 17] == 85
finally:
    try:
        region.write(0, saved)
    finally:
        region.close()
print("P2_PSRAM_BOUNDARY_PASS", size, len(positions), ram.diagnostics())
