# Where the full Edge profile spends hub RAM

The compact trial retained the Edge modules, FAT/LittleFS, floating point, both stacks, VM settings, board and 160 MHz clock. It used the audited firmware as the control, before the separate VM dispatch and GC stack-scanning changes. Each cell below shows the median of five board runs followed by the range in microseconds. Both sides ran the exact same benchmark source, SHA-256 `c6f4421c1efc36a513f62e3fb2d3c4cb1abca9571f0cf87d055418258cd4573b`. Each batch checks its result. [Control](../validation/audit-baseline.json) · [Compact trial](../validation/audit-compact.json)

| Batch | Original µs | Compact µs |
| --- | ---: | ---: |
| Copy 4096 bytes to PSRAM and back 16 times | 150654 (150653–150654) | 49526 (49525–49526) |
| Write and sum 256 sequential 32-bit elements | 587374 (587374–587374) | 489019 (489019–489020) |
| Write and sum 160 strided elements | 705276 (705275–706093) | 630152 (630151–630747) |

The raw transfer moved 128 KiB per batch, from 0.83 to 2.52 MiB/s counting both directions. The typed array now checks the most recently used page before searching its LRU list and returns a slot index directly. Hits on that page avoid a list update and a temporary Python tuple.

The final Edge image combines the transfers with the faster VM and GC. In a second matched five-run comparison, 16 writes of 4096 bytes took 23,244 µs (23,243–23,244) versus 67,552 µs (67,551–67,552) originally. The reads took 24,464 µs (24,464–24,465) versus 81,470 µs (81,470–81,471). Writing then summing 1,024 scalar array elements took 1,623,636 µs (1,623,636–1,623,637) versus 2,313,554 µs (2,313,553–2,313,554). The sampled C stack use fell from 1388 to 1196 bytes. Maximum observed PSRAM transaction duration on the final image was 550 cycles, including measurement overhead. [Matched control](../validation/audit-reference.json) · [Final firmware results](../validation/audit-final-bench.json)

Flat firmware shrank from 404428 to 402796 bytes. The benchmark observed 67248 and 69472 free hub bytes, respectively, before constructing the array. Its retained cost for an 8 MiB array was **944 versus 928 hub bytes**, including 512 bytes of actual cache. The simpler transfer-only harness measured 880 retained bytes. These deltas follow a collection and depend on which classes and qstrs the interpreter has already encountered. They exclude transient parser, conversion and GC work. The C stack sample in the identical benchmark was 940 bytes on both images. Heap sizes measured after loading a benchmark differ from an idle prompt.

The original compiler/support revision was held fixed for the compact trial. Enabling upstream ROM text compression alone made the freestanding compiler emit chains of runtime string comparisons and overflow hub RAM. Selecting compressed literals at the call site lets the compiler fold the comparisons. Compression alone produced 402540 bytes; the implemented burst path and frozen array changes used a net 256 more bytes. All error messages remain available. Incremental QSTR preprocessing also needed to retain the C source marker when its first error text came from an included header.

## Larger programs

The existing staged loader imports one ordinary bytecode module at a time from a mounted volume. Its recorded application comprised 36 stages and 237971 bytes of compiled modules. It completed 23040 operations in 4.785 seconds and checked the result. Keep data needed by later stages in a shared explicit region and avoid returning references to the previous module. [Recorded run](../validation/overlay-release.json) · [Loader](../modules/p2overlay.py)

The native P2 backend emits ordinary hub pointers and HUBEXEC calls. On the compact build, `mp_execute_bytecode` alone occupies 10076 hub bytes and calls back into runtime helpers. A 4 KiB code window could not hold that function. At the measured raw transfer rate even a perfectly sequential 4 KiB fill would cost about 1.55 ms before relocation and dispatch overhead. A general overlay needs linker-generated relocation/branch metadata, resident call gates, and an exception-safe strategy for callbacks or returns into evicted code. The supplied Roger Loh patches and pinned TinyGo/P2 memory primitives do not provide those components for this ABI. A practical smaller overlay already exists for independent native services: load a trusted position-independent P2D1 image, run it from a rooted hub allocation, stop it and reuse the memory for another service. [Roger Loh comparison](../toolchain/roger-comparison.md) · [TinyGo/P2 sources](../SOURCES.md)

Moving ordinary Python objects into PSRAM would additionally require translating object pointers on every access and teaching the collector to mark and trace external storage. The Edge interpreter continues to use normal hub-backed objects. Four-word transfers, explicit regions, cached arrays and block devices make the external store available without changing those object semantics.
