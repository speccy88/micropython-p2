"""MIDI 1.0 channel messages over a caller-owned 31250-baud UART."""


class MidiOut:
    def __init__(self, uart, channel=1):
        if not isinstance(channel, int) or not 1 <= channel <= 16:
            raise ValueError("channel must be 1..16")
        self._uart = uart
        self._channel = channel - 1

    def _send(self, command, a, b):
        if (
            not isinstance(a, int)
            or not 0 <= a <= 127
            or not isinstance(b, int)
            or not 0 <= b <= 127
        ):
            raise ValueError("MIDI data must be 0..127")
        data = bytes((command | self._channel, a, b))
        if self._uart.write(data) != 3:
            raise OSError("incomplete MIDI message")

    def note_on(self, note, velocity=100):
        self._send(0x90, note, velocity)

    def note_off(self, note, velocity=0):
        self._send(0x80, note, velocity)

    def control(self, controller, value):
        self._send(0xB0, controller, value)
