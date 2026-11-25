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

The fixture runs nested setjmp/longjmp with zero and negative return values, deliberate clobbering of two preserved registers on an unaligned stack, more than 1,800 permutations of short memory operations, mixed variadic values, aggregate copy/return, signed division/remainder, boolean comparison, and single-precision libm. Roger Loh identified modulus, CORDIC dependencies, stack frames and stdio linkage in the older LLVM 14 port. The modern backend uses different frame, register-save, call and builtins code. The byte-by-byte historical patch comparison requires the original archives. See the port's source matrix for current acquisition status.

## Original forum attachments

The original HTML of the archived P23 post identifies all three media IDs, filenames and file URLs. On 24 November 2026 the primary server returned HTTP 202 challenge HTML for each download and the browser requested an interactive CAPTCHA. The Wayback Machine retained the post, while requests for the six possible archive-file URLs (download route and stored file for each) returned HTTP 404. ZIP checksums are pending. The archived P24 page from 20 May ends with a 22 April post, and its pagination ends at page 24. The later live state remains unconfirmed. [19 May P23 capture](https://web.archive.org/web/20260519133108/https://forums.parallax.com/discussion/169862/micropython-for-p2/p23) and [20 May P24 capture](https://web.archive.org/web/20260520010039/https://forums.parallax.com/discussion/169862/micropython-for-p2/p24).

| Original name | Original attachment | Stored ZIP |
| --- | --- | --- |
| p2-mp-minimal.zip | [148228](https://forums.parallax.com/discussion/download/148228/p2-mp-minimal.zip) | [d2g4tb5o0kms.zip](https://forums.parallax.com/uploads/editor/4g/d2g4tb5o0kms.zip) |
| llvmfixes.zip | [148229](https://forums.parallax.com/discussion/download/148229/llvmfixes.zip) | [vfug12bxm3uh.zip](https://forums.parallax.com/uploads/editor/yt/vfug12bxm3uh.zip) |
| p2llvm-fixes.zip | [148230](https://forums.parallax.com/discussion/download/148230/p2llvm-fixes.zip) | [yv6wrlghoj6i.zip](https://forums.parallax.com/uploads/editor/um/yv6wrlghoj6i.zip) |

Once available, hash each original archive and compare each source file against the P2LLVM commit and LLVM submodule recorded there, then against the prepared LLVM 15 tree. Preserve the old ABI files as reference. The physical C foundation regression tests can be rerun using the commands above.
