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

The [bytecode workload](tests/overlay_workload.py) compiles 36 cooperating stages, uploads them to a 2 MiB LittleFS2 volume in PSRAM, and passes state from one stage to the next. The host independently computes the result. A previous board run executed 237,971 bytes of compiled modules with 92,256 bytes of free hub heap at startup. A single live stage and anything retained across stages must fit with the runtime. [Original overlay measurement](validation/overlay.json)

## Repeat the checks

Start the RAM session for the selected image as described in the [quick start](README.md). From `ports/p2`, run the following with pyserial and mpremote installed.

```sh
python tests/acceptance.py --port socket://127.0.0.1:8122 --image firmware/edge.bin --output build-retest/edge.json --scripts tests/vm.py tests/timer.py tests/drivers/api.py tests/drivers/bounds32.py tests/drivers/borrowed_io.py examples/external_array.py tests/media_readonly.py
python tests/hubdriver.py --port socket://127.0.0.1:8122 --image firmware/edge.bin --output build-retest/driver.json
python tests/tool_workflows.py --port socket://127.0.0.1:8122 --image firmware/edge.bin --output build-retest/tools.json
python tests/upstream.py --port socket://127.0.0.1:8122 --image firmware/edge.bin --out build-retest/upstream
python tests/overlay_workload.py --port socket://127.0.0.1:8122 --mpy-cross /absolute/linux/path/to/mpy-cross --output build-retest/overlay.json
```

On Windows use `--wsl` for the Linux mpy-cross executable. For the native ABI fixture, stop the serial relay before using its ROM loader. The development and validation workflow uses RAM downloads. Physical write/cold-boot acceptance needs known expendable media and a recoverable boot image. A calibrated analog source, an external I²C/SPI target and an oscilloscope would close the remaining electrical checks. The original minimal-port ZIP has no ready-to-run image for this Edge configuration, so factorial timings on this build cannot establish a controlled performance comparison with Roger's binary.
