"""Physical Edge media acceptance. Supply a designated FAT directory or one scratch NOR sector."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import secrets

SECTOR = 4096
FLASH_BYTES = 16 * 1024 * 1024
BOOT_RESERVE = 1024 * 1024


def scratch_address(text):
    start = int(text, 0)
    if not BOOT_RESERVE <= start <= FLASH_BYTES - SECTOR or start % SECTOR:
        raise argparse.ArgumentTypeError(
            "select an aligned 4096-byte sector above the boot reservation"
        )
    return start


def sd_directory(text):
    p = PurePosixPath(text)
    if p.root != "/" or ".." in p.parts or "\\" in text or ":" in text or "\0" in text:
        raise argparse.ArgumentTypeError("supply an absolute path on the FAT root without '..'")
    return str(p)


def check_sd(board, directory):
    path = str(PurePosixPath(directory) / ("P2" + secrets.token_hex(3).upper() + ".TMP"))
    print(f"SD scratch file {path}", flush=True)
    # The raw soft reset at entry automounts the card at root and skips user boot scripts.
    board.exec("import os,p2sd,vfs\nassert p2sd.active() is not None")
    board.exec(f"assert os.stat({directory!r})[0] & 0x4000")
    board.exec(f"f=open({path!r},'xb')")  # On collision, leave the existing file alone.
    try:
        board.exec(
            """try:
 assert f.write(bytes(range(251))*5) == 1255
 f.flush()
finally:
 f.close()
"""
        )
        board.exec(
            f"""try:
 with open({path!r},'r+b') as handle:
  handle.seek(247)
  assert handle.write(b'cross-256-boundary') == 18
  raise ValueError('acceptance exception')
except ValueError as e:
 assert e.args == ('acceptance exception',)
dirty=open({path!r},'ab')
assert dirty.write(b'reset-tail') == 10
"""
        )
        # Leave the dirty file open; the firmware must close/sync it during a raw soft reset.
        board.enter_raw_repl(soft_reset=True)
        board.exec("import os,p2sd,vfs\nsd=p2sd.active()\nassert sd is not None")
        board.exec(
            """vfs.umount('/')
if p2sd.active() is not None:
 assert sd.ioctl(2,0)==0
sd=p2sd.SDCard()
vfs.mount(vfs.VfsFat(sd),'/')"""
        )
        board.exec(
            f"""expected=bytearray(bytes(range(251))*5)
expected[247:265]=b'cross-256-boundary'
with open({path!r},'rb') as handle:
 assert handle.read()==expected+b'reset-tail'
assert sd.ioctl(3,0)==0"""
        )
    finally:
        # A second raw reset also releases dirty handles if a test failed midway.
        board.enter_raw_repl(soft_reset=True)
        board.exec(f"import os,p2sd\nassert p2sd.active() is not None\nos.remove({path!r})")
        board.exec("assert p2sd.active().ioctl(3,0)==0")
    return {"directory": directory, "file": path, "verified_bytes": 1265}


def check_startup(board):
    token = secrets.token_hex(3).upper()
    originals = []
    created = []
    boot_line = "P2 test boot " + token
    main_line = "P2 test main " + token
    scripts = {
        "/boot.py": f"p2_test_token={token!r}\nprint({boot_line!r})\n",
        "/main.py": f"assert p2_test_token=={token!r}\nprint({main_line!r})\n",
    }
    try:
        board.exec("import os,p2sd\nassert p2sd.active() is not None")
        for i, (path, source) in enumerate(scripts.items()):
            saved = f"/{i}{token}.BAK"
            # FAT rename refuses an existing destination. Propagate other I/O errors.
            status = board.exec(
                f"""try:
 os.stat({path!r})
except OSError as e:
 if e.args[0]!=2: raise
 print(0)
else:
 print(1)"""
            ).strip()
            if status == b"1":
                print(f"Startup recovery: {saved} belongs at {path}", flush=True)
                board.exec(f"os.rename({path!r},{saved!r})")
                originals.append((path, saved))
            elif status != b"0":
                raise RuntimeError("could not identify existing startup file")
            board.exec(f"f=open({path!r},'xb')")
            created.append(path)
            board.exec(
                f"try:\n assert f.write({source.encode()!r})=={len(source)}\nfinally:\n f.close()"
            )
        board.exit_raw_repl()
        if not board.read_until(1, b">>> ", timeout_overall=30).endswith(b">>> "):
            raise RuntimeError("friendly REPL did not appear")
        board.serial.write(b"\x04")
        result = board.read_until(1, b">>> ", timeout_overall=45)
        lines = result.decode(errors="replace").splitlines()
        if (
            boot_line not in lines
            or main_line not in lines
            or lines.index(main_line) <= lines.index(boot_line)
        ):
            raise RuntimeError("friendly reset did not run boot.py then main.py")
        board.enter_raw_repl(soft_reset=True)
        board.exec("assert 'p2_test_token' not in globals()")
    finally:
        # Even a temporary script with an error can be bypassed using raw reset.
        board.enter_raw_repl(soft_reset=True)
        board.exec("import os,p2sd\nassert p2sd.active() is not None")
        for path in reversed(created):
            board.exec(f"os.remove({path!r})")
        for path, saved in originals:
            board.exec(f"os.rename({saved!r},{path!r})")
        board.exec("assert p2sd.active().ioctl(3,0)==0")
    return {
        "friendly_order": ["boot.py", "main.py"],
        "raw_skipped": True,
        "originals_restored": len(originals),
    }


def flash_read(board):
    output = board.exec(
        "buf=bytearray(4096)\nassert flash.readblocks(0,buf)==0\nprint(bytes(buf).hex())"
    )
    data = bytes.fromhex(output.decode().strip())
    if len(data) != SECTOR:
        raise ValueError("short sector read")
    return data


def backup_content(record, start, jedec):
    data = bytes.fromhex(record["hex"])
    if (
        record["start"] != start
        or record["jedec"] != jedec
        or len(data) != SECTOR
        or record["sha256"] != hashlib.sha256(data).hexdigest()
    ):
        raise ValueError("backup address, JEDEC ID, size or checksum mismatch")
    return data


def restore_sector(board, original):
    if flash_read(board) == original:
        return
    # The device owns only the requested sector. The driver checks every erase/program command.
    board.exec("assert flash.ioctl(6,0)==0")
    for pos in range(0, SECTOR, 256):
        page = original[pos : pos + 256]
        if page != b"\xff" * len(page):
            board.exec(f"assert flash.writeblocks(0,{page!r},{pos})==0")
    board.exec("assert flash.ioctl(3,0)==0")
    if flash_read(board) != original:
        raise ValueError("scratch sector restoration failed; retain the backup")


def check_flash(board, start, backup, restore):
    board.exec(
        """import p2,p2sd,vfs
