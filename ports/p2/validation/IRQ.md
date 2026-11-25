# Cog 0 pin IRQ acceptance

On 2026-11-25 a P2-EC32MB on COM12 (ROM `Prop_Ver G`, 160 MHz) ran the Edge and Lean IRQ images from RAM. The selector, mask, interrupt vector and GPIO event were real P2 hardware. The stimulus came from a second cog driving an otherwise disconnected pad. Applications using the IRQ feature do not need that test cog. [Build and use the feature](../IRQ.md) · [Repeat the experiments](../tests/irq/README.md)

## Firmware and memory

The baseline was `5140d038db094ec17cac9cacf5c9f16538ad276f`. The implementation was `d2b4886d59357a158b1d0494576ce66186abb8f0`. Both used the port's private LLVM 15.0.7 overlay on TinyGo/P2 `fc631f268080135e7c13ad27783ee6e1bb6a1c35`, the same frozen modules and the profile build script. Flags included `-Oz`, corrected `-Oz` map lowering, and computed-goto dispatch on Edge. The 16,384-byte primary stack and the per-profile LUT remained the same size. [Exact inputs and ELF/bin SHA-256](irq/builds.json) · [Compiler setup](../toolchain/README.md)

| Board profile | IRQ | Image bytes | Static BSS bytes | GC arena bytes | LUT bytes |
| --- | --- | ---: | ---: | ---: | ---: |
| Edge | off | 403,960 | 12,632 | 73,904 | 1,172 |
| Edge | on | 406,404 | 12,664 | 71,424 | 1,172 |
| Lean | off | 238,464 | 11,192 | 240,840 | 772 |
| Lean | on | 240,928 | 11,232 | 238,336 | 772 |
| Threaded | off | 232,824 | 63,664 | 194,008 | 772 |

For a controlled byte comparison the builds used `SOURCE_DATE_EPOCH=1795581669`, `MICROPY_GIT_HASH=ee618817ca5a` and `MICROPY_GIT_TAG=v1.29.0-p2.1`, matching the packaged metadata. Use the hashes to identify these images. All three disabled flat binaries **and ELFs** matched the baseline and release manifest byte for byte. There is zero disabled instruction, storage or polling overhead. Independent enabled builds also produced matching binaries and ELFs. Passing `P2_ENABLE_HW_IRQ=1` with `PROFILE=threaded`, or passing an invalid option value, failed at configuration time as intended. [Release manifest](../firmware/manifest.json)

The linked checker found a 19-long ISR at COG $080 and verified its absolute references, exact register use, mask instructions, vector installation, event routing and the Edge PSRAM guards. It found 192 serialized CORDIC commands on Edge and 103 on Lean. The compiler uses registers from $1d0 upward. The runtime's largest SETQ scratch copy occupies $000–$07f. The IRQ reservation covers $080–$09f. [Checker](../tests/check_irq_asm.py) · [Runtime memory implementation](../runtime/memory.S)

## Timing on Edge

The native CT1 fixture compared the same COG loop with and without interrupt delivery. All eight control trials took **627 cycles**. All eight interrupt trials took **721 cycles**. The incremental cost of entry, handler and return in this fixture was **94 cycles (0.588 µs)**. The service timestamp came 17 cycles after the programmed CT1 deadline. The fixture also found correct C/Z, working registers, pointer registers, hardware CALL return, FIFO data, CORDIC quotient/remainder and foreground cycle-counter readings. Six sampled return PCs were in a LUT divide. All 112 alignment/overlap/size cases produced the expected memory contents, including the 512-byte copy boundary. [Raw native results](irq/native.json)

The pin timings below start at the stimulus cog's counter read just before it changes the pin. They include stimulus instructions, input propagation and the ISR prologue. The Python timestamp also includes VM dispatch and callback entry. Each loaded test verified that the edge fell inside the measured foreground operation. One microsecond is 160 cycles. [Measured samples](irq/hil.json) · [Stimulus assembly](../tests/irq/stimulus.S)

| Foreground activity | Trials | Worst observed cycles to native timestamp | Worst observed time to Python |
| --- | ---: | ---: | ---: |
| Waiting for a pin transition | 12 | 91 | 153.5 µs |
| `gc.collect()` | 3 | 45 | 5.60 ms |
| `sum(range(3000))` | 3 | 69 | 28.49 ms |
| 4 KiB aligned PSRAM write | 3 | 181 | 1.20 ms |

