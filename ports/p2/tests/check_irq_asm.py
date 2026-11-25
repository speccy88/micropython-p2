"""Check the native INT1 contract against the P2 objects that will run."""

import argparse
from pathlib import Path
import re
import subprocess


def require(condition, message):
    if not condition:
        raise SystemExit("P2 IRQ verification failed: " + message)


def check(tool_dir, firmware, obj):
    def tool(name, *args):
        return subprocess.check_output([tool_dir / name, *args], text=True)

    symbols = {}
    for line in tool("llvm-nm", "-P", firmware).splitlines():
        name, kind, address, *_ = line.split()
        symbols[name] = int(address, 16)

    instructions = {}
    listing = tool("llvm-objdump", "-d", firmware)
    for match in re.finditer(r"^\s*([0-9a-f]+): ((?:[0-9a-f]{2} ){4})\s+(.+)$", listing, re.M):
        address, raw, asm = match.groups()
        instructions[int(address, 16)] = (int.from_bytes(bytes.fromhex(raw), "little"), asm)

    def verify(name, words):
        for offset, expected in enumerate(words):
            addr = symbols[name] + 4 * offset
            actual, asm = instructions[addr]
            require(actual == expected, f"{name}+{offset * 4:#x}: {asm} ({actual:08x})")

    def augmented(op, addr):
        return [0xFF000000 | (addr >> 9), op | (addr & 511)]

    # Exact whitelist, including all condition, flag, source and destination
    # bits. Thus a branch, hidden clobber or SETQ cannot enter the copied blob.
    pending_relocs = []
    words = [0xFD640025]  # SETINT1 #0

    def hub_access(op, symbol):
        name = "p2_irq_" + symbol
        addr = symbols[name]
        require(
            symbols["_bss_start"] <= addr < symbols["_bss_end"] and addr % 4 == 0,
            f"{name} outside aligned HUB BSS",
        )
        offset = 4 * len(words)
        pending_relocs.extend(
            [(offset, "R_P2_AUG_HI23", name), (offset + 4, "R_P2_AUGS_LO9", name)]
        )
        words.extend(augmented(op, addr))

    write_r31, read_r31 = 0xFC67DE00, 0xFB07DE00
    hub_access(write_r31, "saved_r31")
    words.append(0xFD63DE1A)  # GETCT r31, no WC (preserve latched high CT)
    hub_access(write_r31, "timestamp")
    hub_access(read_r31, "pin")
    words.extend([0xFD73DE40, 0xFD63DE6C])  # TESTP r31 WC / WRC r31
    hub_access(write_r31, "level")
    hub_access(read_r31, "generation")
    hub_access(write_r31, "pending")
    hub_access(read_r31, "saved_r31")
    words.append(0xFB3BFFF5)  # RETI1 restores foreground C, Z and PC.
    verify("p2_irq_stub", words)

    blob = symbols["p2_irq_stub"]
    length = 4 * len(words)
    require(blob % 4 == 0 and blob >= 0xA00, "unaligned or non-HUB blob")
    require(blob + length == symbols["p2_irq_stub_end"] and length <= 32 * 4, "bad blob size")
    section = re.search(
        r"\s\.p2\.irq_blob\s+([0-9a-f]+)\s+([0-9a-f]+)\s+TEXT",
        tool("llvm-objdump", "-h", firmware),
    )
    require(
        section and tuple(int(v, 16) for v in section.groups()) == (length, blob), "blob section"
    )
    relocations = tool("llvm-readelf", "-r", obj).split("'.rela.p2.irq_blob'")[1].split("\n\n")[0]
    actual_relocs = []
    for line in relocations.splitlines()[2:]:
        offset, _, kind, _, name, plus, addend = line.split()
        require((plus, addend) == ("+", "0"), f"nonzero blob relocation addend: {line}")
        actual_relocs.append((int(offset, 16), kind, name))
    require(actual_relocs == pending_relocs, "unexpected blob relocation type, offset or target")

    reta = 0xFD64002E
    verify("p2_irq_save", [0xFD7BDE35, 0xFD604224, 0xF047DE01, 0xF507DE01, reta])
    verify("p2_irq_restore", [0xF7CFA001, 0x5D604224, 0xAD604024, reta])
    verify(
        "p2_irq_native_install",
        [
            0xFD63DE01,  # COGID r31
            0xFB9FDE08,  # TJNZ r31 to RETA
            0xFD640025,  # SETINT1 #0
            0xFD604A24,  # NIXINT1
            *augmented(0xF607DE00, blob),  # MOV r31, ##p2_irq_stub
            0xFF800000,  # assembler emits AUGD for symbol-difference expression
            0xFD640028 | ((len(words) - 1) << 9),  # SETQ #longs-1
            0xFB0101EF,  # RDLONG $080,r31
            0xF607E880,  # MOV IJMP1,#$080
            reta,
        ],
    )
    verify(
        "p2_irq_native_arm",
        [
            0xFD640025,  # SETINT1 #0
            0xFD604A24,  # NIXINT1
            *augmented(0xFC67A000, symbols["p2_irq_pin"]),  # WRLONG r0, ##p2_irq_pin
            0xF603DFD1,  # MOV r31,r1 (trigger)
            0xF067DE06,  # SHL r31,#6
            0xF543DFD0,  # OR r31,r0 (pin)
            0xFD63DE20,  # SETSE1 r31
            0xFD640825,  # SETINT1 #4
            reta,
        ],
    )
    verify("p2_irq_native_stop", [0xFD640025, 0xFD604A24, 0xFD640020, 0xF607E800, reta])

    # The Edge fast path keeps its raw mask token in ABI scratch $003
    # through a whole chip selection. The word and quad entries converge.
    for op in ("read", "write"):
        entry = f"p2_psram_{op}_quad"
        if entry not in symbols:
            continue
        start = symbols[entry]
        end = start
        while end in instructions and instructions[end][0] != reta:
            end += 4
        require(end in instructions, f"{entry} missing return")
        kernel = [instructions[a][0] for a in range(start, end, 4)]
        getbrk, stalli = 0xFD780635, 0xFD604224
        select, release = 0xFD647248, 0xFD647249  # OUTL/OUTH #57
        require(
            all(kernel.count(word) == 1 for word in (getbrk, stalli, select, release)),
            f"{entry} mask/CS operations",
        )
        save = kernel.index(getbrk)
        require(
            kernel[save + 1] == stalli and save < kernel.index(select) < kernel.index(release),
            f"{entry} mask/CS order",
        )
        # TEST $003,#2 WZ / IF_Z ALLOWI, immediately before the return.
        require(kernel[-2:] == [0xF7CC0602, 0xAD604024], f"{entry} raw token restore")
        uses = [a for a in range(start, end, 4) if "$0x003" in instructions[a][1]]
        require(uses == [start + 4 * save, end - 8], f"{entry} mask token clobber")

    # Pipelined CORDIC commands can overwrite each other's results during a
    # long ISR even if the ISR never uses CORDIC. Require a blocking result
    # read after each issued command in the final HUB and LUT code.
    cordic = 0
    for addr, (_, asm) in instructions.items():
        if re.search(r"\b(qmul|qdiv|qfrac|qsqrt|qrotate|qvector|qlog|qexp)\b", asm):
            next_asm = instructions[addr + 4][1].split()
            require(next_asm[0] in ("getqx", "getqy"), f"undrained CORDIC at {addr:#x}: {asm}")
            cordic += 1
        if re.search(r"\$0x0[89][0-9a-f]\b", asm):
            require(addr == symbols["p2_irq_native_install"] + 32, f"reserved COG access: {asm}")
    require(cordic > 0, "failed to locate linked arithmetic helpers")
    print(
        f"INT1 verified: {len(words)} COG longs at $080, {cordic} non-overlapping CORDIC commands"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bin", type=Path, required=True)
    parser.add_argument("firmware", type=Path)
    parser.add_argument("irq_object", type=Path)
    args = parser.parse_args()
    check(args.bin, args.firmware, args.irq_object)