sd=p2sd.active()
if sd is not None:
 vfs.umount('/')
 if p2sd.active() is not None:
  assert sd.ioctl(2,0)==0"""
    )
    jedec = int(board.exec("print(p2.Flash.probe())").strip())
    if jedec not in (0xEF4018, 0xEF7018):
        raise ValueError("expected a supported 16 MiB W25Q128 device")
    args = f"start={start}, size={SECTOR}"
    try:
        if restore:
            original = backup_content(json.loads(backup.read_text()), start, jedec)
        else:
            board.exec(f"flash=p2.Flash({args})")
            try:
                original = flash_read(board)
            finally:
                board.exec("flash.deinit()")
            record = {
                "start": start,
                "jedec": jedec,
                "hex": original.hex(),
                "sha256": hashlib.sha256(original).hexdigest(),
            }
            with backup.open("x", encoding="ascii") as dest:
                json.dump(record, dest)
                dest.flush()
                os.fsync(dest.fileno())
            original = backup_content(json.loads(backup.read_text()), start, jedec)
        board.exec(f"flash=p2.Flash({args}, writable=True)")
        try:
            if not restore:
                try:
                    board.exec("assert flash.ioctl(6,0)==0")
                    if flash_read(board) != b"\xff" * SECTOR:
                        raise ValueError("sector erase did not read back as all ones")
                    # Cross multiple NOR program-page boundaries at an unaligned offset.
                    pattern = bytes(range(251)) * 3
                    board.exec(f"assert flash.writeblocks(0,{pattern!r},199)==0")
                    board.exec("assert flash.ioctl(3,0)==0")
                    expected = bytearray(b"\xff" * SECTOR)
                    expected[199 : 199 + len(pattern)] = pattern
                    if flash_read(board) != expected:
                        raise ValueError("page program changed unexpected bytes")
                finally:
                    restore_sector(board, original)
            else:
                restore_sector(board, original)
        finally:
            board.exec("flash.deinit()")
        board.exec(f"flash=p2.Flash({args})")
        try:
            if flash_read(board) != original:
                raise ValueError("original sector differs after reopening")
        finally:
            board.exec("flash.deinit()")
    finally:
        board.enter_raw_repl(soft_reset=True)  # Release handles and restore normal SD automount.
    return {
        "sector_start": start,
        "jedec": hex(jedec),
        "restored_sha256": hashlib.sha256(original).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="raw REPL RAM relay or serial port")
    parser.add_argument("--image", type=Path, required=True, help="image loaded for this test")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--sd-directory", type=sd_directory, help="existing expendable FAT directory"
    )
    group.add_argument(
        "--flash-sector",
        type=scratch_address,
        help="explicit expendable 4 KiB sector byte address",
    )
    backup = parser.add_mutually_exclusive_group()
    backup.add_argument(
        "--backup", type=Path, help="create a new host backup before the first NOR erase"
    )
    backup.add_argument(
        "--restore", type=Path, help="restore this saved sector after interruption"
    )
    parser.add_argument(
        "--startup",
        action="store_true",
        help="also check friendly SD boot.py/main.py and raw recovery",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    save = args.backup or args.restore
    if (args.flash_sector is not None) != bool(save):
        parser.error("a flash sector requires --backup or --restore; SD uses neither")
    if args.startup and not args.sd_directory:
        parser.error("--startup uses the designated SD, not the NOR scratch test")
    if args.output.exists() or (save and save.resolve() == args.output.resolve()):
        parser.error("choose a new result path separate from the backup")
    if args.backup and args.backup.exists():
        parser.error("choose a new backup path")
    record = {"image_sha256": hashlib.sha256(args.image.read_bytes()).hexdigest(), "passed": False}
    from mpremote.transport_serial import SerialTransport

    board = SerialTransport(args.port)
    try:
        board.enter_raw_repl(soft_reset=True)
        if args.sd_directory:
            record["sd"] = check_sd(board, args.sd_directory)
            if args.startup:
                record["startup"] = check_startup(board)
        else:
            record["flash"] = check_flash(board, args.flash_sector, save, bool(args.restore))
        record["passed"] = True
    except Exception as exc:
        record["error"] = repr(exc)
        raise
    finally:
        board.close()
        with args.output.open("x", encoding="utf-8") as out:
            json.dump(record, out, indent=2)
        print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
