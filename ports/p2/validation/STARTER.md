# Starter kit integrity

The original kit.1 ZIP downloaded from the release is 1,288,579 bytes, SHA-256
`f39e3e9a193814f43baa3c17fe575818ea0d7f983d8e44cc9ba8cd2bf7cea4be`.
The three flat images match the firmware manifest. Git normalized CRLF byte
pairs inside the following four binaries before creating the ZIP.

| File | Bytes in kit.1 | Original bytes | Original SHA-256 |
| --- | ---: | ---: | --- |
| edge.elf | 545736 | 545744 | 00af7d1acb3bbf2673c4f48a0b3fbce05b27234b2a11f2e361c8a6cfa6cef334 |
| lean.elf | 322216 | 322224 | b7a5a97a891f3426a0967a5bad15a8a1df832448c03f793c13a47cfa1d2b49d0 |
| threaded.elf | 306467 | 306476 | b01f145729824abd19e144302d3f98fd06dfffea31e7ad666d6ba30d4a006ec1 |
| mpy-cross-linux-x86_64 | 444617 | 444624 | 4c86414b1d66b6fcf1bbfd17fa9df6f118a47f86b0766090a3801b15272f6e68 |

Recovery commit `88a0c3fe1` restores all four blobs from retained outputs of
source `8432dcbac3aacf072f3b32c424dc4f0c4517f58a`. Each matched the
original manifest before staging, including the compiler from the Linux build
and the ELFs from the verified profile builds. P2 ELFs, driver images and
the extensionless compiler now have Git binary attributes. Linux Info-ZIP
extracted the compiler as mode 0755, and it compiled a bytecode v6 module
under x86-64 WSL. The current hashes for all profiles live in the
[firmware manifest](../firmware/manifest.json).

Kit.2 supersedes kit.1 and packages the three profiles built from
`ee618817ca5a2f119cabdc8ef567ccdf012ed85d`. The full Edge flat image is
403,960 bytes. Its SHA-256 is
`7a44cce09e27e658486701ca70d473c9a4fdcb730eab4438ecf75fd3fbe89052`.
All six firmware files and the Linux compiler matched the original Linux
build outputs, the Git blobs in `4a1cc18c9`, and an independent Windows
checkout with `core.autocrlf=true`. Building a kit from that checkout
produced byte-for-byte identical output to building it from the development
checkout at the same commit. The extracted Linux compiler emits .mpy v6.3.
[Replacement release and download checksums](https://github.com/speccy88/micropython-p2/releases/tag/v1.29.0-p2.1-kit.2)

The published kit.2 ZIP is 1,428,023 bytes. Its SHA-256 is
`002e5429ab9aef58ddd1e593184daa5765f33ba6ccd796c33bb2852008571a85`.
An anonymous download matched the local archive byte for byte. Its Linux
compiler built a module that the physical Edge imported from a PSRAM filesystem
and ran on COM12, returning `1938`.
[Downloaded assets and member hashes](release-kit2-download.json) · [Board import](release-kit2-board.json)

## Starter kit 3

Kit.3 ships the verified SD installer, ROM boot instructions and a Smart Pin
counter that the experimental Python worker can read. Its three firmware
profiles and Linux compiler have the same bytes as kit.2. On GitHub, the
1,444,063-byte ZIP has SHA-256
`f35366dafcc0f85d95baa30ef5ecc65c80b0d4b6cd9ad39a01db3df88a20d0fc`.
Both public assets matched the copies built from tag `4364cc9fe` in a fresh
Windows checkout. The Linux compiler from the download produced the same
bytecode as the module that returned `1938` on the physical Edge.
[Release and downloads](https://github.com/speccy88/micropython-p2/releases/tag/v1.29.0-p2.1-kit.3) Â· [Per-file checksums and compiler test](release-kit3-download.json)

Windows, macOS and Ubuntu runners downloaded the published ZIP, checked its
checksum and manifest, extracted it into a path containing a space, and ran
the host tools and driver tests. Ubuntu also compiled a module with the
packaged Linux x86-64 executable. To repeat these checks, select the kit tag
in the manual **Starter kit on desktop hosts** workflow and enable **Download
and test the release assets attached to the selected tag**.
[Three-host download test](https://github.com/speccy88/micropython-p2/actions/runs/45612686039)

## Verify a download

Compare the ZIP hash to `SHA256SUMS.txt` using `sha256sum -c SHA256SUMS.txt`
on Linux, `shasum -a 256 -c SHA256SUMS.txt` on macOS, or
`Get-FileHash micropython-p2-starter.zip -Algorithm SHA256` in PowerShell.
From a source checkout, the following checks the archive CRCs, expected
members, every firmware size and SHA-256, compiler mode and pinned flash loader.

```sh
python ports/p2/tools/make_starter.py --verify micropython-p2-starter.zip
```

Inside an extracted kit, use `python ports/p2/tools/make_starter.py --check-files`.
Download the replacement if verification fails. [Releases](https://github.com/speccy88/micropython-p2/releases)

## Compare original and candidate builds

Use separate Linux build directories, a path without spaces, and the verified
LLVM overlay. Set `P2_BIN` and `P2_WORK` as in the [toolchain guide](../toolchain/README.md).
The following rebuilds the original code used by kit.1 alongside the selected
candidate. Pass the precise candidate **firmware source commit** from its
manifest. To reproduce the original embedded build date, the port's build
script derives `SOURCE_DATE_EPOCH` from that checkout.
Kit.2 froze the five port modules in the order returned by the original
Linux filesystem. The release metadata now pins a second commit for that
one build recipe. GitHub's manual rebuild restores only `ports/p2/manifest.py`
from that commit. The reference and candidate keep their original sources
and version headers.

```sh
baseline=8432dcbac3aacf072f3b32c424dc4f0c4517f58a
candidate=$(python -c 'import json; print(json.load(open("ports/p2/firmware/manifest.json"))["source_commit"])')
recipe=$(python -c 'import json; print(json.load(open("ports/p2/firmware/manifest.json")).get("frozen_manifest_commit", ""))')
for variant in baseline candidate; do
    if [ "$variant" = baseline ]; then revision=$baseline; else revision=$candidate; fi
    folder="$(pwd)/../p2-ab-$variant"
    git worktree add --detach "$folder" "$revision" || exit 1
    if [ "$variant" = candidate ] && [ -n "$recipe" ]; then
        git -C "$folder" restore --source="$recipe" --worktree -- ports/p2/manifest.py || exit 1
    fi
    git -C "$folder" submodule update --init --depth 1 lib/micropython-lib || exit 1
    (cd "$folder" && bash ports/p2/tools/build_profiles.sh edge lean threaded) || exit 1
    python ports/p2/tools/package.py "$folder/ports/p2/build-delivery" --repo "$folder" --output "$folder/ports/p2/build-packaged" || exit 1
done
```

Keep benchmark code, board, clock, compiler revision and flags fixed when
comparing software changes. To check the actual release kit, build it from
the intended release commit rather than from a directory of loose binaries.

```sh
python ports/p2/tools/make_starter.py dist
python ports/p2/tests/test_starter.py
python ports/p2/tests/kit_mpy.py dist/micropython-p2-starter.zip
```

The last command runs on x86-64 Linux. On Windows add `--wsl`. With the
matching Edge image loaded and standard mpremote installed, add
`--port socket://127.0.0.1:8122 --output kit-mpy.json` to copy the compiled
module to a fresh PSRAM filesystem, import it and check the result on the P2.
