"""Loaded once into the board's raw REPL. Leave P0 and P1 disconnected."""

import gc
import machine
import micropython
import p2
import time
from machine import Pin


def wait_for(test):
    start = time.ticks_ms()
    while not test():
        if time.ticks_diff(time.ticks_ms(), start) > 750:
            raise RuntimeError("IRQ fixture timed out")
        time.sleep_ms(1)


def drive(mode):
    seq = driver.word(1) + 1
    driver.word(4, mode)
    driver.word(1, seq)
    wait_for(lambda: driver.word(2) == seq)


def expect_error(fun, *args, **kwargs):
    try:
        fun(*args, **kwargs)
    except (TypeError, ValueError, OSError) as exc:
        return exc
    raise AssertionError("invalid operation succeeded")


def setup():
    global driver, pin
    assert p2.pin_owner(0) == "free"
    pin = Pin(0, Pin.IN)
    # The native stimulus is an independent electrical source on the same
    # otherwise disconnected pad. Cog0's DIR stays low throughout the test.
    driver = p2.Driver(globals()["IRQ_STIMULUS"])
    drive(0)


def cleanup():
    pin.deinit()
    driver.stop()
    assert p2.pin_owner(0) == "free"


def edges():
    other = Pin(1, Pin.IN)
    hits, latency = [], []
    try:
        for mode in (Pin.IRQ_RISING, Pin.IRQ_FALLING, Pin.IRQ_RISING | Pin.IRQ_FALLING):
            up = mode != Pin.IRQ_FALLING
            drive(int(not up))

            def callback(obj):
                ct = p2.cycles()
                hits.append((obj is pin, obj.irq().info(), ct))

            handle = pin.irq(handler=callback, trigger=mode)
            assert pin.irq() is handle and handle.info() is None
            err = expect_error(other.irq, handler=callback)
            assert isinstance(err, OSError) and err.args[0] == 16
            for kw in (
                {"hard": True},
                {"trigger": 0},
                {"trigger": 4},
                {"priority": 2},
                {"wake": 1},
            ):
                expect_error(pin.irq, handler=callback, **kw)
                assert pin.irq() is handle
            hits.clear()
            gc.collect()
            for j in range(4):
                drive(int(up))
                wait_for(lambda: len(hits) == 1)
                same, info, callback_ct = hits.pop()
                assert same and info[0] == mode and info[1] == int(up), (mode, info)
                stamp = driver.word(5)
                latency.append(
                    ((info[2] - stamp) & 0xFFFFFFFF, (callback_ct - stamp) & 0xFFFFFFFF)
                )
                if mode == Pin.IRQ_RISING | Pin.IRQ_FALLING:
                    up = not up
                else:
                    drive(int(not up))
                    time.sleep_ms(2)
                    assert not hits
            pin.irq(handler=None)
            assert pin.irq() is None
    finally:
        other.deinit()
    # Cycle deltas measured from the stimulus cog's pre-drive GETCT. These
    # include the fixture's mode compare, pad propagation and ISR prologue.
    print("IRQ_LATENCY_CT", latency)


def roots():
    global pin
    drive(0)
    hits = []

    def install():
        pin.irq(handler=lambda obj: hits.append(obj), trigger=Pin.IRQ_RISING)

    install()
    del pin
    gc.collect()
    drive(1)
    wait_for(lambda: len(hits) == 1)
    pin = hits.pop()
    pin.irq(handler=None)
    print("IRQ_ROOTS_PASS")


def reentry():
    test = Pin(1, Pin.IN)
    test.irq(handler=lambda _: None)

    class Closing:
        def __bool__(self):
            test.deinit()
            return False

    err = expect_error(test.irq, handler=lambda _: None, hard=Closing())
    assert isinstance(err, OSError) and err.args[0] == 19, err
    assert p2.pin_owner(1) == "free"
    test = Pin(1, Pin.IN)
    try:
        assert test.irq() is None
    finally:
        test.deinit()
    print("IRQ_REENTRY_PASS")


def masking():
    drive(0)
    seen = []
    pin.irq(handler=lambda obj: seen.append(obj), trigger=Pin.IRQ_RISING)
    ram = p2.PSRAM().alloc(128) if hasattr(p2, "PSRAM") else None
    outer = machine.disable_irq()
    try:
        inner = machine.disable_irq()
        try:
            drive(1)
            if ram:
                data = bytearray(range(32))
                ram.write(3, data)
                assert ram.read(3, len(data)) == data
                expect_error(ram.read, 127, 2)
        finally:
            machine.enable_irq(inner)
        time.sleep_ms(2)
        assert not seen, "inner restore or PSRAM unmasked the outer section"
    finally:
        machine.enable_irq(outer)
        if ram:
            ram.close()
    wait_for(lambda: len(seen) == 1)
    pin.irq(handler=None)
    print("IRQ_NESTED_PASS", ram is not None)


