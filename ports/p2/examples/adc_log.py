from machine import ADC
from p2 import PSRAM
from time import sleep_ms
adc = ADC(4)
try:
    samples = PSRAM().alloc(2000)
    try:
        record = bytearray(2)
        for i in range(1000):
            value = adc.read_u16()
            record[0], record[1] = value & 255, value >> 8
            samples.write(2 * i, record)
            sleep_ms(1)
        print("first eight little-endian samples", samples.read(0, 16))
    finally:
        samples.close()
finally:
    adc.deinit()
