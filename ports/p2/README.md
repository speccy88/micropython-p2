# Native MicroPython for the Parallax Propeller 2

Start with the Edge image for the P2-EC32MB. It runs MicroPython v1.29.0
at 160 MHz and uses the four on-board PSRAM devices as explicit external
storage. The interpreter, active Python objects and primary stack live in
the P2's 512 KiB hub. A second cog handles full-duplex serial on P62/P63.

### Load and run

From the repository root on Windows, with the pinned TinyGo/P2 project next
to this checkout, run the following in PowerShell. The ROM loader writes
hub RAM. A power cycle returns to the board's existing boot media.

```powershell
py -3.12 -m venv .venv-p2
.\.venv-p2\Scripts\python -m pip install pyserial==3.5 mpremote==1.29.0
.\.venv-p2\Scripts\python ports/p2/tools/ram_session.py ports/p2/firmware/edge.bin --port COM12 --loader-dir ../tinygo-p2/modern/hil
```

Keep that process open. In a second PowerShell window use stock mpremote:

```powershell
$mp = ".\.venv-p2\Scripts\mpremote.exe"
& $mp connect socket://127.0.0.1:8122 exec "import gc,p2;print(gc.mem_free(), p2.PSRAM().capacity())"
& $mp connect socket://127.0.0.1:8122 run ports/p2/examples/external_array.py
& $mp connect socket://127.0.0.1:8122 repl
```

The loopback socket holds the FTDI handle open between tools. On this Windows
host one direct connection succeeded, then closing and reopening stock
mpremote lost the running RAM program. For terminals that preserve DTR, use
`tools/load_ram.py` once and connect to COM12 at 115200, 8N1. Pass
`--baud 115200` to either loader if a serial adapter needs slower ROM
downloads. No boot-header patch flag is needed. Ctrl-C interrupts Python,
Ctrl-D performs a soft reset, and Ctrl-A / Ctrl-B select raw / friendly REPL.

### Use PSRAM for data and code

```python
from p2array import Array

with Array("I", 2 * 1024 * 1024, pages=2, page_bytes=256) as samples:
    samples[2_000_000] = 123456
    print(samples[2_000_000])
    samples.flush()
```

This creates an 8 MiB unsigned 32-bit array with a 512-byte page cache.
`writefrom` and `readinto` transfer whole windows between external storage
and a caller-owned hub buffer. A newly allocated array defaults to zero
initialization. Use a managed PSRAM region and `BlockDevice` for a volatile
FAT or LittleFS2 volume. The runnable ramfs example explicitly formats only
its new allocation. A fresh interpreter can reclaim the same volatile region
after a soft reset if no intervening allocation overwrites it.

For a program too large to hold all of its compiled modules simultaneously,
place independent bytecode modules on that volume and dispatch them with
`p2overlay.Program("/ram/stages", ("filter_a", "filter_b")).run(state)`.
Each stage exports `run(state)`. It passes ordinary state to the next stage.
A stage that returns a function, instance or generator retaining its module
also retains some hub memory. The largest live stage, its imports and its
working data must fit in hub RAM. See the hardware overlay test for a host
generator, matching mpy-cross build, upload and independent output check.

- [Memory, peripherals, packages, wiring and cleanup](drivers/README.md)
- [Virtual machine, GC, ABI tests and threading](VM.md)
- [SoftSPI, SoftI2C and buffered UART](bus/README.md)
- [Flash geometry, write opt-in and partitioning](storage/FLASH.md)
- [Legacy compatibility](packages/COMPATIBILITY.md)
- [Source pins and reuse decisions](SOURCES.md)
- [Hardware acceptance, remaining limits and continuation](PROGRESS.md)

### Storage and packages

The Edge profile probes the on-module SD socket on P58–P61. A mountable FAT
card becomes the root volume. Friendly-mode boot looks for `boot.py` and
then `main.py`. Ctrl-A followed by a raw-mode soft reset skips those scripts.
Missing media and failed mounts return to the REPL. The board used here
already had a populated SD card. Physical card tests read existing sectors.
The writable filesystem and package tests use separately allocated PSRAM.

```powershell
& $mp connect socket://127.0.0.1:8122 exec "import p2,vfs,os;from p2memory import BlockDevice;r=p2.PSRAM().alloc(1048576);d=BlockDevice(r);vfs.VfsLfs2.mkfs(d);vfs.mount(vfs.VfsLfs2(d),'/work');os.mkdir('/work/lib')"
& $mp connect socket://127.0.0.1:8122 resume mip install --target /work/lib ports/p2/packages/p2array/package.json
& $mp connect socket://127.0.0.1:8122 resume fs ls :/work/lib
```

`resume` keeps the live mount instead of soft-resetting between commands.
The host obtains packages and transfers them over serial. Windows local
manifest paths should use forward slashes. PSRAM is volatile across power
loss. The flash block device defaults to read-only access. No storage
formatting or flash update occurs in the loader.

### Build from source

Use a native Linux or WSL checkout in a directory without spaces. GNU make,
CMake, Ninja, Python 3, Git and a prepared TinyGo/P2 LLVM 15.0.7 build are
required. The SDK pin is `fc631f268080135e7c13ad27783ee6e1bb6a1c35`.
For a clean SDK use its `modern/build-toolchain.sh` with a new directory.
The port reads the prepared toolchain in place and rebuilds its target
archives independently in each profile directory.

```sh
git submodule update --init --depth 1 lib/micropython-lib
export P2_WORK="$HOME/tinygo-p2-work"
bash ports/p2/toolchain/build-overlay.sh /path/to/tinygo-p2/modern "$HOME/p2-micropython-toolchain"
export P2_BIN="$HOME/p2-micropython-toolchain/build/bin"
bash ports/p2/tools/build_profiles.sh edge lean threaded
```

Each profile produces a ROM-loadable flat image and a native ELF in
`ports/p2/build-delivery/<profile>/`. The script also builds
`mpy-cross/build/mpy-cross` on the host. Compile an ordinary module with
`mpy-cross/build/mpy-cross mymodule.py`, then transfer `mymodule.mpy`
with mpremote. The selected VM has no P2 native/Viper dynamic-code emitter.

The private compiler build adds the P2 comparison/branch correction and
assembler changes. Its toolchain check runs before firmware compilation.
The firmware manifest records the source checkout used for the binaries.
Check out that commit to reproduce the version string and build date.

| Profile | Board definition | Use |
| --- | --- | --- |
| edge | P2_EC32MB | PSRAM, storage, peripheral modules, float math, asyncio, frozen packages and independent drivers |
| lean | P2_EDGE | Single VM plus console, small hub footprint, no external memory requirement |
| threaded | P2_EC32MB | Experimental compute profile, one additional Python worker, GIL and coordinated GC |

Both board definitions select a 20 MHz reference and 160 MHz system clock.
A plain P2-EVAL with other clock or storage wiring requires a matching board
definition. The checked load paths are serial RAM ELF and flat binary. Cold
boot, persistent firmware installation and SD boot images have separate
acceptance requirements.
