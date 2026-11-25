# Compiler and C foundation

The P2 backend is the LLVM 15.0.7 port and source bundle in `speccy88/tinygo-p2/modern`. Set `P2_WORK` to an installation prepared by its `build-toolchain.sh`. The port invokes that installation's compiler and linker in place. Runtime support objects are built in the MicroPython profile's own build directory.

| Facility | Source and contract |
| --- | --- |
| Arithmetic builtins | Rebuild all objects from the prepared `p2llvm/libp2` sources with CMake. The native library includes LUT code. Every C cog first loads its own LUT copy. |
| Memory | `runtime/memory.S` from TinyGo/P2 (BSD-3-Clause). It handles unaligned and overlapping copies using private cog scratch and preserves r0–r29 and PTRA. |
| Strings | Only explicitly listed P2LLVM libc string sources are compiled from source. P2LLVM profiles that include its stdio, malloc, global locks or disk drivers are excluded. |
| Float math | MicroPython's bundled single-precision libm and the P2LLVM Sun-derived fabsf. The header shim adapts BSD/newlib private integer names and compiler classification macros. |
| Exceptions | `context.S` saves all 30 callee-saved registers, the ascending PTRA and a copy of the status/return PC from CALLA. Longjmp restores them and maps a zero return value to one. Clang's declaration marks setjmp as returning twice. |
| ABI | P2LLVM assigns the first four scalar words to r0–r3, returns a word in r31 and a doubleword in r30/r31. Stack slots can be byte-aligned and varargs use the stack. Compiler-provided stdint/stdarg are preferred. |
| Dynamic frames | This port uses MicroPython's bounded Python stack for bytecode state and local temporaries. The P2 build rejects C VLAs. The bytecode VM runs on the primary cog. |
| Printing and errors | MicroPython supplies print and stream handling and internal errno values. The port's stdio header contains only formatting declarations. Files are managed by VFS. |

From `ports/p2` in bash, run `make -f tests/runtime/Makefile -j4`. The output is `build-runtime/foundation.elf` and a flat `.bin`. On the USB host, run the command below with the real TinyGo loader directory. It loads hub RAM and records both the fresh challenge and the results.

```sh
python tests/runtime/run.py build-runtime/foundation.bin --port COM12 --loader-dir /path/to/tinygo-p2/modern/hil --output validation/foundation.json
```

The fixture runs nested setjmp/longjmp with zero and negative return values, deliberate clobbering of two preserved registers on an unaligned stack, more than 1,800 permutations of short memory operations, mixed variadic values, aggregate copy/return, signed division/remainder, boolean comparison, and single-precision libm.

### Private LLVM overlay

The released SDK miscompiles the sentinel branch in `mp_set_lookup` at `-Oz`. A select can overwrite C/Z after the compare and before its conditional jump. The isolated P2 target patch selects a compare-and-branch terminator which expands after register allocation. It also implements the missing GETRND register instruction, prints signed PTRB offsets, and round-trips PTRA/PTRB counted updates. The signed immediate `[0]` retains its brackets so it reassembles to the exact input register/addressing mode.

From `ports/p2`, with a prepared SDK named by `P2_WORK`, run

```sh
bash toolchain/build-overlay.sh /path/to/tinygo-p2/modern "$HOME/p2-micropython-toolchain"
export P2_BIN="$HOME/p2-micropython-toolchain/build/bin"
bash tools/build_profiles.sh edge lean threaded
```

The script checks the baseline patch digest and checks out LLVM 15.0.7 into a private Git worktree. Clang, MC, LLD and their support tools use that private target. Runtime archives, VM objects and final firmware are rebuilt for the selected profile. The profile script validates the compiler and selects `-Oz` for maps on the corrected compiler. A stock SDK build uses the `-Os` map workaround.

To check an existing installation, run `python3 toolchain/check-overlay.py "$P2_BIN"`. The regression checks the independent select/branch predicates, the quotient and remainder result registers, all 256 standard (unaugmented) pointer encodings, all four flag effects on GETRND, and invalid offset boundaries. The complete comparison records Roger Loh's contributions and the acceptance evidence. [Original archive comparison](roger-comparison.md) · [Compiler validation](../validation/compiler-overlay.json)

The upstream division and memset benchmark fixtures check the compiler's register schedule as well as the loop count. The corrected compiler saves the counter before the call and compares its pre-increment value immediately before the branch. The SDK test patch updates those two FileCheck assertions and keeps the explicit loop bound, single helper call, increment and back edge. To repeat the 32 SDK integration tests, 153 LLVM tests and the instruction matrix with a clean test copy, use the private build produced above.

```sh
out="$HOME/p2-micropython-toolchain"
testcopy="$out/sdk-tests"
mkdir "$testcopy"
cp -a "$P2_WORK/p2llvm/"{tests,utils,libp2,libc} "$testcopy/"
git -C "$testcopy" apply "$PWD/toolchain/p2-sdk-tests.patch"
python3 "$testcopy/tests/run.py" --build-dir "$out/build" --llvm-source "$out/src" -j 2
```

For the physical target extensions, build a separate foundation image with `make -f tests/runtime/Makefile BUILD=build-overlay-foundation P2_LLVM_BIN="$P2_BIN" P2_TEST_OVERLAY=1` and use `tests/runtime/run.py` from the USB host. The integer group also checks unsigned CORDIC division/remainder, actual PTRB reads and updates, different GETRND samples, and tombstone reuse through the `-Oz` fixture.
