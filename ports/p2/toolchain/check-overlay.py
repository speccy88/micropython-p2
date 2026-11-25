"""Exercise the branch, CORDIC, and MC contracts used by the P2 port."""

import argparse
import re
import struct
import subprocess
import tempfile
from pathlib import Path


def run(command, source=None):
    return subprocess.run(command, input=source, text=True, capture_output=True, check=True).stdout


def pointer_cases():
    for ptr, base in (("ptra", 0x100), ("ptrb", 0x180)):
        for offset in range(-32, 32):
            yield f"{ptr}[{offset}]", base | (offset & 63)
        for post in (False, True):
            for step in range(-16, 17):
                if step == 0:
                    continue
                direction = "--" if step < 0 else "++"
                update = ptr + direction if post else direction + ptr
                if abs(step) != 1:
                    update += f"[{abs(step)}]"
                field = (step & 31) if step < 0 else (step & 15)
                yield update, base | 0x40 | (int(post) << 5) | field


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bin", type=Path)
    tools = parser.parse_args().bin.resolve()
    fixture = Path(__file__).with_name("compare-branch.c")
    flags = [tools / "clang", "--target=p2", "-Oz", "-ffreestanding", "-fno-builtin",
             "-mllvm", "-verify-machineinstrs", "-S", "-o", "-"]
    assembly = run(flags + [fixture])
    if not re.search(r"cmps\s+r\d+, #4\s+wcz\s+if_z\s+jmp", assembly):
        raise SystemExit("branch did not consume the sentinel comparison's flags")

    divrem = run(flags + ["-x", "c", "-"],
                 "unsigned rem(unsigned a, unsigned b) { return a%b; }\n"
                 "unsigned quo(unsigned a, unsigned b) { return a/b; }\n")
    for name, read in (("rem", "getqy"), ("quo", "getqx")):
        body = divrem.split(name + ":", 1)[1].split("reta", 1)[0]
        if not re.search(r"qdiv\b.*?\b" + read + r"\b", body, re.S):
            raise SystemExit(f"missing QDIV result for {name}")

    cases = list(pointer_cases())
    statements = [f"rdlong r0, {expr}" for expr, _ in cases]
    random_reads = ["getrnd r3" + suffix for suffix in ("", " wz", " wc", " wcz")]
    statements.extend(random_reads)
    with tempfile.TemporaryDirectory() as work:
        obj, raw = Path(work) / "mc.o", Path(work) / "mc.bin"
        mc = [tools / "llvm-mc", "-triple=p2", "-filetype=obj"]
        run(mc + ["-o", obj], "\n".join(statements) + "\n")
        run([tools / "llvm-objcopy", "-O", "binary", obj, raw])
        words = [value for (value,) in struct.iter_unpack("<I", raw.read_bytes())]
        expected = [(0xf0000000 | (0x58 << 21) | (1 << 18) | (0x1d0 << 9) | value)
                    for _, value in cases]
        expected.extend(0xf0000000 | (0x6b << 21) | (effect << 19) | (0x1d3 << 9) | 27
                        for effect in range(4))
        if words != expected:
            raise SystemExit("pointer or GETRND machine words differ")
        listing = run([tools / "llvm-objdump", "-d", "--no-show-raw-insn", obj])
        lines = re.findall(r"^\s*[\da-f]+:\s+([^\n]+)", listing, re.M)
        if [" ".join(line.split()) for line in lines] != statements:
            raise SystemExit("pointer or GETRND disassembly differs")
        for expr in ("ptrb[32]", "ptra[-33]", "++ptra[0]", "ptrb--[17]"):
            result = subprocess.run(mc + ["-o", obj], input=f"rdlong r0, {expr}\n",
                                    text=True, capture_output=True)
            if result.returncode == 0:
                raise SystemExit(f"invalid operand accepted: {expr}")
    print(f"P2 overlay passed: conditional branch, quotient/remainder, "
          f"{len(cases)} pointer encodings, four GETRND effects, four invalid operands")


if __name__ == "__main__":
    main()
