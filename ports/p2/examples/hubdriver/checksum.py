# Copy checksum.p2d next to this script on a mounted filesystem.
# On a raw REPL the host can instead prepend DRIVER_IMAGE = <bytes literal>.
import gc
import p2
import struct
from time import ticks_ms, ticks_diff

try:
    image = DRIVER_IMAGE
except NameError:
    with open("checksum.p2d", "rb") as stream:
        image = stream.read()


def complete(driver, sequence):
    start = ticks_ms()
    while driver.word(2) != sequence:
        if ticks_diff(ticks_ms(), start) >= 250:
            raise RuntimeError("checksum cog did not complete")
    return driver.word(3), driver.word(5)


def rejected(exception, function, *args):
    try:
        function(*args)
    except exception:
        return
    raise AssertionError("expected rejection")


rejected(TypeError, p2.Driver, bytearray(image))
rejected(ValueError, p2.Driver, image[:-1])
corrupted = bytearray(image)
corrupted[-1] ^= 1
rejected(ValueError, p2.Driver, bytes(corrupted))
rejected(OSError, p2.Driver, image, (62,))

driver = p2.Driver(image, pins=(5,))
cog = driver.id()
second = None
requests = 0
try:
    assert p2.pin_owner(5) == "driver"
    rejected(OSError, p2.Driver, image, (5,))
    second = p2.Driver(image)
    assert second.id() != cog
    assert driver.word(0) == second.word(0) == 1
    rejected(ValueError, driver.word, 0, 4)
    rejected(ValueError, driver.word, 64)
    rejected(ValueError, driver.write, 1, b"abcd")
    rejected(ValueError, driver.readinto, 63, bytearray(8))
    del driver
    gc.collect()
    driver = p2.get_driver(cog)
    for sequence in range(1, 33):
        words = [(sequence * 0x01010101 + i * 397) & 0xFFFFFFFF for i in range(58)]
        payload = bytearray(58 * 4 + 1)
        for i, value in enumerate(words):
            struct.pack_into("<I", payload, 1 + 4 * i, value)
        assert driver.write(6, memoryview(payload)[1:]) == 232
        driver.word(4, len(words))
        driver.word(1, sequence)
        # The native cog runs while the VM allocates and traces its heap.
        junk = [bytearray(64) for i in range(8)]
        gc.collect()
        status, result = complete(driver, sequence)
        assert status == 0 and result == sum(words) & 0xFFFFFFFF
        checked = bytearray(5)
        assert driver.readinto(5, memoryview(checked)[1:]) == 4
        assert struct.unpack_from("<I", checked, 1)[0] == result
        requests += 1
    # A second, independently placed copy reports bad counts in its own mailbox.
    second.word(4, 59)
    second.word(1, 1)
    assert complete(second, 1) == (1, 0)
    assert driver.word(3) == 0
finally:
    if second is not None:
        second.stop()
    p2.get_driver(cog).stop()
assert p2.pin_owner(5) == "free"
driver.stop()
rejected(OSError, p2.get_driver, cog)
rejected(OSError, driver.word, 0)
print("P2_HUBDRIVER_PASS", cog, requests, result)
