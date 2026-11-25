# Non-destructive 32 MiB alias/offset check. Standalone raw REPL, no live regions.
from p2 import PSRAM
from time import sleep_ms
ram = PSRAM()
size = ram.capacity()
assert size == 32 << 20
positions = [0, 0x3fd, 0xffd, 0x1ffffd, 0x3ffffd, 0x7ffffd,
             0xfffffd, 0x17ffffd, 0x1bffffd, size - 7]
original = [ram.read(p, 7) for p in positions]
expected = [bytes(((i * 73 + j * 97 + 11) & 255 for j in range(7)))
            for i in range(len(positions))]
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
print("P2_PSRAM_BOUNDARY_PASS", size, len(positions), ram.diagnostics())