A separate CT1 deadline inside `WAITX #2048` reached the native timestamp 1,953 cycles later. Inside a 256-iteration single-instruction `REP`, it took 417 cycles. All three repetitions of each returned those values. For the measured PSRAM workload, the largest recorded chip-select interval was 549 cycles (3.43 µs). Long C calls, application masking and a full scheduler queue can delay Python delivery further. [WAIT/REP measurements](irq/native.json) · [PSRAM measurements](irq/hil.json)

## Cost with no registration

Each cell gives the minimum, median and maximum elapsed microseconds from five runs of the same checked batch at the same clock. Both images used the full Edge profile. At the initial post-reset heap query, the control had 70,928 free bytes and the enabled image had 68,496. The benchmark reported 844 and 848 bytes of stack use at its sampling point. [Benchmark source](../tests/benchmark.py) · [Control](irq/benchmark-off.json) · [Enabled](irq/benchmark-on.json)

| Checked batch | IRQ off, µs | IRQ on, µs | Median change |
| --- | ---: | ---: | ---: |
| Integer arithmetic | 17,105 / 17,105 / 17,473 | 17,344 / 17,345 / 17,718 | +1.40% |
| Calls and recursion | 29,496 / 29,496 / 29,497 | 29,552 / 29,552 / 29,553 | +0.19% |
| Float | 15,821 / 15,822 / 15,822 | 15,767 / 15,767 / 15,768 | −0.35% |
| Lists, maps and sets | 21,220 / 21,220 / 21,220 | 21,257 / 21,257 / 21,257 | +0.17% |
| Parse and execute | 70,563 / 70,563 / 70,564 | 70,825 / 70,825 / 70,826 | +0.37% |
| Allocation and GC | 62,690 / 62,690 / 62,690 | 62,861 / 62,862 / 62,862 | +0.27% |
| 128 KiB raw PSRAM I/O | 49,634 / 49,634 / 49,635 | 49,438 / 49,438 / 49,438 | −0.39% |
| Sequential cached array | 418,693 / 418,693 / 418,694 | 419,301 / 419,301 / 419,301 | +0.15% |
| Random cached array | 545,878 / 545,879 / 546,412 | 546,425 / 546,426 / 546,959 | +0.10% |

A preliminary version called the native save and restore routines for each PSRAM burst and took 57,760 µs on the median raw batch. Keeping the raw hardware mask in the kernel's ABI scratch register $003 brought it to 49,438 µs. The C initialisation path still guards each bounded chip selection. Each transfer returns with the caller's mask restored before timeout reporting or a Python poll.

## Coverage and remaining hardware checks

- Edge and Lean passed rising, falling and both-edge delivery, registration conflict, invalid configuration, argument reentry, GC roots, mask nesting, queue saturation/retry, invalidation of queued work, exception recovery and self-deinit. The four-entry scheduler was filled deliberately. Both images recovered from raw and friendly soft resets with an actual masked edge pending. The Edge relay saw Ctrl-C complete in 41.56–42.86 ms during the storm, including host transport. Lean ran on the same EC32MB using only pins common to both boards. A separate plain Edge was unavailable. [Edge results](irq/hil.json) · [Lean results](irq/lean-hil.json)
- During IRQ activity, Timer(-1) passed its scheduling tests. The native UART ring passed a 192-byte loopback. All eight SPI mode/bit-order combinations passed loopback. The mounted SD and onboard NOR passed read-only access. The standalone Threaded release ran its two-cog GC regression. [Peripheral results](irq/hil.json) · [Threaded results](irq/threaded.json)
- A passive cog sampled actual SCK and MOSI on bare pads during four 25 kHz SoftSPI transactions. It observed all 32 clock edges per transfer, the expected bit sequence and the tested setup/hold intervals. The maximum high pulse was 3,400 cycles in the control and 3,480 with the ISR. A held SCL produced a real SoftI2C timeout under IRQ, and a subsequent START/STOP recovered. Both buses keep their existing timing loops and waits. [SPI observer](../tests/irq/bus_timing.py) · [I²C and SPI results](irq/hil.json)
- External SPI target margins and I²C ACK/stretch interoperability still need a peripheral, pull-ups and a logic analyzer. The optional BME280 fixture documents exact wiring and tests repeated calibration reads, NACK, timeout and recovery. The existing host I²C model covers line-protocol cases separately. [BME280 acceptance](../tests/irq/bus_bme280.py) · [Host I²C model](../tests/bus/i2c_model.py)
