"""Compare physical FAT root sectors with P2 listdir and set, without logging names."""
import argparse
from collections import Counter
import hashlib
import zlib
import json
from pathlib import Path
import secrets
import struct


def u16(data, index):
    return struct.unpack_from("<H", data, index)[0]


def u32(data, index):
    return struct.unpack_from("<I", data, index)[0]


def boot(data, base, limit):
    if len(data) != 512 or data[510:] != b"\x55\xaa" or u16(data, 11) != 512:
        return None
    spc, reserved, copies = data[13], u16(data, 14), data[16]
    entries, total = u16(data, 17), u16(data, 19) or u32(data, 32)
    fatsz = u16(data, 22) or u32(data, 36)
    if not (0 < spc <= 128 and spc & (spc - 1) == 0 and reserved and copies in (1, 2) and fatsz):
        return None
    root_sectors = (entries * 32 + 511) // 512
    systems = reserved + copies * fatsz + root_sectors
    if not systems < total <= limit:
        return None
    clusters = (total - systems) // spc
    bits = 12 if clusters < 4085 else 16 if clusters < 65525 else 32
    root = u32(data, 44) if bits == 32 else 0
    if bits == 32 and (entries or not 2 <= root < clusters + 2):
        return None
    if bits != 32 and not entries:
        return None
    # FAT32 can explicitly select a FAT when mirroring is off.
    flags = u16(data, 40) if bits == 32 else 0
    active = flags & 15 if flags & 128 else 0
    if active >= copies:
        return None
    return dict(fat_bits=bits, volume_sector=base, sectors_per_cluster=spc, fat_sectors=fatsz,
                fat_start=base + reserved + active * fatsz, root_cluster=root, clusters=clusters,
                root_start=base + reserved + copies * fatsz, root_sectors=root_sectors,
                data_start=base + systems)


def find_volume(read, sectors):
    first = read(0)
    volume = boot(first, 0, sectors)
    if volume:
        return volume
    if first[510:] != b"\x55\xaa":
        raise ValueError("missing boot sector or MBR signature")
    for index in range(4):
        entry = first[446 + 16 * index:462 + 16 * index]
        start, size = u32(entry, 8), u32(entry, 12)
        if entry[4] and 0 < start < sectors and 0 < size <= sectors - start:
            volume = boot(read(start), start, size)
            if volume:
                return volume
    raise ValueError("no supported primary FAT12/16/32 volume")


