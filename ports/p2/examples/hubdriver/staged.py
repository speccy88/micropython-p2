"""Run trusted, position-independent native services staged in PSRAM, one at a time."""

import gc
import p2
import time


def run_stage(region, offset, length, pins, operation):
    """Load only the selected image into hub RAM; stop it even if the client raises."""
    if not 24 < length <= 4120:
        raise ValueError("invalid P2D1 length")
    start = time.ticks_us()
    driver = p2.Driver(region.read(offset, length), pins=pins)
    try:
        load_us = time.ticks_diff(time.ticks_us(), start)
        gc.collect()  # Release the temporary hub copy used by the P2D1 loader.
        return operation(driver), load_us, gc.mem_free()
    finally:
        driver.stop()


def checksum(driver):
    driver.word(4, 2)
    driver.word(6, 21)
    driver.word(7, 34)
    driver.word(1, 1)
    start = time.ticks_ms()
    while driver.word(2) != 1:
        if time.ticks_diff(time.ticks_ms(), start) > 100:
            raise OSError(110)
    assert driver.word(3) == 0 and driver.word(5) == 55
    return driver.id()


def inspect(driver):
    # The pixel service publishes ready without driving a pin. A program
    # that needs a strip would claim a pin and publish a frame here.
    assert driver.word(0) == 1 and driver.word(2) == 0
    return driver.id()


def exercise(region, first_size, second_size):
    gc.collect()
    initial = gc.mem_free()
    for _ in range(3):
        a = run_stage(region, 0, first_size, (), checksum)
        b = run_stage(region, first_size, second_size, (), inspect)
        assert a[0] == b[0]
        print("staged_native", first_size, a[1], a[2], second_size, b[1], b[2])
    del a, b
    gc.collect()
    print("P2_NATIVE_STAGE_PASS", initial, gc.mem_free())


def from_files():
    import os

    names = ("checksum.p2d", "ws2812.p2d")
    sizes = [os.stat(path)[6] for path in names]
    region = p2.PSRAM().alloc(sum(sizes))
    try:
        offset = 0
        for path in names:
            with open(path, "rb") as f:
                while True:
                    block = f.read(256)
                    if not block:
                        break
                    region.write(offset, block)
                    offset += len(block)
        exercise(region, *sizes)
    finally:
        region.close()


if __name__ == "__main__":
    from_files()
