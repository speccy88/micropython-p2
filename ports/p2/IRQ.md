# Pin interrupts on the Propeller 2

The optional IRQ build lets an ordinary input pin wake a Python callback on an edge. Cog 0 captures the event in hardware and the VM calls your function when it can safely run Python. One pin can own the registration at a time. The feature uses INT1 and SE1 on the primary cog and requires no service cog.

## Try it

Start with the port's prepared LLVM 15 toolchain. From the repository root in Linux or WSL, build the Edge profile in its own output directory. The same command with `lean` builds for the plain Edge. The default builds have `P2_ENABLE_HW_IRQ=0`. The threaded build rejects `P2_ENABLE_HW_IRQ=1`. [Toolchain setup](toolchain/README.md)

```sh
export P2_WORK="$HOME/tinygo-p2-work"
export P2_BIN="$HOME/p2-micropython-toolchain/build/bin"
P2_ENABLE_HW_IRQ=1 BUILD_ROOT="$PWD/ports/p2/build-irq" bash ports/p2/tools/build_profiles.sh edge
```

On the machine with the USB cable, load the resulting binary into RAM. Use the actual path to your binary and serial device. For example, run these commands in separate terminals from the repository root, using a Python environment with `mpremote` and `pyserial` installed.

```sh
python ports/p2/tools/ram_session.py ports/p2/build-irq/edge/firmware.bin --port COM12
mpremote connect socket://127.0.0.1:8122 repl
```

For a simple button, use a free P0 with a normally open switch between P0 and 3.3 V through a 1 kΩ series resistor. The pin's weak pull-down holds it low with the switch open. Run this at the REPL, press the button a few times, then press Ctrl-C to release the pin.

```python
from machine import Pin
from time import sleep_ms

button = Pin(0, Pin.IN, Pin.PULL_DOWN)

def pressed(pin):
    print("button pressed", pin.irq().info())

try:
    button.irq(handler=pressed, trigger=Pin.IRQ_RISING, hard=False)
    while True:
        sleep_ms(100)
finally:
    button.deinit()
```

A mechanical switch may bounce. This example can report several presses per actuation. For precise pulse counting or capture, use a Smart Pin configured for that task. [Smart Pin examples](drivers/README.md)

## Registration and delivery

| Operation | Result |
| --- | --- |
| `p.irq(handler=f, trigger=edges)` | Installs or replaces this pin's registration and returns a handle. The VM calls `f(p)` with the same live `Pin` object. The default trigger is both edges. |
| `p.irq()` | Returns the current handle or `None` on a live input. It leaves the configuration in place. |
| `p.irq(handler=None)` | Cancels this pin's registration and queued delivery. The pin remains yours. |
| `p.deinit()` | Stops interrupt production, invalidates the handle for future delivery and releases the pad. |
| `handle.info()` | Returns `None` before the first dispatch, then `(trigger, level, service_ct)` from its latest dispatch. A detached handle keeps its last sample. |

Use `Pin.IRQ_RISING`, `Pin.IRQ_FALLING`, or their bitwise OR. Supported pins are live `machine.Pin` objects configured as `Pin.IN`, subject to the board's usual reservations. Selecting another live input while the slot is occupied raises `OSError(EBUSY)`. A released input raises `OSError(ENODEV)`. Invalid triggers, output/open-drain modes and `hard=True` raise `ValueError`. Priority and wake keywords are unsupported and raise `TypeError`. Smart Pins run separate hardware protocols and keep ownership of their completion signals.

The native handler disconnects its source on entry, samples the cycle counter and the pin level, then publishes one complete record. An edge burst can coalesce before service. During the waiting period more edges can pass without a second record. The VM tries to enqueue that record at its next poll. A full scheduler queue leaves it pending and the source disarmed. When the scheduler dispatches this binding, the trampoline copies the sample, clears stale source state, rearms, and calls Python. Once rearmed, one new event can wait during the callback. Callback exceptions follow the usual scheduled-exception reporting and the binding stays usable.

`trigger` identifies the configured edge mask. `level` is a sample taken during service. In both-edge mode, intervening transitions can change that level before the sample. `service_ct` is the low 32 bits of `GETCT` at service time and wraps every 26.84 seconds at 160 MHz. For a short interval across wrap, calculate `(end - start) & 0xffffffff`. The interface supplies neither an electrical edge timestamp nor a lost-edge count.

The VM roots the binding, its callback and its pin through GC. Each reconfiguration gets a fresh binding identity. A queued stale binding can only discard its delivery. The callback may disable, deinitialise, or replace its pin. On both raw and friendly soft reset the VM invalidates the active binding before running finalisers, rejects new registrations during teardown, and restores the primary cog's entry interrupt-mask state for the next VM.

