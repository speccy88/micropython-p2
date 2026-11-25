"""Run from irq/run.py on an Edge with P0, P8 and P9 physically unconnected."""

import machine
import p2
import time


def spi_capture(active):
    assert all(p2.pin_owner(p) == "free" for p in (0, 8, 9))
    irq_pin = machine.Pin(0, machine.Pin.IN)
    spi = probe = None

    def ready(value):
        start = time.ticks_ms()
        while probe.word(2) != value:
            if time.ticks_diff(time.ticks_ms(), start) > 300:
                raise RuntimeError("SPI observer timeout")

    try:
        spi = machine.SoftSPI(baudrate=25000, sck=8, mosi=9, miso=9)
        probe = p2.Driver(globals()["BUS_PROBE"])
        callbacks = []
        if active:
            irq_pin.irq(
                handler=lambda p: callbacks.append(p.irq().info()[2]), trigger=irq_pin.IRQ_RISING
            )
        request = 2 if active else 1
        probe.word(1, request)
        ready(request)
        rx = bytearray(2)
        spi.write_readinto(b"\xaa\xaa", rx)
        assert rx == b"\xaa\xaa"
        probe.word(1, 3)
        ready(3)
        count = probe.word(3)
        assert 32 < count < 64, ("SPI capture length", count)
        t0 = probe.word(4)
        log = [
            ((probe.word(4 + 2 * i) - t0) & 0xFFFFFFFF, probe.word(5 + 2 * i))
            for i in range(count)
        ]
        return log, [((ct - t0) & 0xFFFFFFFF) for ct in callbacks]
    finally:
        irq_pin.deinit()
        if probe is not None:
            probe.stop()
        if spi is not None:
            spi.deinit()


def spi_measure(active):
    log, callbacks = spi_capture(active)
    assert log[0] == (0, 0)
    changes, edges, bits = [], [], []
    for (prev_ct, prev), (ct, state) in zip(log, log[1:]):
        assert ct > prev_ct
        if (state ^ prev) & 2:
            changes.append(ct)
        if (state ^ prev) & 1:
            assert state & 1 == int(len(edges) % 2 == 0)
            edges.append(ct)
            if state & 1:
                bits.append(state >> 1)
    assert bits == [1, 0] * 8 and len(edges) == 32 and len(changes) == 16
    # Every data transition must precede its corresponding rising edge.
    setup = [edge - changed for edge, changed in zip(edges[::2], changes)]
    hold = [changed - edge for changed, edge in zip(changes[1:], edges[::2])]
    widths = [b - a for a, b in zip(edges, edges[1:])]
    # Sampling tolerance of 400 CT ticks relative to the requested 3200-tick
    # half-period. This checks a mode-0 digital waveform at the default clock.
    assert min(setup + hold + widths) >= 2800, (setup, hold, widths)
    if active:
        assert len(callbacks) == 1 and edges[0] <= callbacks[0] < edges[-1], callbacks
    else:
        assert not callbacks
    print(
        "SPI_CT",
        "IRQ" if active else "CONTROL",
        "high/low/setup/hold min/max",
        [(min(a), max(a)) for a in (widths[::2], widths[1::2], setup, hold)],
    )


for active_trial in (False, True, False, True):
    spi_measure(active_trial)
