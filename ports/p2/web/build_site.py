"""Assemble the static P2 workbench from a built ViperIDE checkout and release images."""
# SPDX-License-Identifier: MIT
import argparse
import hashlib
import html
import json
import shutil
import struct
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from urllib.parse import quote

WEB = Path(__file__).resolve().parent
PORT = WEB.parent
ROOT = PORT.parents[1]
VIPER_COMMIT = "6bbfb5036248312b8b2b4e7d81735acedaa8c9b6"
sys.path.insert(0, str(PORT / "tools"))
from flash_boot import programmer


def write_firmware(dest):
    dest.mkdir()
    manifest = json.loads((PORT / "firmware/manifest.json").read_text())
    index = {"version": manifest["upstream_release"], "profiles": {}}
    for profile, release in manifest["profiles"].items():
        flat = release["flat"]
        image = (PORT / "firmware" / flat["file"]).read_bytes()
        flash = programmer(profile)  # Also verifies the pinned loadp2 stub and release SHA.
        if len(image) != flat["bytes"] or sum(w[0] for w in struct.iter_unpack("<I", flash)) & 0xffffffff:
            raise ValueError(f"Invalid {profile} image")
        (dest / flat["file"]).write_bytes(image)
        filename = f"{profile}-flash.bin"
        (dest / filename).write_bytes(flash)
        index["profiles"][profile] = {
            "ram": flat,
            "flash": {"file": filename, "bytes": len(flash), "sha256": hashlib.sha256(flash).hexdigest()},
        }
    (dest / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")


def write_notices(viper, dest):
    dest.mkdir()
    items = []

    def add(name, source, target):
        shutil.copyfile(source, dest / target)
        items.append(f'<li><a href="{quote(target)}">{html.escape(name)}</a></li>')

    add("P2 workbench (MIT)", WEB / "LICENSE", "workbench.txt")
    add("MicroPython and bundled components", ROOT / "LICENSE", "micropython.txt")
    add("TinyGo/P2 runtime and drivers", PORT / "runtime/LICENSE.tinygo-p2", "tinygo-p2.txt")
    add("loadp2 flash programmer", PORT / "tools/loadp2/LICENSE", "loadp2.txt")
    for filename, title in {
        "compiler-rt.txt": "LLVM compiler-rt",
        "littlefs.txt": "littlefs",
        "p2llvm.txt": "P2 LLVM support",
        "propeller-libc.txt": "Propeller C library",
    }.items():
        add(title, WEB / "notices" / filename, filename)
    # The FAT license lives in the source header. Preserve it with the binary.
    fat_source = (ROOT / "lib/oofatfs/ff.c").read_text(encoding="utf-8")
    header = fat_source[:fat_source.index("#include")].strip()
    (dest / "oofatfs.txt").write_text(header + "\n", encoding="utf-8")
    items.append('<li><a href="oofatfs.txt">ooFatFs / FatFs</a></li>')
    add("ViperIDE (MIT)", viper / "LICENSE", "viperide.txt")
    minifier = metadata.distribution("python-minifier")
    for entry in minifier.files or []:
        if entry.name.upper().startswith("LICENSE"):
            add("Python Minifier", minifier.locate_file(entry), "python-minifier.txt")
            break
    else:
        raise ValueError("Install python-minifier==3.2.0 to include its license.")

    lock = json.loads((viper / "package-lock.json").read_text())
    for path, pkg in sorted(lock["packages"].items()):
        directory = viper / path
        if not path or pkg.get("dev") or not directory.is_dir():
            continue
        label = path.rsplit("node_modules/", 1)[-1] + " " + pkg.get("version", "")
        licenses = sorted(p for p in directory.iterdir() if p.is_file() and
                          p.name.upper().startswith(("LICENSE", "LICENCE", "COPYING", "NOTICE", "OFL")))
        if licenses:
            for license_file in licenses:
                target = path.replace("/", "_").replace("@", "") + "-" + license_file.name + ".txt"
                add(label + " — " + license_file.name, license_file, target)
        else:
            items.append(f'<li>{html.escape(label)} ({html.escape(str(pkg.get("license", "see source package")))})</li>')
    page = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Licenses · P2 Workbench</title>
<link rel="stylesheet" href="../style.css"><main class="wrap"><p><a href="../">← Workbench</a></p>
<h1>Licenses and credits</h1><p>The installer is MIT licensed. ViperIDE, the firmware and their
dependencies retain their own notices. This list includes packages from the IDE's production lockfile.</p>
<p><a href="https://github.com/vshymanskyy/ViperIDE">ViperIDE source</a> ·
<a href="https://github.com/speccy88/micropython-p2/blob/main/ports/p2/SOURCES.md">Firmware credits</a></p>
<ul>""" + "\n".join(items) + "</ul></main></html>\n"
    (dest / "index.html").write_text(page, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("viper", type=Path, help="Patched and built ViperIDE checkout")
    parser.add_argument("output", type=Path, help="New or empty destination directory")
    args = parser.parse_args()
    head = subprocess.check_output(["git", "-C", str(args.viper), "rev-parse", "HEAD"], text=True).strip()
    build = args.viper / "build"
    if head != VIPER_COMMIT or "connectInstalledP2" not in (build / "index.html").read_text(encoding="utf-8"):
        parser.error("Build the pinned ViperIDE source with viper-p2.patch applied.")
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        parser.error("Use an empty output directory.")
    for name in ("index.html", "style.css", "app.mjs", "rom.mjs"):
        shutil.copyfile(WEB / name, out / name)
    ide = out / "ide"
    ide.mkdir()
    for name in ("index.html", "manifest.json", "translations.json", "bridge.html", "benchmark.html", "webrepl_content.js"):
        shutil.copyfile(build / name, ide / name)
    shutil.copytree(build / "assets", ide / "assets", ignore=shutil.ignore_patterns("universal_flash_nuke.uf2", "vendors"))
    write_firmware(out / "firmware")
    write_notices(args.viper, out / "licenses")


if __name__ == "__main__":
    main()
