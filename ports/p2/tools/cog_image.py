#!/usr/bin/env python3
"""Pack a single-section, relocation-free PASM2 ELF object for p2.Driver."""

import argparse
from pathlib import Path
import struct

HEADER = struct.Struct("<4sBBHIIII")
SECTION = struct.Struct("<10I")


def checked_span(data, start, length):
    if start > len(data) or length > len(data) - start:
        raise ValueError("truncated file")
    return data[start : start + length]


def string_at(table, index):
    if index >= len(table):
        raise ValueError("invalid ELF string index")
    end = table.find(b"\0", index)
    if end < 0:
        raise ValueError("unterminated ELF string")
    return table[index:end]


def extract_elf(data):
    if data[:7] != b"\x7fELF\x01\x01\x01" or len(data) < 52:
        raise ValueError("expected little-endian ELF32")
    kind, machine, ver, _, _, shoff, _, _, _, _, shsize, count, strings = struct.unpack_from(
        "<HHIIIIIHHHHHH", data, 16
    )
    if (kind, machine, ver, shsize) != (1, 300, 1, SECTION.size) or not 0 < strings < count:
        raise ValueError("expected a relocatable P2 ELF32 object")
    sections = list(SECTION.iter_unpack(checked_span(data, shoff, shsize * count)))

    def contents(section):
        return checked_span(data, section[4], section[5])

    names = contents(sections[strings])
    code_index = None
    for i, section in enumerate(sections):
        name = string_at(names, section[0])
        if section[1] in (4, 9) and section[5]:
            raise ValueError("driver has unresolved relocations")
        if section[2] & 2 and section[5]:
            if (
                name != b".p2driver"
                or section[1] != 1
                or section[2] != 6
                or code_index is not None
            ):
                raise ValueError("only one allocated executable .p2driver section is allowed")
            if section[8] != 4:
                raise ValueError("driver must require four-byte alignment")
            code_index = i
    if code_index is None:
        raise ValueError("missing .p2driver section")
    entries = []
    for section in sections:
        if section[1] != 2:
            continue
        if section[9] != 16 or section[6] >= count or section[5] % 16:
            raise ValueError("invalid ELF symbol table")
        names = contents(sections[section[6]])
        for index, offset, _, info, _, target in struct.iter_unpack("<IIIBBH", contents(section)):
            if info >> 4 and not target:
                raise ValueError("driver has undefined symbols")
            if (
                string_at(names, index) == b"p2_driver_entry"
                and info >> 4 == 1
                and target == code_index
            ):
                entries.append(offset)
    if len(entries) != 1:
        raise ValueError("expected one global p2_driver_entry in .p2driver")
    return contents(sections[code_index]), entries[0]


def checksum(data):
    value = 2166136261
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xFFFFFFFF
    return value


def verify(data):
    if len(data) < HEADER.size:
        raise ValueError("truncated image")
    magic, abi, flags, size, length, entry, words, check = HEADER.unpack_from(data)
    if (magic, abi, flags, size) != (b"P2D1", 1, 0, HEADER.size):
        raise ValueError("incompatible image header")
    if (
        length != len(data) - size
        or not 4 <= length <= 4096
        or length % 4
        or entry % 4
        or entry >= length
    ):
        raise ValueError("invalid driver code size or entry")
    if not 4 <= words <= 256 or checksum(data[:20] + data[size:]) != check:
        raise ValueError("invalid mailbox size or image checksum")
    return length, entry, words


def pack(obj, words):
    code, entry = extract_elf(obj)
    header = HEADER.pack(b"P2D1", 1, 0, HEADER.size, len(code), entry, words, 0)[:20]
    image = header + struct.pack("<I", checksum(header + code)) + code
    verify(image)
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    make = sub.add_parser("pack")
    make.add_argument("object", type=Path)
    make.add_argument("image", type=Path)
    make.add_argument("--words", required=True, type=int, choices=range(4, 257), metavar="4..256")
    check = sub.add_parser("verify")
    check.add_argument("image", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "pack":
            image = pack(args.object.read_bytes(), args.words)
            args.image.write_bytes(image)
        else:
            image = args.image.read_bytes()
        code, entry, words = verify(image)
    except (ValueError, OSError, struct.error) as error:
        parser.exit(1, f"{error}\n")
    print(f"{args.image}: {code} code bytes, entry +{entry}, {words} mailbox words")


if __name__ == "__main__":
    main()
