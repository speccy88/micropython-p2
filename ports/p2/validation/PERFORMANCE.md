# Full Edge measurements

Both images ran native MicroPython v1.29.0 at 160 MHz on the same P2-EC32MB, using its 20 MHz reference, FTDI adapter on COM12 and RAM loading. Both retain floats, the bytecode compiler, FAT/LittleFS2, timers, native drivers, and all 32 MiB of explicit external memory. The reference is firmware source `8432dcbac3aacf072f3b32c424dc4f0c4517f58a` as distributed at the audit commit. The replacement firmware comes from `ee618817ca5a2f119cabdc8ef567ccdf012ed85d`. Their full image digests are in the two measurement records. [Reference](audit-reference.json) · [Replacement](audit-final-bench.json) · [Image manifest](../firmware/manifest.json)

The toolchain is TinyGo/P2 `fc631f268080135e7c13ad27783ee6e1bb6a1c35`, LLVM 15.0.7 at `8dfdcc7b7bf66834a761bd8e445840ef68e4d1a`, plus the private P2 compiler patch. Both builds use freestanding C, `-Oz`, function/data sections, linker section collection and `-Werror=vla`. Only the full Edge VM enables computed-goto bytecode dispatch in the replacement. The C stack remains 16 KiB and the primary Python stack 8 KiB. The full flags and compiler patch digest are versioned. [Makefile](../Makefile) · [Compiler validation](compiler-overlay.json) · [Runtime layout](../VM.md)

## Matched five-run batches

Each cell shows median elapsed microseconds, with the minimum and maximum in parentheses. Times come from the device clock and include the Python operations in the particular batch. The source hashes for both benchmark scripts match across the two measurements. The workloads verify arithmetic results, dictionary/set membership or bytes read back. All five repetitions are retained. [Language and memory workload](../tests/benchmark.py) · [Transfer and scalar array workload](../tests/drivers/transfer_bench.py)

| Work per batch | Reference, µs | Replacement, µs |
| --- | ---: | ---: |
| Integer arithmetic and branches | 28,498 (28,497–28,878) | 17,215 (17,214–17,595) |
| Recursive calls | 36,429 (36,429–36,430) | 29,222 (29,221–29,222) |
| Floating-point arithmetic | 20,587 (20,586–20,588) | 15,748 (15,747–15,748) |
| List, dictionary and set operations | 23,230 (23,230–23,230) | 20,948 (20,948–20,949) |
| Parse and execute 12 source snippets | 70,824 (70,824–70,824) | 70,424 (70,424–70,424) |
| Eight allocation/GC batches | 68,598 (68,598–68,598) | 61,159 (61,159–61,160) |
| 64 KiB raw PSRAM writes | 67,552 (67,551–67,552) | 23,244 (23,243–23,244) |
| 64 KiB raw PSRAM reads | 81,470 (81,470–81,471) | 24,464 (24,464–24,465) |
| 1,024 scalar array writes plus reads | 2,313,554 (2,313,553–2,313,554) | 1,623,636 (1,623,636–1,623,637) |
| Strided array writes and reads | 705,361 (705,361–706,179) | 544,991 (544,990–545,524) |

The flat image shrank from **404,428 to 403,960 bytes**. The linker GC arena grew from 73,432 to 73,904 bytes. The matched host probe reported 71,104 and 71,552 free heap bytes after collection. Loading the language benchmark changed those readings to 67,872 and 68,320 bytes. The eight-megabyte array retained 928 bytes in that context and 880 bytes in the dedicated transfer benchmark, including its 512-byte cache on both builds. These deltas describe retained allocations after GC. Peak allocation during construction was not instrumented. [Reference measurements](audit-reference.json) · [Replacement measurements](audit-final-bench.json)

The transfer benchmark's sampled C stack use decreased from 1,388 to 1,196 bytes (14,996 and 15,188 bytes below the 16 KiB reservation at the point sampled). Stack high-water over a run remains unmeasured. Four-word bursts increased the longest observed PSRAM critical section from 214 to 550 clock cycles, about 1.34 to 3.44 µs. Keep that cost in mind when sharing time with a latency-sensitive native service. The checked 64 KiB batches delivered about 0.97 → 2.82 MB/s on writes and 0.80 → 2.68 MB/s on reads (decimal units). [Driver memory and timing](../drivers/MEMORY.md)

## Final-image I/O timings

At 115,200 baud, five checked 6,240-byte outputs delivered a median **10,230 bytes/s** through the Windows USB relay (9,300–10,523). Ctrl-C to receipt of the traceback took 31 ms median (31–63 ms). On the designated FAT SD card, five 16 KiB file writes including flush and close took 267.695 ms median (243.629–267.831). Reading back and checking the same data took 230.188 ms median (226.296–234.087). These measurements cover the final firmware only. [Serial fixture](../tests/serial_latency.py) · [Serial samples](audit-latency.json) · [SD fixture](../tests/sd_bench.py) · [SD samples](audit-sd-timing.json)

## What changed

| Isolated trial | Result on the Edge | Decision |
| --- | --- | --- |
| VM object at `-Os` | 405,464-byte image, 19,587 µs median integer batch. | The direct-dispatch trial was faster on this workload. [Object-level optimization](audit-os.json) |
| Upstream computed-goto dispatch in the Edge VM | 405,548-byte image, 17,175 µs integer batch and 29,156 µs recursive calls. | Enable on full Edge. Retain the smaller dispatch configuration in the other profiles. [Dispatch trial](audit-goto.json) |
| Rolling unaligned stack scan | 404,456-byte image, 63,812 µs allocation/GC batch. Each possible four-byte window on the ascending stack still contributes a candidate. | Reuse three bytes of the previous window for each new candidate. [GC trial](audit-rolling.json) |
| QPI bursts, cached array hits and ROM string compression | 402,796-byte image, 23,344 µs for 64 KiB writes and 24,566 µs for reads. The 32 MiB address-pattern sweep, boundary checks and borrowed buffers all passed. | Combine with the selected dispatch and stack changes; keep ownership, error messages and range checks. [Compact trial](audit-compact.json) |
| Link-time optimization | A host cross-link of the earlier combined-driver source fit in hub RAM. | Keep LTO experimental pending matched board timings, exception/GC, ABI and peripheral acceptance with that linker configuration. |

In the replacement VM fixture, twenty collections took 6,071–6,102 µs, with a 6,079 µs median. The separate application workload stages bytecode in an external filesystem. Its older 36-stage run completed 23,040 checked operations from 237,971 compiled-module bytes in 4.785 seconds. The older factorial timing and Roger Loh's earlier experiment used different source or firmware. Neither supplies a controlled before/after measurement here. [VM fixture](audit-final-edge.json) · [Bytecode stage receipt](overlay-release.json)

To repeat the matched batches, start the RAM relay for the image in question, then run this command from the repository root. The host records the image digest, script digests, individual samples and any device exception.

```sh
python ports/p2/tests/measure.py --port socket://127.0.0.1:8122 --image ports/p2/firmware/edge.bin --output edge-measurements.json ports/p2/tests/benchmark.py ports/p2/tests/drivers/transfer_bench.py
```
