# Roger Loh's P2 port and compiler changes

Roger Loh supplied replacement source files in three April 2026 forum attachments. The received ZIPs contain five minimal-port files, eleven P2LLVM runtime files, and five LLVM target files. Their names, byte counts, SHA-256 digests, member digests, and all changed hunk ranges are recorded in the [source comparison receipt](../validation/roger-sources.json). The forum download links and ZIP hashes are also in the [source matrix](../SOURCES.md).

For the SDK comparison, the March 13 P2LLVM revision immediately preceding Roger's post is `bdcefcce7860b2232c06f35726fea679a3a7309c`. Its LLVM gitlink is `72a9bb1ef2656d9953d1f41a8196d425ff2ab0b1`. For the minimal port, the comparison base is upstream's v1.28.0 release, `e0e9fbb17ed6fd06bb76e266ae554784c9c80804`. The ZIPs contain no revision metadata establishing Roger's exact development checkouts. The current port uses MicroPython v1.29.0, the TinyGo/P2 LLVM 15.0.7 patch set pinned in the source matrix, and the [additional P2 patch](p2-codegen.patch).

### LLVM target

| File and changed code | Decision and verification |
| --- | --- |
| `MCTargetDesc/P2InstPrinter.cpp`, both hunks | Roger adds signed PTRB offsets, selection of PTRA/PTRB, signed pre/post-update magnitudes and compact zero-offset text. LLVM15 originally handled signed PTRA and unit updates only. The private patch implements formatting and corresponding assembler parsing. Its regression compares hardware encoding fields against ELF bytes and then disassembles all 256 ordinary pointer patterns, including both signs at 16, offsets −32 and +31, and immediate zero. The disassembler preserves explicit `[0]` to distinguish encoded pointer addressing from plain register mode. AUGS-extended indexing was outside Roger's change. |
| `P2ExpandPseudos.cpp`, opening and closing the conditional around GETQX | Roger suppresses a quotient read which twice defined the same virtual destination as the remainder. The selected backend reads the quotient into a fresh virtual register before the remainder into its true result, preserving the order of CORDIC result accesses. Clang's machine verifier accepts unsigned division and remainder and the final code consumes QX and QY respectively. The physical C fixture separately covers signed division and remainder. |
| `P2FrameLowering.h`, constructor | Roger raises stack and transient alignment from one to four bytes. The selected Clang ABI supports byte-offset CALLA frames and aligns individual locals, spills and types. A global four-byte stack guarantee would alter interoperation with C/Go call frames. The physical fixture occupies an intentionally unaligned frame, clobbers two saved registers, longjmps, then verifies the register values and ascending stack restoration. Mixed varargs and aggregate return/copy are separate groups. |
| `P2InstrFormats.td`, five hunks | Adds optional register-def lists to LIDS and LD, propagates them, then creates CORDIC variants for two-operand operations and one-operand QLOG/QEXP. The selected LLVM target expresses this in the instruction records through outer TableGen `Defs` and side-effect declarations. |
| `P2InstrInfo.td`, first hunk | Roger marks QMUL, QDIV, QFRAC, QROTATE and QVECTOR as defining QX/QY, and QSQRT, QLOG and QEXP as defining QX. The selected backend conservatively models both outputs for all eight. GETQX and GETQY carry explicit result-register inputs. The instruction matrix compares generated encodings against the Rev B opcode table. The [foundation receipt](../validation/foundation-final.json) separately records arithmetic execution on silicon. |
| `P2InstrInfo.td`, second hunk | Adds GETRND and COGATN encodings. LLVM15 already has immediate/register COGATN; GETRND was absent. The private patch adds register GETRND with an explicit side effect and checks exact words and disassembly for no flag effect, WZ, WC and WCZ. |

The MicroPython collection failure exposed a separate defect. A select pseudo expanded to a flag-writing compare between the sentinel compare and the branch that consumed its flags. The ZIP's CORDIC changes do not model that dependency. The private LLVM patch emits the compare and branch together after register allocation. [Reduced C reproducer](compare-branch.c) · [Regression program](check-overlay.py)

