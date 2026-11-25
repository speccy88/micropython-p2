"""Small serial REPL line editor for bounded UTF-8 text files."""

import os
import sys

LIMIT = 4096
MAX_LINES = 256


def _readline(prompt):
    # The core-features P2 build provides stdin/stdout but omits builtins.input.
    print(prompt, end="")
    line = bytearray()
    overflow = False
    while True:
        key = sys.stdin.buffer.read(1)
        if not key or key == b"\x04":
            raise EOFError
        if key == b"\x03":
            raise KeyboardInterrupt
        if key in (b"\r", b"\n"):
            if overflow:
                print("\nCommand too long; nothing changed")
                print(prompt, end="")
                line = bytearray()
                overflow = False
                continue
            if not line:
                continue
            print()
            try:
                return line.decode()
            except UnicodeError:
                print("Invalid UTF-8; nothing changed")
                print(prompt, end="")
                line = bytearray()
                continue
        if overflow:
            continue
        if key in (b"\x08", b"\x7f"):
            if line:
                while line and line.pop() & 0xC0 == 0x80:
                    pass
                sys.stdout.write("\b \b")
        elif key[0] >= 32:
            if len(line) >= LIMIT + 12:
                overflow = True
            else:
                line.extend(key)
                sys.stdout.buffer.write(key)


def _exists(path):
    try:
        os.stat(path)
    except OSError as exc:
        if exc.args[0] == 2:
            return False
        raise
    return True


def _save(path, lines):
    tmp = path + ".new"
    backup = path + ".bak"
    if _exists(tmp) or _exists(backup):
        raise OSError("Recover or rename " + tmp + " and " + backup + " before saving")
    f = open(tmp, "xb")
    try:
        with f:
            for line in lines:
                data = (line + "\n").encode()
                if f.write(data) != len(data):
                    raise OSError("short write to " + tmp)
            f.flush()
    except OSError:
        # The previous file is intact and this incomplete temp belongs to us.
        os.remove(tmp)
        raise
    had_file = _exists(path)
    if had_file:
        os.rename(path, backup)
    try:
        os.rename(tmp, path)
    except OSError:
        if had_file:
            os.rename(backup, path)
        os.remove(tmp)
        raise
    if had_file:
        try:
            os.remove(backup)
        except OSError:
            print("Saved. The previous version remains at", backup)


def edit(path):
    """Edit an absolute path in a mounted writable volume using the friendly REPL."""
    if not path.startswith("/") or path.endswith("/"):
        raise ValueError("supply an absolute file path")
    lines = []
    size = 0
    if _exists(path):
        with open(path, "rb") as f:
            raw = f.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise ValueError("file exceeds 4096 bytes")
        if raw.count(b"\n") + int(bool(raw) and not raw.endswith(b"\n")) > MAX_LINES:
            raise ValueError("file exceeds 256 lines")
        lines = raw.decode().replace("\r\n", "\n").split("\n")
        if lines[-1] == "":
            lines.pop()
        size = sum(len(s.encode()) + 1 for s in lines)
        del raw
    print("a TEXT append | r N TEXT replace | d N delete | p print | w save | q quit")
    while True:
        cmd = _readline("edit> ")
        if cmd == "p":
            for n, line in enumerate(lines):
                print(n + 1, line)
        elif cmd == "q":
            return False
        elif cmd == "w":
            if size > LIMIT:
                print("File exceeds 4096 bytes")
                continue
            try:
                _save(path, lines)
            except OSError as exc:
                print("Save failed; edits are still in memory:", exc)
            else:
                return True
        elif cmd == "a" or cmd.startswith("a "):
            line = cmd[2:]
            extra = len(line.encode()) + 1
            if size + extra > LIMIT or len(lines) >= MAX_LINES:
                print("File limit reached")
                continue
            lines.append(line)
            size += extra
        elif cmd.startswith("r ") or cmd.startswith("d "):
            parts = cmd.split(" ", 2)
            try:
                i = int(parts[1]) - 1
            except ValueError:
                i = -1
            if i < 0 or i >= len(lines):
                print("No such line")
                continue
            old = len(lines[i].encode()) + 1
            if parts[0] == "d" and len(parts) == 2:
                del lines[i]
                size -= old
            elif parts[0] == "r":
                line = parts[2] if len(parts) == 3 else ""
                change = len(line.encode()) + 1 - old
                if size + change > LIMIT:
                    print("File limit reached")
                    continue
                lines[i] = line
                size += change
            else:
                print("Use d N")
        else:
            print("Unknown command")
