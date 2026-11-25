# Run through the RAM session's mpremote endpoint. No jumpers required.
import gc
from machine import Pin
from p2 import Cog, PSRAM, SmartPin, pin_owner
from time import ticks_ms, ticks_diff, ticks_us
def rejects(error, call, *args):
    try:
        call(*args)
    except error:
        return
    raise AssertionError(args)

assert pin_owner(40) == "psram" and pin_owner(57) == "psram"
assert pin_owner(58) == "sd" and pin_owner(61) == "sd"
assert pin_owner(62) == "console" and pin_owner(63) == "console"
rejects(OSError, Pin, 57, Pin.OUT)
rejects(ValueError, Pin, 64)
s = SmartPin(0, SmartPin.REPOSITORY, 0)
try:
    s.write_x(0x8321BADC)
    assert s.peek() == 0x8321BADC and s.read() == 0x8321BADC
    rejects(OSError, Pin, 0)
finally:
    s.deinit()
rejects(OSError, s.read)
assert pin_owner(0) == "free"
ram = PSRAM()
assert ram.capacity() == 32 << 20
assert ram.diagnostics()["ids"][0:2] == b"\x0d\x5d"
a = ram.alloc(4097)
cog = Cog(100)
try:
    data = bytearray(513)
    for i in range(len(data)):
        data[i] = (i * 139 + 231) & 255
    a.fill(0, 4097, 0x33)
    a.write(3, data)
    assert a.read(2, 2) == bytes((0x33, data[0]))
    assert a.read(3, len(data)) == data and a.read(516, 1) == b"3"
    a.copy(7, 3, len(data))
    assert a.read(7, len(data)) == data
    a.copy(3, 7, len(data))
    assert a.read(3, len(data)) == data
    assert a.readinto(4097, bytearray()) == 0
    rejects(ValueError, a.read, 4096, 2)
    rejects(ValueError, a.write, -1, b"")
    rejects(OSError, ram.read, 0, 1)
    start = ticks_ms()
    initial = cog.count()
    rounds = 0
    while ticks_diff(ticks_ms(), start) < 5000:
        temp = [bytearray(31 + i) for i in range(12)]
        gc.collect()
        a.write(13, data)
        a.readinto(13, temp[0])
        assert temp[0] == data[:31]
        rounds += 1
        if rounds % 32 == 0:
            print("soak", rounds, cog.count())
    since = ticks_diff(ticks_ms(), start)
    assert rounds > 0 and cog.count() - initial >= since * 8
    start = ticks_us()
    for i in range(8):
        a.write(0, data)
    write_us = ticks_diff(ticks_us(), start)
    start = ticks_us()
    for i in range(8):
        a.readinto(0, data)
    read_us = ticks_diff(ticks_us(), start)
    print("P2_DRIVER_PASS", rounds, since, cog.id(), write_us, read_us, ram.diagnostics())
finally:
    cog.stop()
    a.close()
rejects(OSError, cog.count)
rejects(OSError, a.read, 0, 0)
new = ram.alloc(4097)
new.close()
print("cleanup pass")
