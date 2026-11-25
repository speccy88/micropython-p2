# Parallax P2 Edge

Use `make BOARD=P2_EDGE PROFILE=lean all`. This target expects a 20 MHz clock
reference, configures the PLL for 160 MHz and leaves P40–P57 available to
GPIO/Smart Pins. P58–P61 are reserved for shared storage and P62/P63 for the
serial console. Configure an external SD carrier's alternate pins explicitly
when its wiring differs. Board revisions and carriers differ in clock-source
packaging and storage wiring.
[Parallax product guide](https://www.parallax.com/package/p2-edge-module-product-guide/)
and [Rev A/C/D schematics](https://www.parallax.com/package/p2-edge-module-schematics/).

The connected COM12 device is the 32 MiB variant. Running a plain-profile image
on it tests the image startup and VM but cannot establish electrical behavior
of a separate plain Edge. Its PSRAM pins remain physically wired on the
connected module, so use the EC32MB configuration there.
