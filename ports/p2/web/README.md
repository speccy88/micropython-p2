# P2 Web Serial workbench

The workbench runs entirely in the browser. Desktop Chrome and Edge can load one of the three release profiles, start ViperIDE on the same open serial port, and run a first script over the REPL. Existing MicroPython installations have a connect-only entry point. Visitors can also open the editor without granting USB access. [Open the workbench](https://speccy88.github.io/micropython-p2/)

To try hardware pin callbacks with `machine.Pin.irq()`, select **Edge IRQ** for the 32 MiB board or **Lean IRQ** for the plain Edge. These two choices are RAM-only. The site builder checks both binaries against the hardware acceptance hashes before packaging them. [Pin IRQ guide](../IRQ.md) · [Tested builds and hashes](../validation/irq/builds.json)

With a prepared FAT32 card inserted, open **Can I boot my SD card?** and
select **Boot SD & open ViperIDE**. The workbench resets the board into its
serial ROM monitor, requests `R_BOOT_P2.BIX`, and hands the open port to
the editor once MicroPython answers. On Windows, desktop Chrome ran the editor's first script on COM12 and printed `External RAM: 32 MiB`. [Board run](../validation/sd-kit3-browser.json) · [Preparing the card](../storage/ACCEPTANCE.md#boot-the-interpreter-from-sd)

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

RAM and boot-flash uploads use **2,000,000 baud**, 8N1. The browser sends Base64 through the P2 ROM's `Prop_Txt` command. On the test Edge and FTDI adapter on COM12, the 403,960-byte Edge image transferred in 2.73 and 2.89 seconds using the Python loader. The same image took 5.87 seconds at 921,600 baud. Browser setup and flash programming take additional time.

- **RAM** waits for the ROM's checksum acknowledgement.
- **Boot flash** checks the programmer and image before transmission. The final `~` starts programming. Keep power connected. Once the final page clears BUSY, the programmer sends `P2OK` at 2 Mbaud. The browser waits for this marker before changing baud.
- **SD boot** and **Connect to the IDE** open directly at the console speed of **115,200 baud**.

After an upload, Web Serial releases its stream locks and reopens the same adapter at console speed. The workbench checks the P2 MicroPython REPL and hands that open connection to ViperIDE. For an adapter that needs a lower transfer speed, the current command-line RAM and flash tools accept `--baud 921600` or `--baud 115200`.

The web-only programmer can be rebuilt from `ports/p2/tools/loadp2` with `flexspin -2 -c -D WEB_FAST_UPLOAD -o flash_loader_2m.bin flash_loader.spin2` (FlexSpin source revision `6d371da09a7680cec7ace00d85672d6d3e5b1e42`). Omitting the define reproduces the original 496-byte programmer. The browser variant adds a serial completion message to the downloaded programmer; the Python firmware installed in flash keeps its release bytes.

## Sources and licenses

The workbench and P2 integration use the MIT license. ViperIDE and its dependencies keep their upstream notices. The deployed site includes a license index. [Workbench license](LICENSE) · [Pinned ViperIDE source](https://github.com/vshymanskyy/ViperIDE/tree/6bbfb5036248312b8b2b4e7d81735acedaa8c9b6) · [Firmware sources and credits](../SOURCES.md)

The USB reset and base64 protocol were checked against the supplied Propeller Bench implementation, this port's RAM loader, and the loadp2 programmer. The site ships the published MicroPython images and the loadp2-derived programmer. [RAM loader](../tools/p2ram.py) · [loadp2 license](../tools/loadp2/LICENSE)

The board selector uses supplied Parallax product photos of the [plain P2 Edge](https://www.parallax.com/products/p2-edge-module/) and the [32 MB Edge](https://www.parallax.com/products/p2-edge-module-with-32mb-ram). The workbench and editor use the navy, white and pale blue from [Parallax](https://www.parallax.com/). The editor's welcome tab loads the repository README bundled with each Pages deployment.
