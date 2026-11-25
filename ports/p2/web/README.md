# P2 Web Serial workbench

The workbench runs entirely in the browser. Desktop Chrome and Edge can load one of the three release profiles, start ViperIDE on the same open serial port, and run a first script over the REPL. Existing MicroPython installations have a connect-only entry point. Visitors can also open the editor without granting USB access. [Open the workbench](https://speccy88.github.io/micropython-p2/)

With a prepared FAT32 card inserted, open **Can I boot my SD card?** and
select **Boot SD & open ViperIDE**. The workbench resets the board into its
serial ROM monitor, requests `R_BOOT_P2.BIX`, and hands the open port to
the editor once MicroPython answers. [Preparing the card](../storage/ACCEPTANCE.md#boot-the-interpreter-from-sd)

## Build a local copy

Use a clean checkout of this repository, Git, Node 24, and Python 3.12. The commands below work in a POSIX shell, including WSL. Use a fresh output directory. The directory name under `_site` matches the URL path compiled into ViperIDE.

```sh
python -m venv .venv-pages
. .venv-pages/bin/activate
python -m pip install python-minifier==3.2.0
git clone https://github.com/vshymanskyy/ViperIDE.git _vendor/viper
git -C _vendor/viper checkout --detach 6bbfb5036248312b8b2b4e7d81735acedaa8c9b6
git -C _vendor/viper apply "$(pwd)/ports/p2/web/viper-p2.patch"
(cd _vendor/viper && npm ci && VIPER_IDE_BASE_URL=/micropython-p2/ide python build.py --skip-tests)
node --test ports/p2/web/rom.test.mjs
python ports/p2/web/build_site.py _vendor/viper _site/micropython-p2
python -m http.server 8000 --bind 127.0.0.1 --directory _site
```

Open `http://localhost:8000/micropython-p2/`. Web Serial requires HTTPS or a loopback origin. The Pages workflow repeats the build and publishes its artifact on changes to the workbench or release images. [Deployment workflow](../../../.github/workflows/p2-pages.yml)

## How a transfer works

The click opens the browser's native port chooser. The workbench verifies the selected binary's SHA-256, opens the adapter at 115200 baud, pulses DTR and waits for the P2 ROM's silicon identifier. Data travels in unpadded base64 using `Prop_Txt`.

- **RAM** appends the ROM checksum, requests verification with `?`, and waits for both the positive acknowledgement and the MicroPython banner.
- **Boot flash** sends the self-checksummed programmer built by the port's existing Python tool. Only the final `~` starts the programmer. At that point the page asks the user to keep power connected and waits for MicroPython to start. A reset with flash boot selected checks persistence. [Programmer source](../tools/flash_boot.py)

Once Python starts, the loader releases its stream locks and hands the open port to the same-origin ViperIDE frame. A second open can reset a Prop Plug board and lose the RAM session. The bundled example runs through the raw REPL and does not need a writable filesystem.

## Sources and licenses

The workbench and P2 integration use the MIT license. ViperIDE and its dependencies keep their upstream notices. The deployed site includes a license index. [Workbench license](LICENSE) · [Pinned ViperIDE source](https://github.com/vshymanskyy/ViperIDE/tree/6bbfb5036248312b8b2b4e7d81735acedaa8c9b6) · [Firmware sources and credits](../SOURCES.md)

The USB reset and base64 protocol were checked against the supplied Propeller Bench implementation, this port's RAM loader, and the loadp2 programmer. The site ships the published MicroPython images and the pinned loadp2 stub. [RAM loader](../tools/p2ram.py) · [loadp2 license](../tools/loadp2/LICENSE)
