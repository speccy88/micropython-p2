# No jumper: P1 and P2 internally observe the P0 pad. Leave P0 unconnected.
from machine import PWM, Pin
from p2 import SmartPin, CLOCK_HZ, pin_owner
from p2signals import Frequency
from time import ticks_diff, ticks_ms, sleep_ms


def measured_high_ticks(sensor):
    start = ticks_ms()
    while not sensor.ready():
        if ticks_diff(ticks_ms(), start) >= 250:
            raise OSError(110)
    return sensor.read()


def run():
    assert pin_owner(0) == pin_owner(1) == pin_owner(2) == "free"
    pwm = PWM(0, freq=1000, duty_u16=16384)
    try:
        for hz, duty in ((1000, 16384), (2000, 49151)):
            pwm.freq(hz)
            pwm.duty_u16(duty)
            sleep_ms(5)
            sensor = Frequency(1, 4, source_pin=0)
            try:
                observed = sensor.read_hz(250)
                assert abs(observed - hz) <= hz // 100
            finally:
                sensor.deinit()
            # Smart pin 2 uses its relative -2 A input (P0).
            high = SmartPin(2, SmartPin.HIGH_TICKS | (6 << 28))
            try:
                measured_high_ticks(high)  # discard a possible initial partial pulse
                clocks = measured_high_ticks(high)
            finally:
                high.deinit()
            expected = (CLOCK_HZ // hz) * duty // 65535
            assert abs(clocks - expected) <= expected // 100 + 8
            print("PWM_CAPTURE", observed, clocks, expected)
    finally:
        pwm.deinit()
    assert pin_owner(0) == pin_owner(1) == pin_owner(2) == "free"
    pin = Pin(0)
    pin.deinit()
    print("P2_PWM_CAPTURE_PASS")


run()
