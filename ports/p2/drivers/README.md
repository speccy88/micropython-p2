# P2 hardware API and examples

The default board configuration uses a 20 MHz reference and 160 MHz system clock. Select `BOARD=P2_EC32MB` for the four-chip PSRAM Edge or `BOARD=P2_EDGE` for the plain Edge. The ROM reported `Prop_Ver G` on COM12. Read the module markings to identify its printed PCB revision.

## Ownership

The interpreter runs on cog 0. Cog 1 services the console. Additional drivers acquire spare cogs. On the EC32MB, P40–P55 carry four quad data lanes and P56/P57 are clock and chip select. P58–P61 are reserved for storage and P62/P63 for serial. The plain Edge frees P40–P57. A second claim on an occupied configurable pin raises `OSError(EBUSY)`. Selecting a board-reserved pin as GPIO raises `OSError(EPERM)`. Inspect a pin with `p2.pin_owner(number)`. Release configurable pins with their owner's `deinit()` before another driver claims them. Changing the permanent board reservations requires a board configuration change.

Hardware-facing constructors take integer pin numbers. Drivers allocate their handles on the hub heap. Explicit cleanup gives deterministic release. On a soft reset the VM stops native cogs before floating owned pins and reclaiming memory. Code running on another cog must relinquish its own DIR and OUT contributions before handoff. A lock alone cannot float a pin driven by that cog.

## External memory

```python
from p2 import PSRAM
ram = PSRAM()
region = ram.alloc(1 << 20)
try:
    region.write(7, b"wave")
    scratch = bytearray(4)
    region.readinto(7, scratch)
    print(scratch, region.capacity())
finally:
    region.close()
```

| Method | Contract |
| --- | --- |
| `PSRAM()` | Identify all four devices and enter QPI on first use. Missing manufacturer/known-good IDs raise `ENODEV`. |
| `capacity()` | Bytes in the receiver. A device has 33,554,432 bytes. |
| `alloc(n)` | Allocate a positive-size, nonoverlapping region from the device. Offsets on its handle start at zero. Supports 32 simultaneous regions. Allocation is first-fit and does not initialize the bytes. |
| `close()` | Release a region or close a device handle. Existing regions retain separate lifetimes. Access after close raises `ENODEV`. |
| `read(offset, n)` | Copy into a newly allocated hub `bytes` object. Hub heap size limits this request. |
| `readinto(offset, writable_buffer)`, `write(offset, buffer)` | Copy through a hub buffer and return its length. An unaligned write preserves adjacent bytes. |
| `fill(offset, length, byte)`, `copy(dest, source, length)` | Fill or move within a single receiver. Copy supports overlapping ranges in both directions. Maximum staging allocation is 64 stack bytes. |
| `diagnostics()` | `ids` contains four concatenated, bank-ordered eight-byte IDs. `max_cycles` reports the longest observed transaction in P2 clock cycles. `completed` counts confirmed destination bytes in the most recent transfer. |

The device handle refuses direct access into an allocated region. Nested allocations are unsupported. Bounds checks use subtraction before address addition. Timing failures raise `ETIMEDOUT` and leave `completed` excluding the word or four-word burst whose timing was uncertain. During a backward overlapping copy, completed writes start at the high end. Transfer-level serialization uses the single VM cog. Scheduled Python callbacks are deferred until borrowed buffers are released. Transfers poll for Ctrl-C between batches. Other cogs cannot invoke this pin-owning service directly. A future native PSRAM client on another cog needs a mailbox to the owner.

Python buffers, the GC heap and the VM stack are in hub RAM. External offsets require read/write transactions. Filesystems retain their block-device reference while mounted. Unmount a volume before closing its region. Its contents are volatile. After a soft reset the allocator is empty and previously issued handles are gone.

The Edge service uses four-word bursts for a 16-byte-aligned logical offset, an aligned hub buffer and at least 16 bytes remaining. Each chip transfers four consecutive physical bytes. Even the shortest 32-byte wrap window fits the whole transaction. Head, tail and skewed buffer transfers use a single-word transaction, including read-modify-write for partial words. Interrupts are stalled only inside a native transaction, and the C loop polls pending Ctrl-C at most every 256 transferred bytes.

