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

### Interpreting the early SD directory count

The early image printed 34 entries and a set length of 34 for the SD root.
Its compiler generated an incorrect branch in `mp_set_lookup`. Each
insertion skipped the equality check at the string's home slot, overwrote
that slot and incremented the set's size. Repeated strings therefore
inflated `len(set(names))`. The corrected compiler keeps the slot
comparison and conditional branch together. On COM12 the same string
inserted 34 times gave a reported length of 34 and one iterable member on
the early image. The release returned one for both measurements. Both
images read matching SHA-256 values from the five compared SD sectors.
[Historical control](validation/fat-historical-control.json)

On the release image an independent host parser decoded 34 FAT entries
in the three root-directory sectors and found four distinct short names.
String and byte directory listings from the VM matched all 34 decoded
names in order. Pairwise comparisons, the Python set and a host comparison
also agreed on four distinct names. This establishes what the board
returned from those sectors. Determining when duplicate entries appeared
requires a separate history of the medium.
[Read-only directory analysis](validation/fat-directory.json)

On a fresh PSRAM FAT volume the release recovered all 40 separately
created filenames, including uppercase 8.3, lowercase and long names,
and verified each file's distinct contents. [PSRAM FAT check](validation/extended-memory-media.json)

## REPL and checks

Ctrl-A enters raw mode, Ctrl-B returns to friendly mode, Ctrl-C interrupts
running Python, and Ctrl-D performs a soft reboot. A raw-mode soft reboot
skips user startup scripts for recovery. The upstream raw-paste receiver
advertises flow control to standard `mpremote`. The serial cog detects the
selected interrupt byte and the VM cog delivers the pending exception.

On Edge soft reset, the port first rejects new pin, cog and bus claims. A
selective finaliser pass closes native FAT and LittleFS streams while their
devices and Python block adapters are still available. The port then syncs
mounted FAT volumes and unmounts native filesystems. Once user finalisers
finish, the port releases storage and stops any remaining drivers immediately
before the collector frees hub objects. An I/O failure during cleanup is printed on the
console. Ordinary garbage collection keeps upstream finaliser semantics.
`tests/reset_files.py` checks this order using only fresh volatile PSRAM
volumes, including unclosed files with buffered data.

Run from `ports/p2` with the RAM image already loaded:

```console
python -m mpremote connect COM12 exec "import sys,gc; print(sys.implementation,gc.mem_free())"
python -m mpremote connect COM12 run tests/vm.py
```

The stress program reports heap bytes, C stack usage at the sample, 20 GC
pause samples (minimum, median and maximum in microseconds), and time for
a 1000-iteration integer sum. Its pass criteria also include exception
recovery, recursion limits and successful allocation after heap exhaustion.

## Virtual timers

Edge and lean provide `machine.Timer(-1)`. Virtual timers share the VM
cog's monotonic counter and upstream soft-timer queue. No dedicated cog,
pin or P2 interrupt is required. Configure a one-shot or periodic timer
with `period` in milliseconds, `period` and `tick_hz` together, or
`freq` in hertz. Resolution is 1 ms and maximum frequency is 1 kHz.
Callbacks take the timer object and execute as ordinary scheduled Python
on the VM cog. `hard=True` raises `ValueError`.

```python
from machine import Timer

timer = Timer(-1, mode=Timer.PERIODIC, period=100, callback=lambda t: print("tick"))
# Stop future ticks and cancel any pending callback for this timer.
timer.deinit()
```

VM loop and event polls service deadlines. A blocking C operation that
does not poll can delay delivery. Missed periods coalesce into one pending
callback per timer. A full scheduler queue retries delivery after 1 ms.
Active timers retain their callbacks through GC and soft reset cancels all
timers. Run `tests/timer.py` on the device and `tests/timer_reset.py
--port PORT` from the host to exercise these paths.

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