def root_lbas(volume, read):
    if volume["fat_bits"] != 32:
        yield from range(volume["root_start"], volume["root_start"] + volume["root_sectors"])
        return
    cluster = volume["root_cluster"]
    seen = set()
    while cluster < 0x0ffffff8:
        if cluster in seen or not 2 <= cluster < volume["clusters"] + 2:
            raise ValueError("bad root cluster chain")
        seen.add(cluster)
        base = volume["data_start"] + (cluster - 2) * volume["sectors_per_cluster"]
        yield from range(base, base + volume["sectors_per_cluster"])
        if cluster // 128 >= volume["fat_sectors"]:
            raise ValueError("FAT link outside FAT")
        cluster = u32(read(volume["fat_start"] + cluster // 128), (cluster % 128) * 4) & 0x0fffffff


def short_name(record, apply_case):
    short = bytearray(record[:11])
    if short[0] == 5:
        short[0] = 0xe5
    body, ext = bytes(short[:8]).rstrip(b" "), bytes(short[8:]).rstrip(b" ")
    if apply_case and record[12] & 8:
        body = body.lower()
    if apply_case and record[12] & 16:
        ext = ext.lower()
    return body + (b"." + ext if ext else b"")


def long_name(slots, short):
    if not slots:
        return None
    count = len(slots)
    if count > 20 or slots[0][0] != count | 64:
        return None
    checksum = 0
    for byte in short:
        checksum = (((checksum >> 1) | (checksum << 7)) + byte) & 255
    text = bytearray()
    for number, slot in enumerate(reversed(slots), 1):
        if (slot[0] != (number | (64 if number == count else 0)) or slot[13] != checksum
                or slot[12] or u16(slot, 26)):
            return None
        text.extend(slot[1:11] + slot[14:26] + slot[28:32])
    codes = [unit[0] for unit in struct.iter_unpack("<H", text)]
    length = codes.index(0) if 0 in codes else len(codes)
    if length > 255 or any(c != 0xffff for c in codes[length + 1:]) or 0xffff in codes[:length]:
        return None
    try:
        return text[:2 * length].decode("utf-16le")
    except UnicodeDecodeError:
        return None


def directory(volume, read):
    result, slots, lbas = [], [], []
    for lba in root_lbas(volume, read):
        if len(lbas) >= 128:
            raise ValueError("diagnostic limit of 128 directory sectors reached")
        lbas.append(lba)
        data = read(lba)
        for offset in range(0, 512, 32):
            rec = data[offset:offset + 32]
            if rec[0] == 0:
                return result, lbas
            if rec[0] == 0xe5:
                slots.clear()
            elif rec[11] == 15:
                if rec[0] & 64:
                    slots.clear()
                slots.append(rec)
            else:
                lfn = long_name(slots, rec[:11])
                slots.clear()
                if rec[11] & 8 or rec[0] == 46:
                    continue
                # FatFs' short-only build preserves the raw SFN case. Its
                # LFN build applies NT body/extension case flags on fallback.
                short = short_name(rec, False)
                display = short_name(rec, True)
                if lfn:
                    # This port uses FatFs ANSI/OEM output and code page 437.
                    # FatFs returns the SFN if a Unicode character cannot map.
                    try:
                        display = lfn.encode("cp437")
                    except UnicodeEncodeError:
                        pass
                result.append((short, display, bool(lfn)))
    return result, lbas


# A fresh private seed keeps the report from becoming a filename dictionary.
# FNV tags only compare content between host and board. SHA-256 below commits
# to the whole ordered tag stream. The raw sectors and tags live only in RAM.
def name_tag(data, seed):
    h = seed
    for c in data:
        h = ((h ^ c) * 16777619) & 0xffffffff
    return (len(data), h)


SETUP = """
import os, p2sd
_card = p2sd.active()
assert _card is not None and _card.ioctl(5, 0) == 512
def _sector(i):
    a = bytearray(512)
    b = bytearray(512)
    assert _card.readblocks(i, a) == 0 and _card.readblocks(i, b) == 0
    assert a == b, 'unstable sector read'
    print(bytes(a).hex())
def _tag(s, seed):
    if isinstance(s, str):
        s = s.encode()
    h = seed
    for c in s:
        h = ((h ^ c) * 16777619) & 0xffffffff
    return [len(s), h]
def _counts(names):
    distinct = []
    for name in names:
        if all(name != old for old in distinct):
            distinct.append(name)
    return [len(names), len(distinct), len(set(names)), len(set(hash(n) for n in names))]
"""


def digest(tags):
    h = hashlib.sha256()
    for size, value in tags:
        h.update(struct.pack("<II", size, value))
    return h.hexdigest()


def diagnose(board, report, short_only=False):
    import ast
    report["stage"] = "active mounted card"
    board.exec(SETUP)
    card_size = int(board.exec("print(_card.ioctl(4,0))"))
    seed = secrets.randbelow(1 << 30) + 1
    sector_hashes = {}
    sector_crc32 = {}
    def read(index):
        if not 0 <= index < card_size:
            raise ValueError("read outside card")
        # The sector contents are not logged or written to disk.
        raw = bytes.fromhex(board.exec(f"_sector({index})").decode("ascii"))
        if len(raw) != 512:
            raise ValueError("short sector reply")
        sha = hashlib.sha256(raw).hexdigest()
        sector_crc32[index] = "%08x" % zlib.crc32(raw)
        if sector_hashes.setdefault(index, sha) != sha:
            raise ValueError("repeated sector differs")
        return raw
    report["stage"] = "volume boot sector"
    volume = find_volume(read, card_size)
    report["stage"] = "raw directory sectors"
    records, lbas = directory(volume, read)
    short = [name_tag(row[0], seed) for row in records]
    preferred = [name_tag(row[1], seed) for row in records]
    report.update(card_sectors=card_size, fat_bits=volume["fat_bits"], volume_sector=volume["volume_sector"],
                  sectors_per_cluster=volume["sectors_per_cluster"], raw_entries=len(records),
                  validated_lfn_entries=sum(row[2] for row in records), raw_unique_sfn=len(set(short)),
                  raw_unique_preferred=len(set(preferred)), root_sectors=lbas,
                  sector_sha256=sector_hashes, sector_crc32=sector_crc32)
    for category, expression in (("listdir_str", "os.listdir('/')"), ("listdir_bytes", "os.listdir(b'/')"),
                                 ("ilistdir", "[x[0] for x in os.ilistdir('/')]")):
        report["stage"] = category
        board.exec("_names = " + expression)
        counts = ast.literal_eval(board.exec("print(_counts(_names))").decode("ascii"))
        tags = ast.literal_eval(board.exec(f"print([_tag(n,{seed}) for n in _names])").decode("ascii"))
        tags = list(map(tuple, tags))
        report[category] = {
            "count": counts[0], "pairwise_unique": counts[1], "set_unique": counts[2],
            "builtin_hash_unique": counts[3], "host_unique_content": len(set(tags)),
            "matches_sfn_multiset": Counter(tags) == Counter(short),
            "matches_preferred_multiset": Counter(tags) == Counter(preferred),
            "preferred_position_matches": sum(a == b for a, b in zip(tags, preferred)),
            "ordered_tag_sha256": digest(tags),
        }
    report["expected_preferred_ordered_tag_sha256"] = digest(preferred)
    report["synthetic_counts"] = ast.literal_eval(board.exec(
        "print(_counts(['p2check' + str(i) for i in range(64)]))").decode("ascii"))
    expected = "matches_sfn_multiset" if short_only else "matches_preferred_multiset"
    expected_unique = len(set(short if short_only else preferred))
    report["directory_has_duplicate_names"] = len(records) != expected_unique
    report["passed"] = all(report[key][expected] and
                           report[key]["count"] == len(records) and
                           report[key]["pairwise_unique"] == report[key]["set_unique"] == expected_unique
                           for key in ("listdir_str", "listdir_bytes", "ilistdir"))
    report["passed"] &= report["synthetic_counts"][:3] == [64, 64, 64]
    report["stage"] = "complete"


def main():
    from mpremote.transport_serial import SerialTransport
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--short-only", action="store_true", help="expect the control firmware's 8.3 names")
    args = parser.parse_args()
    report = {"flat_image_sha256": hashlib.sha256(args.image.read_bytes()).hexdigest(),
              "serial_endpoint": args.port, "expected_names": "short" if args.short_only else "long",
              "passed": False}
    board = None
    try:
        board = SerialTransport(args.port)
        board.enter_raw_repl(soft_reset=False)
        diagnose(board, report, args.short_only)
    except Exception as error:
        # Transport exceptions may contain device output. Only report their
        # type here, and expose plain diagnostic messages we generate locally.
        report["error_type"] = type(error).__name__
        if type(error) is ValueError and str(error) in (
                "repeated sector differs", "short sector reply", "bad root cluster chain",
                "FAT link outside FAT", "missing boot sector or MBR signature",
                "no supported primary FAT12/16/32 volume", "diagnostic limit of 128 directory sectors reached"):
            report["error"] = str(error)
    finally:
        if board:
            board.close()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
