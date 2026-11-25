# Native interpreter

The C interpreter runs in hub RAM on cog 0 at 160 MHz. An independent
console cog services P62 (TX) and P63 (RX) at 115200 8N1. Ordinary Python
and architecture-independent `.mpy` files execute in the MicroPython
bytecode VM. Build `mpy-cross` from the same v1.29.0 checkout. The Edge
profile uses single-precision floats. Check `sys.implementation._mpy` on
the running image when transferring bytecode.

## Runtime memory

The linker defines lower and upper bounds for the ascending C stack and hub GC
arena. Each call to the recursion checker uses PTRA with a 2048-byte reserve.
The port configures an additional 8192-byte upstream Python stack in hub BSS.
The VM uses it for bytecode call frames, bound-method arguments, and
`mp_local_alloc`. NLR restores its cursor on exceptions and the upstream GC
traces its active range. Exhaustion raises `RuntimeError`. Compiling with
`-Werror=vla` rejects new variable-sized C stack objects. Core source
`py/{objfun.c,objboundmeth.c,pystack.h}` contains the three `alloca` paths
disabled by this configuration.

The P2 entry to `gc_collect` captures all 32 general registers plus PA, PB,
PTRB and the original PTRA before entering C. It visits each possible
four-byte window in the active C stack because local pointers can occupy
unaligned offsets. Registered MicroPython root fields and the Python stack
are traced by `gc_collect_start`. Native drivers must either keep hub data
outside the Python heap or register references for the entire asynchronous
operation. The Edge and lean profiles run one Python thread.

The P2 NLR buffer saves the head of the exception-cleanup chain on entry.
A nonlocal return unwinds to that exact head without comparing stack-local
addresses. This handles the upward stack direction and independent compiler
layout of locals in the same activation.

## REPL and checks

Ctrl-A enters raw mode, Ctrl-B returns to friendly mode, Ctrl-C interrupts
running Python, and Ctrl-D performs a soft reboot. A raw-mode soft reboot
skips user startup scripts for recovery. The upstream raw-paste receiver
advertises flow control to standard `mpremote`. The serial cog detects the
selected interrupt byte and the VM cog delivers the pending exception.

Run from `ports/p2` with the RAM image already loaded:

```console
python -m mpremote connect COM12 exec "import sys,gc; print(sys.implementation,gc.mem_free())"
python -m mpremote connect COM12 run tests/vm.py
```

The stress program reports heap bytes, C stack usage at the sample, 20 GC
pause samples (minimum, median and maximum in microseconds), and time for
a 1000-iteration integer sum. Its pass criteria also include exception
recovery, recursion limits and successful allocation after heap exhaustion.

To exercise exact native GC roots use a separate test build with
`CFLAGS_EXTRA=-DP2_TEST_GC_ROOTS=1`. On every reset it prints a mask
`P2 GC roots: 7/7` on success. Bit 0 indicates survival of an object held
only in r2, bit 1 survival from a four-byte slot at address 1 modulo 4,
and bit 2 reclamation of an unreferenced control object. Firmware without
the flag omits the PASM regression harness.

On the Windows FTDI configuration where reopening COM12 resets the running
RAM image, keep the physical serial handle open with `tools/ram_session.py`
and pass its reported local endpoint to the commands instead of COM12.
With this relay running, the upstream runner uses the same binary stream:

```console
cd tests
python run-tests.py --test-instance port:socket://127.0.0.1:8122 basics/int_divmod.py basics/try_finally1.py
```

## Threaded compute profile

`PROFILE=threaded` builds the standard `_thread` module with one main Python
cog and one worker. A separate console cog continues serving UART. A second
concurrent worker raises `OSError(EBUSY)`. The bytecode interpreter uses a
GIL with ticket ordering; VM checkpoints and millisecond delays give another
runnable thread an opportunity to acquire it. A Python mutex releases the
GIL while waiting. The worker runs standard MicroPython thread entry,
exception and termination paths. Pin, PSRAM, storage and native peripheral
bindings are confined to the Edge and lean profiles to preserve cog-local
electrical ownership. This profile exposes no unrestricted native callback
that executes outside the GIL.

One P2 hardware lock serialises ticket updates for all Python locks. An
idle worker remains available for another task until soft reset. Reset on
the main cog holds the GIL, signals the worker, waits for acknowledgement
outside the ticket guard, and stops its cog before clearing VM memory.

The worker reserves a 16 KiB C stack and a separate, eight-byte-aligned
3072-byte Python stack.
`_thread.stack_size(n)` can request a limit between 8192 and 16384 bytes
for a subsequent worker. Two 16 KiB stack snapshot buffers and two register
snapshots are statically reserved in this profile. At a GIL handoff, the
outgoing thread copies its live native stack and registers before releasing
the lock. Collection traces active bytes of the peer snapshot, including
unaligned slots, and the suspended thread's active Python stack. The Python
stack cannot change while its thread is outside the GIL. Startup arguments stay
in a registered root until thread exit. Autonomous console state contains
no GC pointers.

`tests/threaded.py` checks scheduling, lock acquisition, worker capacity,
and preservation of thread-local buffers while each cog collects. Its JSON
record includes thread identities and wall time for 25 collections.