On the COM12 board, the worker/GC test returned main ID 1 and worker ID 3.
The recorded 25-collection loop took 77,684 microseconds. The threaded
image also passed a 39,969-byte raw-paste upload, interruption, and four
soft resets with 179,600 free hub-heap bytes at the repeated sample. Six
additional resets with a live worker allowed the next worker to start.
See `validation/threaded.json` for the tested image hash and individual
checks, and `validation/thread-reset.json` for the active-worker resets.

## Roger Loh's five-file native port

The supplied copy of `p2-mp-minimal.zip` has SHA-256
`9aedcf554e84ea80659eb58c5c2c779d07e6d4524eb32a87992e4151c4ef2443`.
Its five members carry April 11, 2026 ZIP timestamps. Roger supplied this
as an overlay for upstream's minimal port. This comparison credits his
implementation and records the specific decisions adopted here. The new
port uses the upstream v1.29.0 sources and independently implemented HAL.
[Original Parallax post](https://forums.parallax.com/discussion/comment/1572778/)

| Archive member | Behavior in the supplied source | Decision in this port |
| --- | --- | --- |
| `main.c` | Starts upstream GC and PYSTACK and enters the friendly interpreter once. Its collector scans word slots between two C locals in descending order. The source warns about missing register roots. Its file lexer raises ENOENT and its import-stat hook always reports absent. | Retain the upstream VM and PYSTACK model. Replace stack-local bounds with linker bounds and PTRA, capture registers, scan every stack offset, implement the soft reboot and raw/friendly loops, and route file/import calls to VFS. |
| `Makefile` | Uses Clang with the P2 target, disables jump tables, uses function/data sections and linker garbage collection, explicitly disables ROM text compression, and freezes a single sample with no long-integer support. Its Mac tool paths, support libraries, default linker script and `loadp2 -PATCH` establish the historical boot contract. | Reuse those target/compiler-size decisions. Pin the shared SDK, use the TinyGo-derived native entry and linker assertions, build support archives from source and freeze selected modules with upstream manifests. The RAM loader understands this image's entry. |
| `mpconfigport.h` | Enables upstream PYSTACK, compiler and GC in a minimal-feature configuration, defines `alloca` as the compiler builtin, specifies P2-EVAL, and sets a 2048-byte GC heap. The separate PYSTACK has 1024 object slots. Several `sys` features are disabled. | Retain PYSTACK as the solution to VM-local dynamic storage. Audit the v1.29.0 preprocessor paths and reject real C VLAs. The main Python stack has 2048 slots and the collector uses the linker's remaining hub arena. Board/profile definitions establish memory and module availability. |
| `mphalport.h` | Its millisecond clock returns zero and its interrupt-character setter has an empty body. | Supply a 64-bit GETCT time base, millisecond/microsecond sleep with pending-event processing, and interrupt delivery on the VM cog. |
| `uart_core.c` | Calls installed libp2 for RX P63 and TX P62. Host input busy-waits on a single receive indication and output emits one byte at a time. | Keep the same pin/baud contract. A dedicated cog handles the Smart Pins, moves bytes through hub rings, and counts interrupt characters while Python runs. |

The ZIP contains no C library, startup assembly, setjmp implementation,
board linker script, SD driver or native pin/cog modules. The linker recipe
depends on the versions present in Roger's installed libp2/libc. The ZIP
does not pin a MicroPython or toolchain commit. Its 160 MHz setting
provides a clock reference; an independently reproduced historical
performance number with matching features is unavailable.

Roger's later public discussion reports native v1.28 P2-EVAL pin/CPU work
and an SDHC demonstration. He describes adapting the ESP32 SD-card model and
work on alternate bus slots. Those changes go beyond this five-file ZIP.
Our Edge SD implementation uses the board's shared SPI wiring, alternate
pin arguments, checked timeouts and upstream FatFs. The Team Oz and
Rayman archives provide separate historical sources. The public page-25
request yielded no readable later source in this audit, and the public
`rogloh` GitHub repository listing contained only `loadp2`.
[Later discussion](https://forums.parallax.com/discussion/169862/micropython-for-p2/p24)
[Public GitHub repositories](https://github.com/rogloh?tab=repositories)
