# Parallax P2-EC32MB

Use `make BOARD=P2_EC32MB PROFILE=edge all`. The native startup configures a
20 MHz reference and 160 MHz system clock. The product page specifies a
20 MHz TCXO on the listed module revision. The ROM silicon response and
PSRAM IDs identify the working target, but cannot distinguish a crystal from
a TCXO or identify the printed circuit board revision remotely.
[Product specifications](https://www.parallax.com/products/p2-edge-module-with-32mb-ram)
and [Rev A/B schematics](https://www.parallax.com/package/p2-edge-module-with-32mb-ram-schematic/).

The accepted COM12 board returned `Prop_Ver G` and `0d 5d` from each of four
striped PSRAM devices. P40–P55 carry their four quad-data lanes, P56 is clock
and P57 chip select. P58–P61 are shared flash and SD. P62/P63 are console TX/RX.
Leave these reserved pins under their owning drivers. General examples default
to P0–P13. Exact carrier model and silkscreen revision require visual inspection.
[Physical capture](../../validation/drivers-probe.json)
