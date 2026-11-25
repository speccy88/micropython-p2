# P2 Edge hardware checkpoint

The recommended image is [firmware/edge.bin](firmware/edge.bin). It boots the native MicroPython v1.29.0 interpreter at 160 MHz and makes 32 MiB of PSRAM available to Python through region, array and block-device APIs. Start with the [Windows quick start](README.md#load-and-run). The [firmware manifest](firmware/manifest.json) identifies the exact source revision, image hashes, ELF section sizes, heap boundaries, primary stack reservation and C-cog LUT usage.

## Hardware and build

The board on COM12 enumerated as an FTDI serial interface, VID/PID 0403:6001, serial A500507HA. The ROM returned `Prop_Ver G`. All four PSRAM devices returned the expected manufacturer and device family bytes, 0D 5D. The on-module SD socket held a FAT card with 61,132,800 sectors of 512 bytes. The flash returned Winbond JEDEC EF7018. The physical PCB revision requires reading its silkscreen. All device measurements used the Edge's 20 MHz reference and 160 MHz clock configuration. The plain-board image was tested on this same Edge with its PSRAM disabled.

The build uses the pinned TinyGo/P2 LLVM 15.0.7 sources, a separately built P2 backend, and freshly compiled target support objects. The installed TinyGo toolchain and its project remain independent. The three supplied Roger Loh archives have 21 source files in total. His LLVM changes helped establish the intended CORDIC ordering, GETRND encoding and PTRB operands. A separate comparison/branch dependency defect surfaced under the larger VM test suite. Before the correction, an optimized Python set lost 98 of 100 integers. [Archive audit](toolchain/roger-comparison.md) · [Dependencies and licenses](SOURCES.md) · [Compiler regression results](validation/compiler-overlay.json)

## Feature and acceptance matrix

| Area | Status | Evidence and limits |
| --- | --- | --- |
| Native compiler and C runtime | Verified on COM12, with additional host compiler tests | Fresh challenge response covered unaligned frames, nested setjmp/longjmp, varargs, aggregates, arithmetic, bools, memory routines, float math, CORDIC and native operand behavior. The historical ZIPs reference a setjmp implementation outside their contents. [Physical ABI fixture](validation/foundation-overlay.json) |
| VM and serial | Hardware tested | Register-only roots and unaligned stack roots have a dedicated boot fixture. The VM supports bytecode imports, MPZ integers, generators, exceptions, raw paste, Ctrl-C, reset, allocation recovery and an ascending stack. [GC fixture](validation/roots-boot.json) · [Interpreter design](VM.md) |
| PSRAM | Hardware tested on P40–P57 | All four chips, end-of-capacity, device boundaries, unaligned writes, overlapping copies, error checks, concurrent driver activity and volatile filesystems. In-process external allocation metadata and the ordinary collector stay in the hub. [PSRAM contracts](drivers/README.md) |
| Native cogs | Hardware tested | An autonomous counter and versioned, position-independent HUBEXEC drivers run through Python allocations and GC. The loader retains executable and mailbox, tracks pin claims, handles startup timeout and stops drivers on reset. All six available cogs were exhaustible and recoverable. [Driver ABI](drivers/README.md#loadable-hubexec-drivers) · [Driver fixture](validation/hubdriver.json) |
| GPIO and serial buses | Mixed hardware coverage | Pin ownership, PWM-to-capture, native UART loopback, eight software SPI mode/bit-order combinations and software I²C argument/claim handling have board tests. The APIs for SPI and I²C are `machine.SoftSPI` and `machine.SoftI2C`. External slave ACK/stretching, actual SPI peripheral transfers, servo position, encoder mechanics, analog calibration and DAC accuracy require attached loads or instruments. [Bus details](bus/README.md) · [Wiring and samples](drivers/README.md) |
| Timers and scheduling | Hardware tested | `machine.Timer` schedules VM callbacks, retains armed timers through GC, coalesces missed periodic events and handles a full scheduling queue. A hard interrupt callback or per-edge Pin IRQ API remains future work. [Timer tests](tests/timer.py) |
| Storage | SD and flash reads on hardware, volatile writes on hardware | Physical SD reads and FAT directory enumeration passed. The flash probe and bounded partition reads passed. FAT/LittleFS2 create, write, reopen and reset recovery ran in PSRAM. Physical flash erase/program has a host NOR/LittleFS model and requires a separate disposable partition test. Alternate SD wiring, SD writes and cold flash/SD boot require separate validation. [Flash layout and opt-in](storage/FLASH.md) · [NOR model](validation/flash-model.json) |
| Packages and tools | Mixed hardware and host coverage | Stock mpremote serial execution, bidirectional copies and host mip installation are exercised on PSRAM. The standard Thonny generic backend ran a script and retrieved a variable from the physical board through the local serial bridge. A full Thonny GUI session and Mu have separate validation. Device packages include servo/PWM, counters, encoder, ADC logging, TMP102 and SSD1306. Recording buses verify sensor/display protocol sequences. [Package results](validation/packages-host.json) · [Legacy matrix](packages/COMPATIBILITY.md) |
| Optional multicore | Experimental, hardware tested | One additional Python worker with its own stack, a shared GIL and GC coordination. The reset fixture parks a worker on a lock and reclaims it six times. Drivers on the Edge profile can run in parallel with the interpreter. [Multicore tests](tests/threaded.py) |
| Larger extensions | Open | Elastic ordinary Python heap, native/Viper emitters, executable native `.mpy`, multimedia/VGA/USB keyboard, Wi-Fi networking, audio/MIDI and WS2812 each require their own implementation or hardware acceptance. The overlay loader runs architecture-independent bytecode from a volatile filesystem. Each active stage fits in the hub. |

## Using external memory

`p2array.Array` places the bulk data in PSRAM and caches selected pages in ordinary hub buffers. The [8 MiB example](examples/external_array.py) writes and verifies every element, then revisits randomly selected pages after dirty evictions. The cache size describes persistent page buffers. Allocations during the Python loop can temporarily consume much more hub space. `p2.PSRAM` also supports checked staging-buffer I/O without the array cache.

The full-capacity hardware test allocated one managed region of **33,554,432 bytes**, wrote all 8,192 address-tagged tiles before reading any back, then compared every byte with the expected pattern. It used two 4 KiB hub buffers. Writing took 40.476 seconds. Readback and verification took 62.055 seconds. [Full-capacity test](tests/drivers/full_capacity.py) · [Physical results](validation/extended-memory-media.json)

The [bytecode workload](tests/overlay_workload.py) compiles 36 cooperating stages, uploads them to a 2 MiB LittleFS2 volume in PSRAM, and passes state from one stage to the next. With 69,088 bytes of free hub heap at the start, the release executed 237,971 bytes of compiled modules containing 23,040 generated operations. Execution took 4.785 seconds and produced 41,735, matching the independent host calculation. Upload over serial took 107.47 seconds. A single live stage and anything retained across stages must fit with the runtime. [Release overlay measurement](validation/overlay-release.json)

## Recorded measurements

The Edge image from source `8432dcbac` produced byte-identical ELF and flat files in two independent build directories. Its 404,428-byte flat image contains code and initialized data. BSS occupies a further 12,632 bytes. The linker reserves 16,384 bytes for the primary C stack, 1,024 for the serial cog stack and 16,384 bytes at the top of hub RAM. The C-cog runtime uses 1,172 of the available 2,048 LUT bytes. The link fails if the GC arena falls below 32 KiB. [Rebuild comparison](validation/reproducibility.json) · [Profile memory budgets](firmware/manifest.json)

| Measurement on the Edge at 160 MHz | Observed |
| --- | --- |
| Free Python heap after each of four raw resets | 70,640 bytes |
| Timed 1,000-iteration integer sum | 41,528 µs |
| Garbage collection, 20 samples with the VM fixture loaded | 6,809 µs minimum, 6,817 µs median, 6,841 µs maximum |
| Active C stack at the fixture's sample point | 1,388 bytes inside a 16 KiB reservation. This is a sample rather than a high-water mark. |
| Recursive factorial(10), ten seconds | 13,503 iterations |
| 8 MiB typed array, full bulk write / full read verification | 14.338 s / 19.678 s, compared with 18.948 s / 23.082 s in the earlier development image |
| 512 dirty random page evictions and readbacks | 2.329 s with a 512-byte cache. Live hub delta after collection was 5,008 bytes. Transient sampled peak was 48,208 bytes. |
| Combined allocation, GC, PSRAM, serial and autonomous-counter soak | 1,045 loops in 5.001 s, all data verified. A run of eight 513-byte writes took 5,081 µs and eight reads took 5,826 µs. |
| SD block throughput | 16,384 bytes read in 183,348 µs. This board shares the SD and flash pins. |
| ADC readiness | Internal GIO/VIO reference means 720 and 3,417 on P4. Thirty-two undriven input samples completed. External voltage and absolute accuracy were not measured. |

The PSRAM driver keeps each chip-select assertion bounded. The native probe observed 138 write cycles and 214 read cycles. The firmware fast path avoids per-word hub copying for aligned transfers and preserves the original chip transaction. Both array measurements include Python, GC and cache overhead. Differences between the two firmware revisions also include VM/compiler changes. [Edge performance and driver records](validation/edge-release.json) · [Native probe](validation/drivers-probe.json)

### Release acceptance

The Edge ran 698 upstream test files covering language basics, float arithmetic, selected standard modules, FAT, LittleFS and heap allocation. Of these, **573 passed, 125 skipped and zero failed**. The target requested 83 skips and the upstream runner excluded 42 for the detected configuration. The receipt lists each file, the skip category and candidate source guards for program-requested skips. An earlier run lost part of one list printout on the serial transport. The release passed that upstream file, 20 consecutive repetitions, a 39,969-byte raw paste, and an exact 80,896-byte output comparison. The cause of the one earlier serial loss remains unconfirmed. [Upstream results](validation/upstream.json) · [Repeated list output](validation/serial-repeat.json)

| Profile | Flat image | GC arena | Free heap after raw reset | Physical coverage |
| --- | ---: | ---: | ---: | --- |
| Edge | 404,428 B | 73,432 B | 70,640 B | Native devices, VM, storage, PSRAM, packages, tools and upstream suites |
| Lean | 238,420 B | 240,880 B | 235,024 B | Plain-board configuration tested on this EC32MB with external RAM disabled, VM and software timer |
| Threaded | 228,092 B | 198,824 B | 193,936 B | Two GIL-coordinated Python cogs, 25 GC calls in 78,221 µs wall time and six worker resets |

[Lean receipt](validation/lean-release.json) · [Threaded receipt](validation/threaded-release.json) · [Worker reset receipt](validation/thread-reset.json) · [Thonny backend and variable inspector](validation/thonny.json) · [Standard mpremote and mip](validation/mpremote.json)

The existing card's root has 34 live directory entries with four distinct short names. Python's string list, bytes list and iterator all matched the independently decoded on-card entries in order. The earlier firmware reported 34 distinct names: the old compiler incorrectly returned a set length of 34 even for 34 copies of the same key. That same physical control returns one on the corrected firmware. Both images returned identical SHA-256 values for the MBR, boot sector and three root directory sectors. A fresh FAT volume on PSRAM passed creation, enumeration and content verification for 40 distinct short, lowercase and long names. No card repair was attempted. [Raw-sector and API comparison](validation/fat-directory.json) · [Old-image control](validation/fat-historical-control.json) · [Volatile filesystem checks](validation/extended-memory-media.json)

A second RAM-loaded P2 program used the SDK's independent Smart Pin SD driver to read all five sectors twice. Its SHA-256 values matched the MicroPython block driver at every LBA, and its bytewise directory scan counted the same four distinct short names. The recommended Edge firmware was then reloaded from the delivery directory and returned to its friendly REPL on COM12. [Independent SD receipt](validation/sd-independent.json) · [Final RAM-load receipt](validation/installed-ram.json)

## Repeat the checks

Start the RAM session for the selected image as described in the [quick start](README.md). From `ports/p2`, run the following with pyserial and mpremote installed.

```sh
python tests/acceptance.py --port socket://127.0.0.1:8122 --image firmware/edge.bin --output build-retest/edge.json --scripts tests/vm.py tests/timer.py tests/drivers/api.py tests/drivers/bounds32.py tests/drivers/borrowed_io.py examples/external_array.py tests/media_readonly.py
python tests/hubdriver.py --port socket://127.0.0.1:8122 --image firmware/edge.bin --output build-retest/driver.json
mpremote connect socket://127.0.0.1:8122 run tests/drivers/full_capacity.py
python tests/tool_workflows.py --port socket://127.0.0.1:8122 --image firmware/edge.bin --output build-retest/tools.json
python tests/upstream.py --port socket://127.0.0.1:8122 --image firmware/edge.bin --out build-retest/upstream
python tests/overlay_workload.py --port socket://127.0.0.1:8122 --mpy-cross /absolute/linux/path/to/mpy-cross --output build-retest/overlay.json
```

On Windows use `--wsl` for the Linux mpy-cross executable. For the native ABI fixture, stop the serial relay before using its ROM loader. The development and validation workflow uses RAM downloads. Physical write/cold-boot acceptance needs known expendable media and a recoverable boot image. A calibrated analog source, an external I²C/SPI target and an oscilloscope would close the remaining electrical checks. The original minimal-port ZIP has no ready-to-run image for this Edge configuration, so factorial timings on this build cannot establish a controlled performance comparison with Roger's binary.
