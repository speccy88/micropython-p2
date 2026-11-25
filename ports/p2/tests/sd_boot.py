"""Prepare or check an Edge FAT32 SD boot file through the RAM-loaded interpreter."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

from fat_directory import boot, u16, u32

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from p2ram import read_image

BOOTFILE = "/_BOOT_P2.BIX"
SHORT_NAME = b"_BOOT_P2BIX"


def read_sectors(board, index, count=1):
    """Keep the physical read fixed while retrying only incomplete serial frames."""
    size = count * 512
    board.exec(
        f"sector_buf=bytearray({size}); "
        f"assert sd.readblocks({index},sector_buf)==0, 'readblocks LBA {index}, {count} sectors'"
    )
    data = bytearray()
    for start in range(0, size, 256):
        prefix = f"{index}:{start}:".encode()
        command = f"print('{prefix.decode()}'+bytes(sector_buf[{start}:{start + 256}]).hex())"
        for attempt in range(3):
            reply = board.exec(command).strip()
            try:
                if not reply.startswith(prefix):
                    raise ValueError("missing frame identifier")
                payload = reply[len(prefix) :]
                if len(payload) != 512:
                    raise ValueError(f"expected 512 hex digits, received {len(payload)}")
                block = bytes.fromhex(payload.decode("ascii"))
                if len(block) != 256:
                    raise ValueError(f"expected 256 bytes, decoded {len(block)}")
            except ValueError as exc:
                if attempt == 2:
                    raise ValueError(
                        f"SD readback frame at LBA {index + start // 512}, "
                        f"sector offset {start % 512}, failed three times: {exc}"
                    ) from exc
            else:
                data.extend(block)
                break
    return bytes(data)


def geometry(read, capacity):
    mbr = read(0)
    entry = mbr[446:462]
    first, size = u32(entry, 8), u32(entry, 12)
    if (
        mbr[510:] != b"\x55\xaa"
        or entry[0] not in (0, 128)
        or entry[4] not in (11, 12)
        or first == 0
        or size == 0
        or first + size > capacity
    ):
        raise ValueError("expected FAT32 in primary partition 1 of the MBR (type 0x0B or 0x0C)")
    vbr = read(first)
    for sector in (mbr, vbr):
        if sector[0x17C:0x180] in (b"Prop", b"ProP"):
            raise ValueError("card has a higher-priority P2 boot record")
    vol = boot(vbr, first, size)
    if not vol or vol["fat_bits"] != 32 or vol["root_cluster"] != 2 or vbr[16] != 2:
        raise ValueError(
            "ROM directory boot needs FAT32, 512-byte sectors, two FATs and root cluster 2"
        )
    fs = read(first + u16(vbr, 48))
    if u32(fs, 0) != 0x41615252 or u32(fs, 484) != 0x61417272 or fs[510:] != b"\x55\xaa":
        raise ValueError("invalid FAT32 FSInfo sector")
    return vol


def locate(read, vol, size):
    spc = vol["sectors_per_cluster"]
    for sector in range(vol["data_start"], vol["data_start"] + spc):
        data = read(sector)
        for pos in range(0, 512, 32):
            entry = data[pos : pos + 32]
            if not entry[0]:
                raise ValueError("boot file is absent from the first root cluster")
            if entry[:11] != SHORT_NAME or entry[11] & 0xD8:
                continue
            if u32(entry, 28) != size:
                raise ValueError("existing boot file has a different size")
            cluster = u16(entry, 20) << 16 | u16(entry, 26)
            count = (size + spc * 512 - 1) // (spc * 512)
            if not 2 <= cluster or cluster + count > vol["clusters"] + 2:
                raise ValueError("boot file extends outside the partition")
            for number in range(cluster, cluster + count):
                link = u32(read(vol["fat_start"] + number // 128), 4 * (number % 128)) & 0x0FFFFFFF
                if number + 1 == cluster + count:
                    if link < 0x0FFFFFF8:
                        raise ValueError("boot file has an unexpected FAT chain terminator")
                elif link != number + 1:
                    raise ValueError("boot file is fragmented; ROM reads consecutive sectors")
            return vol["data_start"] + (cluster - 2) * spc
    raise ValueError("boot file lies outside the directory range scanned by the ROM")


def main():
    from mpremote.transport_serial import SerialTransport

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="P2 RAM serial relay")
    parser.add_argument("--image", type=Path, required=True, help="P2 flat image or ELF")
    parser.add_argument("--install", action="store_true", help="create _BOOT_P2.BIX if absent")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    image, _ = read_image(args.image)
    if not image or len(image) > 496 * 1024 or len(image) % 4:
        parser.error("boot image must be long-aligned and fit the ROM's 496 KiB window")
    if args.output.exists():
        parser.error("choose a new result path")
    record = {
        "path": BOOTFILE,
        "bytes": len(image),
        "sha256": hashlib.sha256(image).hexdigest(),
        "passed": False,
        "rom_boot_observed": False,
    }
    board = SerialTransport(args.port)
    created = False
    try:
        board.enter_raw_repl(soft_reset=True)
        board.exec("""import os,p2sd
sd=p2sd.active()
assert sd is not None and sd.ioctl(5,0)==512""")
        capacity = int(board.exec("print(sd.ioctl(4,0))"))

        def sectors(index, count=1):
            return read_sectors(board, index, count)

        from functools import lru_cache

        read = lru_cache(maxsize=128)(sectors)
        vol = geometry(read, capacity)
        try:
            board.fs_stat(BOOTFILE)
        except OSError as exc:
            if exc.errno != 2 or not args.install:
                raise
            # Claim the exact root name exclusively before opening it for bulk writes.
            board.exec(f"with open({BOOTFILE!r},'xb'): pass")
            created = True
            board.fs_writefile(BOOTFILE, image, chunk_size=1024)
            board.exec("assert sd.ioctl(3,0)==0")
        read.cache_clear()
        first = locate(read, vol, len(image))
        digest = hashlib.sha256()
        for pos in range(0, len(image), 4096):
            length = min(4096, len(image) - pos)
            digest.update(sectors(first + pos // 512, (length + 511) // 512)[:length])
        if digest.hexdigest() != record["sha256"]:
            raise ValueError("raw contiguous sectors differ from the requested image")
        record.update(
            passed=True, created=created, first_lba=first, sectors=(len(image) + 511) // 512
        )
    except BaseException as exc:
        record["error"] = repr(exc)
        if created:
            board.enter_raw_repl(soft_reset=True)
            board.exec(f"import os; os.remove({BOOTFILE!r})")
        raise
    finally:
        board.close()
        with args.output.open("x", encoding="utf-8") as out:
            json.dump(record, out, indent=2)
        print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