On the 160 MHz Edge the largest observed transaction took 533 cycles in the compact trial and 550 in the final image, including overhead outside chip select. The driver rejects durations of 1,280 cycles or greater. The 32 MiB write/read/full verification finished in 50.648 seconds on the compact trial. Adjacent-byte preservation was checked around 16, 128 and 4096 logical bytes with both aligned and skewed views. [Measured tradeoffs and memory costs](MEMORY.md) · [Hardware record](../validation/audit-compact.json)

The historical short run completed 997 GC/PSRAM/driver iterations. The sustained runner also records progress, heap and native service responsiveness throughout a configurable run. [Sustained validation](../tests/sustained.py)
Eight 513-byte writes took 7,151 µs and reads took 7,254 µs (0.55 and 0.54
MiB/s). The sequence verified unaligned RMW, forward and backward overlapping
copies, closed handles and raw/allocated region exclusion. See the per-script
output in [the Edge acceptance capture](../validation/edge.json).

A second hardware test wrote ten distinctive seven-byte vectors across the
full 32 MiB, including unaligned transfers spanning 8, 16 and 24 MiB and the
final byte. It waited 100 ms, read them in reverse order, restored and then
checked the prior contents. [Boundary and retention capture](../validation/edge-boundaries.json)

## Typed external arrays

The `p2array` package exposes large numeric arrays independently of hub heap
capacity. For example, `Array("I", 2_097_152, pages=2, page_bytes=256)` creates
8 MiB of unsigned 32-bit data backed by external RAM and two 256-byte hub cache
pages. The object, tags, LRU list and transfer buffers also consume hub space.
The `examples/external_array.py` benchmark measures both live hub usage and the
sampled heap low-water mark. The sample is a lower bound on peak consumption.

```python
from p2array import Array
with Array("H", 5_000_000) as samples:
    samples[3_500_123] = 49152
    print(samples[3_500_123])
    page = bytearray(256)
    samples.readinto(3_500_100, page)
    samples.flush()
```

New arrays initially contain zeros. Use `zero=False` when the application
will initialize every value it reads. Alternatively pass `region=region` to
borrow a caller-owned region. Its bytes are preserved unless `zero=True`.
After `close()` the caller may use its borrowed region again. An internally
allocated region is released on close. A borrowed region requires exclusive
ownership for the array's lifetime, including while its cache is clean.

Type codes are signed/unsigned 8, 16 and 32-bit (`b/B/h/H/i/I`) and binary32
(`f`, requires floating-point firmware). Storage is little-endian. Indexes may
be negative. Overflowing integer assignments raise `OverflowError`. Size is
fixed. Use `readinto(element_index, bytearray)` and `writefrom(element_index,
bytes_or_bytearray)` to stream arbitrary numbers of complete packed elements
using a caller-bounded hub window. Both return an element count. Cache
capacity is 1–8 pages, power-of-two page sizes of 32–4096 bytes and at most
16 KiB in total. Scalar writes mark their resident page dirty. Dirty eviction,
bulk I/O and explicit flush maintain coherence. A failed write keeps a dirty
page resident for retry. A failed replacement read invalidates the partial
page. An unsuccessful close can be retried. Explicit flush or close is required
to commit cached data. A soft reset discards in-flight state.

The benchmark fills 8 MiB with index-specific tiles, reads and checks every
byte, writes and verifies 512 sparse scalar updates and prints microsecond
timings. Its two 2 KiB transfer buffers are separate from the two 256-byte
cache pages. Run the host differential and error-injection checks with
`python -B tests/drivers/test_array.py -v`. To install using a writable
target, select `packages/p2array/package.json` with host mpremote.

On the COM12 P2 at 160 MHz this run started with 91,824 hub bytes free, then
stored and verified 8,388,608 external bytes (more than 91 times that starting
free heap). A full write took 18.948 s (432 KiB/s) and a full read with
verification took 23.082 s (355 KiB/s). The 512 sparse writes, flush and 512
reverse-order checks took 2.480 s. After collection the live hub delta was
5,024 bytes, including the 512-byte cache and two 2 KiB tiles. The largest
sampled delta was 82,816 bytes including transient interpreter allocations.
Read the timing fields and firmware hash in [the run record](../validation/edge.json).

