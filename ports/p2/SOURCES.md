# P2 source and reuse record

The native target starts at MicroPython v1.29.0, commit
`0fd6c573ea815774668bbb16b8e197c8822368b2`. The release list and Git
tags agreed on 24 November 2026. The newer v1.30.0 tag explicitly says preview.

| Source inspected | Decision for this port |
| --- | --- |
| [MicroPython](https://github.com/micropython/micropython/releases/tag/v1.29.0) and [micropython-lib](https://github.com/micropython/micropython-lib/tree/ee4bb8ff139e24c42b739935fbd8ec7c4d061e02) | Retain upstream history, VM, compiler, GC, PYSTACK, bytecode tools, VFS, FatFs, LittleFS and REPL code. The library commit is the upstream submodule pin. |
| [TinyGo/P2](https://github.com/speccy88/tinygo-p2/tree/fc631f268080135e7c13ad27783ee6e1bb6a1c35/modern) | Reuse its LLVM, Clang, LLD and ROM loader. Adapt the two-stage native bootstrap, clock, memory assembly and PSRAM transactions. The Go task scheduler and collector have no role in this firmware. Compare the phase-specific tests to modern/VALIDATION.md. |
| [ne75/p2llvm](https://github.com/ne75/p2llvm/tree/b914b1baa8a2055feb52c801b5c3564eda6a9abc) | Target ancestry and source for selected libc routines and compiler-rt builtins. Recompile with the patched 15.0.7 target. See runtime/runtime.mk. LLVM base is 8dfdcc7b7bf66834a761bd8de445840ef68e4d1a. |
| [Roger Loh's original post](https://forums.parallax.com/discussion/comment/1572778/) and [later discussion](https://forums.parallax.com/discussion/169862/micropython-for-p2/p24) | The user supplied the three original attachments after the live server returned a CAPTCHA. The five port files, five LLVM files and eleven support-library files were available for comparison. See [VM comparison](VM.md) and [toolchain notes](toolchain/README.md). The later public discussion describes v1.28 on P2-EVAL, including SDHC and alternate slots. These five port files describe an earlier minimal configuration. |
| [Eric Smith / Total Spectrum](https://github.com/totalspectrum/micropython/tree/0e552b41f62ed64c8f4be3ca6b93a91c5b3ef1ae/ports/riscv-p2) | Inspected board, buffered serial, Pin/CPU and SD source. Historical SD pin order and bounded SPI transactions give useful comparison points. Implemented native single-owner drivers using the current VM APIs. |
| [riscvp2](https://github.com/totalspectrum/riscvp2/tree/4e1e88e4d8216ddde8f45a072de32ecdeb9f02e2) | Inspected trace/JIT build, LUT, hub and flash linker scripts. This uses a different instruction set and execution engine. |
| [Team Oz](https://github.com/team-oz/p2-native-micropython/tree/1ccb02008146d5fa87b491eefc20d3ebe763c818) | Inspected P2NMP113.zip and both Spin2 wrappers. The archive contains three binary images and two loaders; its second loader directs a flash installation. It supplies a historical standalone workflow but no rebuildable native driver source in that archive. No Oz installer was run. SHA-256 53e5b975aa69916d889a7fce213c3c7ca1fae31eda5f92f9dd3db1e0f3b42916. |
| [Rayman's distribution](https://www.rayslogic.com/Propeller2/upy/micropython.html) | The September 2024 v1.23 source archive contains machine_pin.c, machine_i2c.c, machine_spi.c, SD, serial, VGA and USB files. The provided builds use the RISC-V runtime and a 252 MHz board configuration. Legacy p2 and display helpers need individual compatibility checks. Archive SHA-256 6b9b761c67cf91793f3c28bd0636d32f56a7869d215652944a2a3ee494a5024f. |
| [Parallax P2-EC32MB guide](https://www.parallax.com/package/p2-edge-module-with-32mb-ram-product-guide/) | Board clock and pin reservations. The ROM identifies its silicon version; the serial adapter does not report the PCB silkscreen revision. |

### Compiler ancestry

The SDK's modern/toolchain.lock.json pins all source trees, modern/build-toolchain.sh
configures LLVM and rebuilds the target support library, and modern/patches
contains distinct LLVM, P2 support and TinyGo changes. The TinyGo overlay's
targets, runtime/p2_memory.S, runtime/p2_psram.c and .S, machine/machine_p2_psram.go
and hardware tests establish the original contracts. This port has two startup
cogs, its own mailbox and pins registry, a separate C stack and Python
allocator, and a new setjmp/longjmp for Clang's ascending CALLA stack.

| Observed requirement | Status relative to TinyGo's compiler |
| --- | --- |
| Boolean truncation and signed remainder | Already addressed in the pinned SDK. The native C fixture exercises signed quotient/remainder and boolean results. |
| Integer64/double alignment and aggregate values | SDK target data layout and Clang sret/byval patches retained. Mixed varargs and aggregate copies are included in physical acceptance. |
| Variable-length C stack allocation | Still unsupported in this backend. The port uses upstream's exception-restored PYSTACK, rejects VLAs during compilation and checks stack direction explicitly. |
| Memory and CORDIC clobbers | Reuse the tested memory primitives and interrupt-controlled PSRAM word implementation. MicroPython driver's non-Python worker has independent cog-local state. |
| Historical binary archives and stdio | Use rebuilt support and MicroPython file APIs and printf. C objects from older ports are not linked. |

Attribution and license notices are retained alongside copied source. The
P2LLVM string and math implementations are built from the pinned source trees.
The physical fixtures in this repository are the authority for this port's
acceptance. Benchmarks from the older projects describe their own configurations.

| Supplied attachment | SHA-256 |
| --- | --- |
| [p2-mp-minimal.zip](https://forums.parallax.com/discussion/download/148228/p2-mp-minimal.zip) | 9aedcf554e84ea80659eb58c5c2c779d07e6d4524eb32a87992e4151c4ef2443 |
| [llvmfixes.zip](https://forums.parallax.com/discussion/download/148229/llvmfixes.zip) | f87677f8032e718b8df5af2157a7ec6c473cb5bd294c2d3855ba5bda950b40d6 |
| [p2llvm-fixes.zip](https://forums.parallax.com/discussion/download/148230/p2llvm-fixes.zip) | ff92f4339b8ba42f0c977ced07cac60f6640eb35a3d8896112481ec3b247c49d |
