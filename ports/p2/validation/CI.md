# P2 continuous integration

The check to require on pull requests is **P2 host checks**. It runs on every pull request targeting `main` and every push to `main`, including documentation-only changes. Feature branches use pull requests to get validation. Concurrency cancels superseded checks for the same ref. At the audit, GitHub returned no branch protection, required status contexts or active rules for `main`.

| Workflow | When it runs | Coverage |
| --- | --- | --- |
| `p2-checks.yml` | Main push, pull request to main, manual | Pinned Ruff, codespell and MicroPython's C formatter. Builds mpy-cross, tests the P2 Python packages, compiles examples, exercises the binary REPL socket and Web Serial model, and runs the real NOR command engine against host LittleFS. Checks release binaries and kit contents and compiles a module with the archived Linux compiler. The Actions summary lists flat size, GC arena and primary stack for every release profile. |
| `ports_unix.yml` | Matching shared-core, library, mpy-cross, Unix, package or test changes on main/PR, manual | One native Linux standard interpreter. Runs upstream basics, float and import tests, imports freshly compiled bytecode and exercises the array API with a file-backed external-memory model. The former cross/emulation, coverage, alternate configuration and sanitizer matrices were removed. |
| `p2-pages.yml` | Main changes to the workbench, published firmware or loader, manual | Builds and deploys the hosted P2 installer and ViperIDE. |
| `p2-firmware.yml` | Manual | Rebuilds Edge, Lean and Threaded on Ubuntu from the SDK revision and compiler overlay used by the port. Caches the relocatable compiler, headers and target runtime sources by runner OS, revisions and SHA-256 of the lockfile, patches and build scripts. Every run retests the compiler, builds fresh firmware and uploads the images, ELFs and maps. |
| `p2-kit-platforms.yml` | Manual before release | Windows, macOS and Linux package and extract the kit into a path with spaces, check its host tools and exercise package APIs. Linux also runs the bundled x86-64 compiler. |

## What the earlier failures measured

GitHub ran 25 repository workflows on `dda022a0c`, excluding Dependabot. The audit used GitHub's job logs and job conclusions. The following changes remove automatic triggers from the fork and preserve the inherited definitions in Git history. [Audited workflow tree](https://github.com/speccy88/micropython-p2/tree/dda022a0ca69d93462dea477ae74512bb308af36/.github/workflows)

| Deleted workflow files | Findings and disposition |
| --- | --- |
| `ports_{alif,cc3200,esp32,esp8266,mimxrt,nrf,psoc-edge,renesas-ra,rp2,samd,stm32,webassembly,windows,zephyr}.yml`, `ports_qemu.yml` | These target other boards, runtimes and emulators. PSoC Edge failed looking for system pip3. SAMD overflowed its board's flash by 708 bytes. QEMU failed compiling Berkeley DB for unrelated architectures. The failing Unix jobs tried to install an unavailable qemu-user-static package. [PSoC](https://github.com/speccy88/micropython-p2/actions/runs/45544042965) · [SAMD](https://github.com/speccy88/micropython-p2/actions/runs/45544042976) · [QEMU](https://github.com/speccy88/micropython-p2/actions/runs/45544043190) · [Unix](https://github.com/speccy88/micropython-p2/actions/runs/45544043155) |
| `code_size.yml`, `code_size_comment.yml` | Both sides of the upstream PR reporting pipeline were removed. P2 validation reports this port's own sizes in the job summary and needs read-only repository access. |
| `ruff.yml`, `codespell.yml`, `code_formatting.yml` | Ruff identified 62 files for formatting. The C formatter produced differences in P2 code and shared NLR. The spell checker flagged the NOR write-enable latch variable and a third-party Spin2 mnemonic. The maintained sources now use the project formatters, the model names the latch explicitly, and vendor material keeps upstream spelling. [Ruff](https://github.com/speccy88/micropython-p2/actions/runs/45544043193) · [C](https://github.com/speccy88/micropython-p2/actions/runs/45544043064) · [Spelling](https://github.com/speccy88/micropython-p2/actions/runs/45544043240) |
| `mpremote.yml`, `mpy_format.yml` | Wheel packaging required upstream version tags absent from this fork. Users install the standard mpremote package. The P2 and shared Unix checks build mpy-cross and validate bytecode directly. [mpremote packaging log](https://github.com/speccy88/micropython-p2/actions/runs/45544043047) |
| `ports.yml`, `docs.yml`, `examples.yml`, `commit_formatting.yml`, `biome.yml` | Upstream download metadata, its full documentation build, generic examples, commit-message convention and general JS scan. P2 examples, documents, host code and website have their own scoped checks. |

The GitHub API confirmed disabling all 27 retired workflows for this repository before the cleanup push. Their YAML has been removed to keep those triggers absent in future checkouts.

## Run the checks

Install the versions listed in `p2-checks.yml`, then run `python ports/p2/ci/quality.py` from a checkout containing the v1.29.0 base commit. Use `--fix` to apply formatting. The script selects tracked P2 sources and shared files changed since the upstream release. Firmware, vendor notices and the original loadp2 sources keep their published bytes.

Select **Actions → Rebuild P2 firmware → Run workflow** for a clean toolchain-backed build, or **Starter kit on desktop hosts** for the release matrix. Physical acceptance uses the USB host and the board procedures. Hosted runners exercise only host programs, fixtures and firmware builds. [Hardware validation](../PROGRESS.md)