`tests/drivers/pwm_capture.py` exercises a no-jumper PWM test. It drives P0
and routes its pad state internally to both capture inputs of P1. It checks
1 kHz and 2 kHz within 1%, then captures high time at nominal 25% and 75%
duty on P2. Leave P0 unconnected for this test. On COM12 it measured 1,000
and 2,000 Hz, with high intervals of 40,000 and 60,001 system clocks.

## Digital and analog pin configuration

`machine.Pin(pin, mode=Pin.IN, pull=None, *, value=...)` supports digital input, push-pull output and open drain. Use `Pin.PULL_UP` or `Pin.PULL_DOWN` for nominal 15 kΩ pulls in input mode. Use `p.value()`, `p.value(bit)`, `p.on()`, `p.off()` or `p()`. The output open-drain high state floats. Release using `deinit()`. User callbacks for GPIO edges are pending.

`p2.SmartPin(pin, mode, x=0, y=0, /)` takes positional arguments. For example, `SmartPin(4, mode, 11)` programs X to 11. The constructor sets mode/X/Y while the pin is held in reset and then enables the circuit. `ready()` reads its IN flag, `read()` reads and acknowledges Z, and `peek()` reads Z without acknowledging. `write_x()` and `write_y()` change the corresponding 32-bit registers. `deinit()` restores high impedance. The paired USB mode is rejected because it needs joint ownership. Low-level modes accept full mode words including the A/B input and pad configuration. Adjacent input selectors are observational. High-level encoder code claims both pins before use.

| Mode family | Named constants on SmartPin |
| --- | --- |
| Basic, pulse and NCO | NORMAL, REPOSITORY, PULSE, TRANSITION, NCO_FREQ, NCO_DUTY |
| Pulse-width modulation | PWM_TRIANGLE, PWM_SAWTOOTH, PWM_SMPS |
| Edge and level counters | QUADRATURE, REG_UP, REG_UP_DOWN, COUNT_RISES, COUNT_HIGHS |
| Time and frequency capture | STATE_TICKS, HIGH_TICKS, EVENTS_TICKS, PERIODS_TICKS, PERIODS_HIGHS, COUNTER_TICKS, COUNTER_HIGHS, COUNTER_PERIODS |
| Serial | SYNC_TX, SYNC_RX, ASYNC_TX, ASYNC_RX |
| Analog | ADC, ADC_EXT, ADC_SCOPE, DAC_NOISE, DAC_DITHER_RND, DAC_DITHER_PWM |
| Configuration | OE, PLUS1_B, MINUS1_B, ADC_1X, ADC_GIO, ADC_VIO, DAC_990R_3V |

For example, `SmartPin(0, SmartPin.REPOSITORY, 123)` stores a value inside the Smart Pin. The standalone probe exercised a high-bit-set value on P0. Each mode's X/Y fields are specified in the [Parallax silicon documentation](https://forums.parallax.com/uploads/editor/bz/sexnusfpmtjf.pdf).

