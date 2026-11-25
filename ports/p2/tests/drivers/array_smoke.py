# Hardware test for actual external reads, dirty eviction and region lifetime.
from p2 import PSRAM
from p2array import Array

region = PSRAM().alloc(132)
try:
    a = Array("I", 33, region=region, pages=1, page_bytes=32, zero=True)
    try:
        for i in range(33):
            a[i] = 0xF1234000 + i
        for i in range(32, -1, -1):
            assert a[i] == 0xF1234000 + i
        a[1] = 0x12345678
        staged = bytearray(4)
        assert a.readinto(1, staged) == 1 and staged == b"\x78\x56\x34\x12"
        assert a.writefrom(1, b"\x44\x33\x22\x11") == 1
        assert a[1] == 0x11223344
        a[-1] = 0xA5A5A5A5
        a.flush()
        try:
            a[33] = 4
            raise AssertionError("missing index error")
        except IndexError:
            pass
    finally:
        a.close()
    assert region.read(128, 4) == b"\xa5" * 4
finally:
    region.close()
print("P2_ARRAY_SMOKE_PASS")