The extended RAM-loaded fixture returned `P2CRT 19831d8c 0000003f` on COM12. Its integer group executed the reduced tombstone-insertion case at `-Oz`, unsigned quotient and remainder, GETRND sampling, and PTRB reads with negative index, counted pre-increment and counted post-decrement. It also reran the context, memory, vararg, aggregate and float groups. The 256-way exhaustive pointer encoding/disassembly test ran on the host. [Physical receipt](../validation/foundation-overlay.json) · [Target checks](../tests/runtime/overlay.c)

### C support

| Archive member | Changed code and use in the current runtime |
| --- | --- |
| `libc/Makefile` and `libc/misc/CMakeLists.txt` | Add `setjmp.o` and `setjmp.c` to the two historical build systems. The ZIP includes neither the referenced implementation nor an object. The current port assembles its own CALLA-compatible context implementation. |
| `libc/include/setjmp.h` | Replaces the builtin macros with external function prototypes; the second hunk adds a trailing blank line. The port supplies declarations with Clang's returns-twice and noreturn attributes. |
| `libc/include/sys/jmpbuf.h` | Expands nine slots to 34 named slots for r0–r31, LR and SP. The chosen ABI preserves r0–r29; the port's 32-word context stores those registers, PTRA and the saved CALLA result PC/flags. Physical zero-to-one conversion, negative return values, nested returns, and register restoration pass. |
| `libc/drivers/CMakeLists.txt` | Drops SDDriver, diskio, ff, ffunicode and sdmmc sources from the stdio-driver aggregate. The port selects libc sources individually and links its own SD block driver to upstream MicroPython VFS, FatFs and LittleFS. |
| `libc/math/CMakeLists.txt` | Enables double-precision `s_fabs.c`. This firmware uses single-precision floats and builds `s_fabsf.c` with the selected upstream MicroPython libm objects. |
| `libp2/lib/builtins/memcpy.c` | Removes an unused stdio include and returns immediately for zero length before starting a FIFO read. The port's independently maintained cog-local assembly exits early and avoids the FIFO. |
| `libp2/lib/builtins/memmove.c` | Adds the zero-length return. The assembly implements overlap-safe copying in each direction. |
| `libp2/lib/builtins/memset.c` | Guards the WRFAST/FIFO loop with a nonzero length. The selected assembly handles zero before touching the destination. The physical fixture checks 1,862 short length/source/destination combinations with untouched guard bytes. |
| `libp2/lib/builtins/powf.c` and `sqrtf.c` | Remove math.h and stdio.h includes respectively. Current builds source-select and link without a hosted math/stdio runtime. The float fixture checks sqrtf and sinf on the P2. |

### Minimal MicroPython port

| Archive member | Changed code and decision |
| --- | --- |
| `Makefile`, four hunks | (1) Mac-local clang/loadp2 paths, P2 target flags, offsetof override, text compression off. (2) Custom linker flags, garbage collection of sections and explicit minimal sources. (3) Flat binary export of selected sections, and a 160 MHz, 115200-baud loadp2 download. (4) Replaces ARM DFU and native test logic with a P2 compilation recipe. The current port uses explicit reproducible SDK paths, native linker placement, rebuilt support and the RAM-only ROM protocol. |
| `main.c`, three hunks | Reserves 1,024 Python-stack words, initializes the stack, removes the Cortex IRQ/reset implementation. The new port has a bounded PYSTACK, its own P2 bootstrap and root capture for registers and ascending stack. |
| `mpconfigport.h` | Selects builtin alloca, PYSTACK, P2-EVAL identification and the 2 KiB heap outside the Thumb guard. The native port uses board profiles, linked memory bounds and compile-time rejection of VLAs. |
| `mphalport.h` | Identical to the comparison base. It returns a constant tick count and ignores the interrupt character. The current HAL reads the P2 counter and delivers serial interrupts to the VM. |
| `uart_core.c`, three hunks | Includes the P2 support header, initializes RX63/TX62, busy-waits and reads RX, and writes each output byte. The current port preserves the console pins and baud rate using cog-driven serial rings. The physical REPL tests cover interrupted Python execution and reset. |

Later forum posts describe SD and other services beyond these five minimal-port source files. The [VM comparison](../VM.md) distinguishes that later work from the supplied snapshots.
