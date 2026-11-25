# Store and check a 1 MiB synthetic signal with a 512-byte hub staging buffer.
from p2 import PSRAM
ram = PSRAM()
tile = bytearray(512)
region = ram.alloc(1024 * 1024)
try:
    for pos in range(0, region.capacity(), len(tile)):
        index = pos // len(tile)
        tile[0], tile[1], tile[-1] = index >> 8, index & 255, (index ^ 255) & 255
        region.write(pos, tile)
    for pos in range(0, region.capacity(), len(tile)):
        index = pos // len(tile)
        region.readinto(pos, tile)
        assert tile[0] == index >> 8 and tile[1] == index & 255 and tile[-1] == (index ^ 255) & 255
    print("verified", region.capacity(), "external bytes")
finally:
    region.close()
