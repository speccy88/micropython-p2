"""Prepend ws2812.py and DRIVER_IMAGE = <ws2812.p2d bytes>. Leave P0..P2 open."""

from p2 import SmartPin


def measure():
    strip = globals()["Strip"](globals()["DRIVER_IMAGE"], 0)
    try:
        # P1 and P2 monitor P0 through the adjacent-pad selectors.
        edges = SmartPin(1, SmartPin.COUNT_RISES | (7 << 28))
        try:
            highs = SmartPin(2, SmartPin.HIGH_TICKS | (6 << 28))
            try:
                for word, low, high in ((0, 36, 60), (0xFFFFFF, 93, 112)):
                    start = edges.peek()
                    strip.show([word] * 32)
                    pulses = (edges.peek() - start) & 0xFFFFFFFF
                    assert pulses == 24 * 32, pulses
                    assert highs.ready()
                    ticks = highs.read()
                    assert low <= ticks <= high, ticks
                    print("WS2812 pulse count/high ticks", pulses, ticks)
            finally:
                highs.deinit()
        finally:
            edges.deinit()
    finally:
        strip.close()
    print("P2_WS2812_TIMING_PASS")


measure()