- `machine.PWM(pin, *, freq=1000, duty_u16=0)` uses sawtooth PWM. The 16-bit base and frame divisors quantize frequencies and duty. `freq()` returns the realized integer frequency. `freq(hz)` and `duty_u16(value)` update it. The allowed range is 1 Hz to 80 MHz at 160 MHz system clock. High frequencies have fewer distinct duty levels.
- `machine.ADC(pin).read_u16()` uses 2,048-clock SINC2 sampling and rescales between on-chip ground and VIO references captured during construction. Samples clip to 0..65535. Effective nominal raw resolution is 12 bits. External voltage accuracy needs calibration against a reference and the actual I/O supply.
- The [ADC readiness check](../tests/drivers/adc_ready.py) measures the two internal references and takes 32 input samples from P4 without a reference circuit. It checks conversion readiness and numerical range. Measuring a DAC transfer curve requires a known connection and load. [Parallax ADC example](https://obex.parallax.com/docs/quick-bytes/propeller-2/simple-analog-input/)
- `machine.DAC(pin).write_u16(level)` selects nominal 990 Ω, 3 V mode with 16-bit PWM dither over the 8-bit pad DAC. Output voltage depends on board VIO, filtering and load.
- All three own one Smart Pin and use zero extra cogs. Call `deinit()` after use. The internal loopback verifies PWM period and duty in system-clock units. Absolute-frequency accuracy, ADC voltage accuracy and DAC output characterization require a reference instrument.

## Native driver protocol v1

`p2.Cog(period_us)` launches the shipped PASM2 counter with a period of 1..1,000,000 microseconds. Read its hardware cog with `id()`, a wrapping 32-bit counter with `count()`, and stop it with `stop()`. The code is a linked, long-aligned, firmware-resident HUBEXEC function. The host passes the permanent hub mailbox address in PTRA using SETQ followed by COGINIT in HUBEXEC_NEW mode. The first three mailbox longs are ready, count and interval in cycles. The VM waits up to 10 ms for ready. A missing free cog raises EBUSY. Startup timeout stops that cog before releasing the slot. Stopping is idempotent. Access after stop raises ENODEV.

The counter uses one cog, six scratch registers, CT1, zero pins, zero hardware locks, zero LUT code, no hub stack, and a 16-byte static slot including host bookkeeping. Up to six slots are provisioned (96 hub bytes). The code and mailboxes are outside the GC heap and have fixed lifetimes. In particular, GC may run while the cog writes its aligned 32-bit count. The driver never follows Python object references. It has no Python callback or dynamic binary loader. Build it with the same Clang/P2 target as the firmware. `tests/drivers/build-probe.sh` also builds this exact source into the native probe.

## Loadable HUBEXEC drivers

`p2.Driver(image, pins=())` launches trusted, position-independent PASM2 in one spare cog on the Edge and lean profiles. The image must be immutable Python `bytes`. The loader checks its header and checksum, copies the code to long-aligned hub memory and appends a zero-initialized mailbox of fixed size. Python can access only the mailbox. Each running driver occupies one of six registry roots so GC keeps its entire executable and mailbox alive, even if Python drops the last handle. Recover the same handle with `p2.get_driver(cog_id)`. A driver runs until `stop()` or soft reset. Both stop the cog before clearing its pin claims and registry entry. After `stop()`, drop the handle to make its hub allocation collectible.

| Field or method | Meaning |
| --- | --- |
| Image header | 24 little-endian bytes, Python struct format `<4sBBHIIII`. Magic `P2D1`, ABI 1, flags 0, header size 24, code length in bytes, entry byte offset, mailbox word count, FNV-1a 32-bit checksum over the first 20 header bytes followed by code. The complete file has exactly 24 + code length bytes. |
| Code and entry | 4..4,096 bytes, divisible by four. The entry offset is long-aligned and inside the code. Launch uses HUBEXEC_NEW and SETQ to supply PTRA. There is no preloaded LUT, C stack or MicroPython native-module ABI. |
| PTRA | Start of 4..256 contiguous, long-aligned mailbox words (16..1,024 bytes). Set word 0 to 1 within 10 ms. A timeout stops the cog and releases its claims. |
| Word 1 | Host request sequence, initially zero. Write inputs before publishing a new sequence. The driver handles each changed sequence exactly once. |
| Words 2 and 3 | Driver-completed sequence and driver-defined status. Write results, then status, then the completed sequence. A host checks completion before reading results or reusing input space. |
| Words 4 onward | Driver-specific payload of little-endian 32-bit words, with ownership of each field defined by its driver. |
| `d.id()`, `d.stop()` | Hardware ID 2..7. Stop is idempotent. Mailbox access after stop raises `ENODEV`. |
| `d.word(i)`, `d.word(i, value)` | Read one word or publish an unsigned 32-bit word. The host can write word 1 and words 4 onward. Aligned individual accesses are atomic. |
| `d.write(i, buffer)`, `d.readinto(i, buffer)` | Copy whole words starting at word index `i`. Return byte count. The buffer length must be divisible by four and fit the mailbox. Bulk writes start at word 4 or later. The driver protocol controls synchronization across multiple words. |
| `pins=(...)` | Zero to eight distinct configurable pins, claimed together. Each reports owner `driver`. Group conflicts or exhaustion roll back. Application drivers share cogs 2–7 with the built-in counter and auxiliary UART. |

The assembler must use a single long-aligned executable section named `.p2driver` and export `p2_driver_entry`. The host packer checks a P2 little-endian ELF32 relocatable object, its named entry, section permissions, length, mailbox bounds, relocations and undefined symbols. Use relative branches and derive hub addresses from PTRA. The instruction stream executes with unrestricted P2 hardware access. The packer cannot infer the target of handwritten numeric addresses or indirect branches. Authors must keep writes inside their mailbox and claimed pins, keep the cog alive until the host stops it, and avoid touching other cogs, locks, board storage or VM memory. Keep the thread-local registers and counters you need in the driver cog. P2D1 uses a corruption check; load images from sources you trust.

From `ports/p2` under WSL, build and check the independent example with the port toolchain.

```sh
P2_CLANG="${P2_BIN:-$HOME/tinygo-p2-work/llvm15-build/bin}/clang"
"$P2_CLANG" --target=p2 -c examples/hubdriver/checksum.S -o /tmp/p2-checksum.o
python3 tools/cog_image.py pack /tmp/p2-checksum.o /tmp/checksum.p2d --words 64
python3 tools/cog_image.py verify /tmp/checksum.p2d
cmp /tmp/checksum.p2d examples/hubdriver/checksum.p2d
```

The checksum driver uses 140 bytes of hub code, 256 bytes of private mailbox and one worker cog per instance. It consumes zero locks, LUT words or I/O pins. The test declares P5 to exercise the registry without driving it. Copy `checksum.p2d` and `checksum.py` into the same working directory on a mounted filesystem and run `checksum.py`. The host acceptance runner can load both over raw REPL entirely in RAM. It verifies two independently placed drivers, GC, 32 checksum requests, timeout cleanup and recovery of all six cogs across an active-driver soft reset. [Example and source](../examples/hubdriver/) · [Physical acceptance runner](../tests/hubdriver.py)

### A native service shared with a Python worker

On the experimental Threaded image, the primary Python cog creates and stops `p2.Driver` instances. The other Python cog can retrieve a running service by ID and read/write its mailbox. Each service owns its native cog and claimed pins. The GIL serializes Python bytecode. The native service runs independently. A multiword request needs an application lock covering the payload, request sequence and matching completion; release that lock in a `with` block. Bound the completion wait. A separately scheduled Python producer can otherwise change the payload before the native cog is finished.

The driver root retains the image and its private mailbox until stop. External hub buffers are copied while the GIL is held and never handed to the native cog. Worker attempts to create or stop drivers raise `EPERM`. A soft reboot first parks the worker and stops its cog, then stops remaining native services before the heap is released. The hardware test forced GC while both Python cogs submitted a total of 24 checked requests to one service, rejected worker lifecycle changes and verified the released pin. [Test](../tests/thread_driver.py) · [Result](../validation/audit-threadservice.json)

### Count pulses from either Python cog

Copy `edgecount.py` and `edgecount.p2d` from the HUBEXEC examples. On the primary Python cog, start a counter on a free Smart Pin. With `source` omitted it reads its own pad. To monitor another service's output internally, select a source within three GPIOs of the counting pin. Both must be in P0–P39. Only the counting pin is claimed. [Example files](../examples/hubdriver/) · [Parallax Smart Pin input selectors](https://forums.parallax.com/uploads/editor/ge/amusmwzpxzd9.pdf)

```python
from edgecount import EdgeCounter

with open("edgecount.p2d", "rb") as f:
    edges = EdgeCounter(f.read(), pin=1, source=0)
try:
    before = edges.count()
    strip.show([0x100000])  # a Strip on P0 sends 24 pulses
    # The native cog publishes snapshots. Allow time for its next read.
    import time
    time.sleep_ms(1)
    print((edges.count() - before) & 0xffffffff)
finally:
    edges.close()
```

The hardware counter runs continuously and wraps at 2³². Either Python cog can read its latest snapshot without clearing it. Each native polling loop includes a 1,600-cycle wait (10 µs at 160 MHz). The service takes one cog, one Smart Pin, 124 hub code bytes and 28 mailbox bytes, plus the driver object and Python wrapper. It uses no PSRAM. Close it on the primary Python cog. Full Edge also offers direct `p2.SmartPin.COUNT_RISES` counting without the extra service cog.

### WS2812 pixels

Copy `ws2812.py` and `ws2812.p2d` from the HUBEXEC examples to a mounted volume. Use a free GPIO from P0 through P39. Connect that pin through a suitable 3.3 V-to-5 V logic buffer to the first pixel's DIN, power the strip from a supply sized for its pixel count, and connect grounds. Confirm the timing requirements of the exact strip revision. The example targets the WS2812B-V5/W at the default 160 MHz. [Source and driver image](../examples/hubdriver) · [Worldsemi timing specification](https://www.world-semi.com/web/userfiles/productfile/WS2812B_V5WDatasheet_V6.1_EN.pdf)

```python
from ws2812 import Strip

with open("ws2812.p2d", "rb") as f:
    strip = Strip(f.read(), 5)
try:
    strip.show([0x001000, 0x100000, 0x000010])  # dim red, green, blue
finally:
    strip.close()
```

One native cog sends 1–32 packed GRB pixels per frame. Its hub allocation holds 216 code bytes and a 152-byte mailbox plus the driver header and GC rounding. It uses one pin and zero PSRAM. On the Threaded image, share the same `Strip` object between callers. Its lock covers payload preparation through the final latch acknowledgement. An overlapping `show()` or `close()` raises `OSError(16)` (busy) immediately. Only the primary Python cog can close an idle strip. A frame acknowledgement times out after 100 ms. Once the native cog finishes that frame, the wrapper can accept a new one.

On the Threaded release the P1 counter measured 24 edges from a worker frame and 48 from a main-cog frame on P0. The check exercised overlapping calls, GC, worker ownership and pin release. To repeat it, leave P0/P1 free, RAM-load `firmware/threaded.bin`, and use the relay address printed by the loader. From `ports/p2`, run `python tests/thread_peripheral.py --image firmware/threaded.bin --port socket://127.0.0.1:8122 --output result.json`. [Board result and tested image hashes](../validation/thread-peripheral.json)

On the final Edge firmware a second Smart Pin counted all 768 rising edges in each 32-pixel frame. Another measured a high width of 49 cycles for zero and 105 for one (306 and 656 ns at 160 MHz). No jumper was needed for the on-chip input selectors. The test checked the signal at P0. A physical strip and independent oscilloscope were unavailable. [Waveform test](../tests/drivers/ws2812_timing.py) · [Board record](../validation/audit-final-bench.json)

## Packages and wiring

Port packages are version 0.1.0. The default manifest can freeze `modules/*.py`. To install a separate copy on a mounted, writable filesystem from the checkout root, use the pinned host mpremote with a local package manifest:

```powershell
mpremote connect socket://127.0.0.1:8122 mip install --target /sd/lib ports/p2/packages/p2signals/package.json
```

Use the port's RAM session tool on COM12 to provide the local serial endpoint.
The adapter connects DTR to reset. Keeping it open retains the RAM-loaded
firmware across host commands. Set the target to a writable path on the
selected board. Add the target to `sys.path` if it is outside the board's
active library path. Installation reads files on the host and transfers bytes
over serial. Each example has a finite run and cleanup in `finally` blocks.
Connect common ground for the external examples and use inputs compatible with
3.3 V signaling.

| Package and example | Required firmware and wiring | Memory and resources |
| --- | --- | --- |
| p2signals / servo.py | machine.PWM. P0 to servo signal, external servo supply and common ground. Servo must accept a 3.3 V control signal. | One PWM pin, no extra cog. Use `pulse_us()` within configured mechanical limits and `deinit()` to stop pulses. |
| p2signals / counter.py | p2.SmartPin. P1 to a 3.3 V digital pulse source, source ground to Edge ground. | One input, 32-bit hardware counter, no extra cog. `deinit()` releases the input. |
| p2signals / frequency.py | machine.PWM and p2.SmartPin. Jumper P0 to P1. P0 generates 1 kHz. | Two pins, no extra cog. Raises ETIMEDOUT if the programmed number of periods is not captured. |
| p2signals / encoder.py | machine.Pin and p2.SmartPin. A to P2, B to P3, encoder ground to Edge ground. Add pull-ups to 3.3 V for open-collector outputs. | Two claimed adjacent pins, no extra cog. Position wraps as a signed 32-bit value. |
| p2memory / ramfs.py | p2.PSRAM and VfsLfs2. Onboard P40–P57 only. The example explicitly formats a fresh 512 KiB region. | One external region, VFS working buffers, no extra cog. Unmount, then close. |
| signal_tiles.py | p2.PSRAM. Onboard P40–P57 only. | 1 MiB external allocation and a 512-byte hub tile. Verifies a tile index at every offset, then closes. |
| adc_log.py | machine.ADC and p2.PSRAM. Attach a voltage in the 0..VIO range to P4 and common ground. | One ADC pin, no extra cog, 2,000 external bytes, 2-byte staging. Takes 1,000 samples with at least 1 ms separation. |
| p2devices / tmp102.py | SoftI2C. P6 SCL, P7 SDA, 4.7 kΩ pull-ups to 3.3 V if absent on breakout, 3.3 V/GND, ADD0 to GND (0x48). Normal 12-bit mode. | Two claimed pins, two-byte sample, no extra cog. The caller owns and closes the bus. [TI TMP102](https://www.ti.com/product/TMP102) |
| p2devices / ssd1306.py | SoftSPI, mode 0 and machine.Pin. SCK P8, MOSI P9, MISO P10 reserved but unconnected, CS P11, D/C P12, reset P13. Four-wire SPI, 128×64, internal charge pump, 3.3 V/GND. | Six claimed pins, a 128-byte page, no extra cog. The caller owns the pins and bus. [SSD1306 datasheet](https://www.mouser.com/datasheet/2/830/SSD1306-2488554.pdf) |

The optional `p2legacy` package supports Rayman's finite digital/PWM LED
operations. The [legacy compatibility table](../packages/COMPATIBILITY.md)
lists exact imports, required pin changes, supported operations and missing
Team Oz, Rayman and Total Spectrum features.

External sensor, servo, display and encoder examples require their named peripherals. The CPython package tests validate payload layout, conversions, error handling, block-device operations and the SPI command sequence with recording buses.

## Checks

From this port directory:

```text
python -B tests/drivers/test_packages.py -v
python tests/drivers/check_probe.py validation/drivers-probe.json
mpremote connect socket://127.0.0.1:8122 run tests/drivers/api.py
```

The Python-on-P2 test checks bounds, managed-region exclusion, overlap, RMW and explicit cleanup. It then runs for at least five seconds with allocation and GC, serial progress, external transfers and a native cog with a 100 µs interval. Pass criteria require matching data, a live counter advancing by at least eight ticks per millisecond, and both pass markers. Any missing physical transcript should be treated as an outstanding check.

## Attribution

`psram_bus.c` and `psram_word.S` are byte-for-byte copies of `modern/overlays/tinygo/src/runtime/p2_psram.{c,S}` from tinygo-p2 commit `fc631f268080135e7c13ad27783ee6e1bb6a1c35`. Source SHA-256 values are `7310122903eb8add2869433423f34489afb697b6d5509b1aa8aadcd8c411b060` and `88dd0e4569224d5ed86a44691ce40a1c898ccb0fd4c90bb9bd2ec4fbd89fd34a`. The BSD three-clause license is included in `drivers/LICENSE.tinygo-p2`. The new service adapts the bounds, device identification, word striping, timing and partial-transfer behavior of `machine_p2_psram.go`. [TinyGo/P2 source](https://github.com/speccy88/tinygo-p2/tree/fc631f268080135e7c13ad27783ee6e1bb6a1c35/modern/overlays/tinygo/src)
