"""Deferred rising-edge counts from a Smart Pin, delivered on the Python VM."""

from machine import Timer
from p2 import SmartPin


class RisingEdges:
    """callback(count) receives all rising edges since the previous delivery."""

    def __init__(self, pin, callback, *, period_ms=10, source_pin=None):
        if not callable(callback) or not isinstance(period_ms, int) or period_ms < 1:
            raise ValueError("expected a callback and positive polling period")
        if source_pin is None:
            source_pin = pin
        delta = source_pin - pin
        if not 0 <= source_pin < 64 or abs(delta) > 3:
            raise ValueError("source pin must be within three pads")
        self._counter = SmartPin(pin, SmartPin.COUNT_RISES | ((delta & 7) << 28))
        try:
            self._last = self._counter.peek()
            self._callback = callback
            self._timer = Timer(period=period_ms, callback=self._poll)
        except BaseException:
            self._counter.deinit()
            raise

    def _poll(self, timer):
        if self._counter is None:
            return
        current = self._counter.peek()
        count = (current - self._last) & 0xFFFFFFFF
        self._last = current
        if count:
            self._callback(count)

    def deinit(self):
        if self._counter is not None:
            self._timer.deinit()
            self._counter.deinit()
            self._counter = None
            self._callback = None