def queue():
    global pin
    drive(0)
    old, new, results = [], [], []
    pin.irq(handler=lambda obj: old.append(obj), trigger=Pin.IRQ_RISING)

    def replace(_):
        # Inside a scheduled callable the scheduler is locked. Native IRQ
        # polling still runs, but the old queued wrapper cannot dispatch yet.
        global pin
        drive(1)
        time.sleep_ms(2)
        pin.deinit()
        pin = Pin(0, Pin.IN)
        pin.irq(handler=lambda obj: new.append(obj), trigger=Pin.IRQ_RISING)
        results.append(1)

    micropython.schedule(replace, None)
    wait_for(lambda: results)
    time.sleep_ms(3)
    assert not old and not new
    drive(0)

    def noop(_):
        pass

    def fill(_):
        count = 0
        while True:
            try:
                micropython.schedule(noop, None)
            except RuntimeError:
                break
            count += 1
        drive(1)
        time.sleep_ms(2)
        results.append(count)

    micropython.schedule(fill, None)
    wait_for(lambda: len(new) == 1)
    assert results[1] > 0 and new[0] is pin
    pin.irq(handler=None)
    print("IRQ_QUEUE_PASS", results[1])


def loaded_latency():
    callbacks = []
    ram = p2.PSRAM().alloc(4096) if hasattr(p2, "PSRAM") else None
    data = bytes(range(256)) * 16

    def callback(obj):
        ct = p2.cycles()
        callbacks.append((obj.irq().info()[2], ct))

    def sample(name, fn, args):
        measurements = []
        for delay in (64000, 80000, 96000):
            drive(0)
            callbacks.clear()
            driver.word(6, delay)
            driver.word(4, 4)
            seq = driver.word(1) + 1
            driver.word(1, seq)
            start = p2.cycles()
            result = fn(*args)
            finish = p2.cycles()
            wait_for(lambda: callbacks)
            edge = driver.word(5)
            duration = (finish - start) & 0xFFFFFFFF
            assert (edge - start) & 0xFFFFFFFF < duration, (name, duration, delay)
            stamp, user = callbacks[0]
            measurements.append(
                (duration, (stamp - edge) & 0xFFFFFFFF, (user - edge) & 0xFFFFFFFF)
            )
        print("IRQ_WORKLOAD_CT", name, measurements)
        return result

    drive(0)
    pin.irq(handler=callback, trigger=Pin.IRQ_RISING)
    try:
        sample("gc", gc.collect, ())
        assert sample("sum", sum, (range(3000),)) == 4498500
        if ram:
            assert sample("psram_write", ram.write, (0, data)) == len(data)
            assert ram.read(0, len(data)) == data
            print("PSRAM_MAX_CS_CT", ram.diagnostics()["max_cycles"])
    finally:
        pin.irq(handler=None)
        if ram:
            ram.close()


def i2c_timeout():
    # The master releases SCL for START and STOP. Another cog supplies a
    # known SCL input level for this test of clock-stretch timeout/recovery.
    # The firmware never drives SCL low during these two specific operations.
    drive(0)
    seen = []
    bus = machine.SoftI2C(scl=10, sda=11, timeout=3000)
    try:
        pin.irq(handler=lambda p: seen.append(p.irq().info()[2]), trigger=Pin.IRQ_RISING)
        drive(5)
        driver.word(6, 64000)
        driver.word(4, 4)
        driver.word(1, driver.word(1) + 1)
        start = p2.cycles()
        err = expect_error(bus.start)
        finish = p2.cycles()
        assert isinstance(err, OSError) and err.args[0] == 110, err
        wait_for(lambda: seen)
        elapsed = (finish - start) & 0xFFFFFFFF
        assert ((seen[0] - start) & 0xFFFFFFFF) < elapsed
        drive(6)
        bus.start()
        bus.stop()
        print("I2C_HELD_SCL_CT", elapsed)
    finally:
        drive(7)
        bus.deinit()
        pin.irq(handler=None)


def callback_lifecycle():
    drive(0)
    seen = []

    def fail_once(obj):
        seen.append(obj)
        if len(seen) == 1:
            raise RuntimeError("irq_expected_exception")
        obj.deinit()

    pin.irq(handler=fail_once, trigger=Pin.IRQ_RISING)
    drive(1)
    wait_for(lambda: len(seen) == 1)
    drive(0)
    drive(1)
    wait_for(lambda: len(seen) == 2)
    assert p2.pin_owner(0) == "free"
    print("IRQ_CALLBACK_PASS")


def storm():
    global storm_calls
    storm_calls = 0

    def on_edge(_):
        global storm_calls
        storm_calls += 1

    drive(0)
    pin.irq(handler=on_edge, trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING)
    drive(2)
    wait_for(lambda: storm_calls > 0)
