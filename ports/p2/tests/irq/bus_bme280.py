"""Optional physical fixture. Wire only this fixture before running it.

BME280 I2C at 3.3 V, common ground, CSB to VDDIO, SDO to GND (0x76).
P10=SCL, P11=SDA, each pulled up to 3.3 V (typically 4.7 kOhm).
Jumper P0 (IRQ input) and P12 (open-drain fault injection) to P10.
From ports/p2 run: mpremote connect COM12 run tests/irq/bus_bme280.py
Sensor reference: Bosch data sheet BST-BME280-DS002, sections 5 and 6.
"""

from machine import Pin, SoftI2C
import p2
import time


def expect_errno(number, call):
    try:
        call()
    except OSError as exc:
        assert exc.args[0] == number, exc
    else:
        raise AssertionError("expected bus error")


def test_sensor():
    assert all(p2.pin_owner(n) == "free" for n in (0, 10, 11, 12))
    tap = Pin(0, Pin.IN)
    bus = fault = None
    delivery = [0]

    def edge(_pin):
        delivery[0] += 1

    try:
        fault = Pin(12, Pin.OPEN_DRAIN, value=1)
        bus = SoftI2C(scl=10, sda=11, freq=50000, timeout=500)
        assert tap.value() == 1
        assert bus.readfrom_mem(0x76, 0xD0, 1) == b"\x60"
        calibration = bus.readfrom_mem(0x76, 0x88, 24)
        tap.irq(handler=edge, trigger=Pin.IRQ_FALLING)
        for _ in range(4):
            assert bus.readfrom_mem(0x76, 0x88, 24) == calibration
        expect_errno(19, lambda: bus.writeto(0x77, b""))  # ENODEV, other address absent
        fault.off()
        try:
            assert tap.value() == 0
            expect_errno(110, lambda: bus.readfrom(0x76, 1))  # ETIMEDOUT, SCL held low
        finally:
            fault.on()
        assert tap.value() == 1
        assert bus.readfrom_mem(0x76, 0xD0, 1) == b"\x60"
        time.sleep_ms(1)
        assert delivery[0] > 0
        print("I2C repeated START, NACK, SCL timeout and recovery passed", delivery[0])
    finally:
        tap.deinit()
        if fault is not None:
            fault.deinit()
        if bus is not None:
            bus.deinit()


test_sensor()
