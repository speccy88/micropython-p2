"""Read-only JEDEC, partition geometry and repeatability check; no formatting."""
import p2

device_id = p2.Flash.probe()
print("flash JEDEC", hex(device_id))
assert device_id in (0xEF4018, 0xEF7018)
flash = p2.Flash()
try:
    count = flash.ioctl(4, 0)
    size = flash.ioctl(5, 0)
    assert (count, size) == (256, 4096)
    assert p2.pin_owner(60) == "flash"
    first = bytearray(32)
    again = bytearray(32)
    for sector in (0, 1, count - 1):
        assert flash.readblocks(sector, first, 17) == 0
        assert flash.readblocks(sector, again, 17) == 0
        assert first == again
    print("flash geometry", count, size, "repeat reads OK")
finally:
    flash.deinit()
