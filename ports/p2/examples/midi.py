# P6 TX to a 3.3 V-compatible MIDI OUT interface, P7 reserved for UART RX.
from machine import UART
from time import sleep_ms
from p2midi import MidiOut

uart = UART(1, 31250, tx=6, rx=7, timeout=100)
try:
    midi = MidiOut(uart, channel=1)
    for note in (60, 64, 67):
        midi.note_on(note)
        try:
            sleep_ms(180)
        finally:
            midi.note_off(note)
    uart.flush()
finally:
    uart.deinit()