## Masking and timing

`machine.disable_irq()` returns an opaque token for the previous hardware mask state. Restore that exact token in a `finally` block, in reverse nesting order, on the same cog. This masks native interrupt service on the current cog only. Other cogs, the scheduler, pending Python callbacks, and Ctrl-C retain their own behavior. Keep masked work short.

```python
import machine

state = machine.disable_irq()
try:
    # A few bounded operations on state shared with a native source.
    pass
finally:
    machine.enable_irq(state)
```

An electrical transition, native service, and Python callback are three different times. Interrupt masking, hardware-instruction interruptibility (including WAIT/REP regions), and the time to enter the ISR affect native service. GC, long C calls, borrowed-buffer operations and other scheduled work can delay Python further. Software-clocked SPI and I²C edges can stretch while the ISR executes. Use the observed timings for the tested workload when assessing a peripheral's tolerance. [Validation records](validation/IRQ.md)

## Native contract

The linker retains the aligned PASM2 instruction blob in the HUB image. Installation copies it into cog 0 at `$080` and points `IJMP1` there. The linker caps the reservation at `$09f`. The memory-copy routines keep their `$000–$07f` scratch region, LLVM registers begin at `$1d0`, and the LUT keeps its normal contents. Treat INT1, SE1 and the reserved cog words as private to this facility when integrating other cog-0 code.

Port-native C clients can reserve the INT1/SE1 pair under the cog mask with `p2_irq_pair_claim(owner, NULL)`. Supply a unique non-null owner address whose lifetime covers the claim. Check the boolean result before writing any event register. The current owner can hand off both resources with `p2_irq_pair_claim(next, owner)`, or stop and release them with `p2_irq_pair_release(owner)`. A token mismatch leaves the hardware and active registration intact. Soft reset releases the pair even for a native owner. The deferred Python binding uses these same operations.

The straight-line stub fits in 19 COG longs. It touches only r31, makes seven absolute HUB accesses and uses `RETI1` to restore the interrupted PC and flags. Six aligned HUB words (24 bytes) hold its scratch and notification state. Ordinary `GETCT` preserves the foreground's timestamp latch. The stub leaves PTRA/PTRB, PA/PB, the call stack, FIFO, Q state and CORDIC intact. Build-time verification examines the installation routine, linked instructions, relocations and CORDIC sequences. The design adapts register preservation from TinyGo/P2. [PASM2 implementation](irq_p2.S) · [Post-link checker](tests/check_irq_asm.py) · [TinyGo/P2 runtime](https://github.com/speccy88/tinygo-p2/blob/fc631f268080135e7c13ad27783ee6e1bb6a1c35/modern/overlays/tinygo/src/runtime/gc_p2.S) · [TinyGo/P2 assembly checks](https://github.com/speccy88/tinygo-p2/blob/fc631f268080135e7c13ad27783ee6e1bb6a1c35/modern/hil/check_runtime_asm.py)

Disarming disconnects INT1 using `SETINT1 #0`. Rearming clears the separate IRQ latch with `NIXINT1`, configures the pin edge and resets its event flag with `SETSE1`, then connects SE1 to INT1 using `SETINT1 #4`. The VM bridge only enqueues from the poll hook. Borrowed-buffer loops retain their exception-only checks while Python delivery waits for safe dispatch. [P2 silicon documentation](https://p2docs.github.io/mirror/p2silicon.html)

Native callers use `p2_irq_save()` and `p2_irq_restore(state)`. Save reads the current STALLI bit using `GETBRK WCZ` before stalling interrupts. Restore reinstates the captured hardware setting. These out-of-line calls form compiler memory barriers. IRQ-enabled PSRAM uses bounded transaction guards. [Native API](irq_native.h) · [PSRAM transactions](drivers/psram.c)

## Repeat the board test

Disconnect the button and all external drives from P0 and P1. The fixture assigns a separate cog to drive P0 while cog 0 sees it as an ordinary input. This exercises the physical input on the same chip without a jumper. With the RAM relay still open and the REPL client disconnected, run the following command.

```sh
python ports/p2/tests/irq/run.py --port socket://127.0.0.1:8122 --image ports/p2/build-irq/edge/firmware.bin --output irq-result.json
```

The report includes the supplied image hash, fixture hashes, per-check output and reset/interrupt results. For the Edge bus and read-only media checks, also leave the bus-test pads free and add `--io`. The fixture includes local loopbacks. External target timing, setup/hold margins and clock-stretch waveforms require an actual peripheral and a logic analyzer. [IRQ fixture](tests/irq/device.py) · [Bus pin assignments](tests/bus/loopback.py) · [Per-image results and outstanding checks](validation/IRQ.md)
