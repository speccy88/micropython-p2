# No jumper required. P4 is an undriven ADC input during this test.
import p2
from machine import ADC
from time import ticks_ms, ticks_diff


def reference(source):
    pin = p2.SmartPin(4, source | 0x30, 11)
    try:
        values = []
        for i in range(12):
            start = ticks_ms()
            while not pin.ready():
                if ticks_diff(ticks_ms(), start) > 20:
                    raise RuntimeError("ADC readiness timeout")
            sample = pin.read()
            if i >= 4:
                values.append(sample)
        return sum(values) // len(values)
    finally:
        pin.deinit()


ground = reference(0x100000)
vio = reference(0x108000)
assert 0 <= ground < vio <= 4095 and vio - ground > 100, (ground, vio)
adc = ADC(4)
try:
    values = [adc.read_u16() for i in range(32)]
    assert all(0 <= v <= 65535 for v in values)
finally:
    adc.deinit()
assert p2.pin_owner(4) == "free"
print(
    "P2_ADC_READY_PASS",
    "internal_raw_gnd",
    ground,
    "internal_raw_vio",
    vio,
    "unreferenced_pin_min",
    min(values),
    "unreferenced_pin_max",
    max(values),
)
