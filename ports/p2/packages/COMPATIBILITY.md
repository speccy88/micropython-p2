# Earlier P2 examples

The bundled source targets the native LLVM 15 ABI and the current MicroPython
object model. The optional `p2legacy` package implements a small set of LED
helpers in Python. Each open output uses one claimed Smart Pin or GPIO and
one retained handle in hub RAM, with no added cog. Call `freepin(pin)` before
switching from digital output to PWM or handing its pin to another driver.

| Original example or API | Compatibility and required edit |
| --- | --- |
| Rayman LED examples 0–1, `pinh`, `pinl`, `pint`, millisecond `delay` | Provided by `import p2legacy as p2`. Choose P0 plus an external LED/330 Ω resistor. Original SimpleP2 P52/P53 and EVAL P56/P57 are wired to PSRAM on the EC32MB and cannot be selected. |
| Rayman LED examples 2–6, `startled`, `setled` | The wrapper accepts brightness 0..255 and scales to the Smart Pin PWM duty. Example 3 can keep `time.ticks_ms`; compare wrapped counters with `time.ticks_diff`. Exact legacy PWM carrier and active-low board wiring require adaptation. |
| Team Oz `Pin(57, Pin.IN, Pin.PULL_UP).value()` | The input constructor and read are implemented. Select an available header pin on EC32MB. The pull uses the P2's nominal 15 kΩ pad drive. |
| Team Oz `Pin.Out_PP`, `p_out.high()/low()/toggle()` | Use `Pin.OUT`, `on()`, `off()`, or the optional helper's `pint`. Passing an integer pin number is supported. |
| Team Oz `machine.freq()` / `machine.freq(252000000)` | Frequency readout returns 160 MHz. Setting the system clock is unsupported. |
| Team Oz `DAC(Pin(1)).write(77)` and assumed 123 Ω, 1 V output | Use `DAC(1).write_u16(77 * 257)` to request the same digital fraction. The chosen nominal 990 Ω DAC drive and actual load change the voltage. Verify the transfer function on the physical circuit before interpreting volts. |
| Team Oz BS2 extensions, standalone editor, VGA and USB keyboard | The port supplies named portable operations and a small LED wrapper. Use the P2 serial line editor for UTF-8 scripts up to 4 KiB. BS2 extensions, the Oz screen editor, VGA engine, USB keyboard stack and legacy binary images need ports. |
| Total Spectrum / Rayman cog launch, video or RISC-V binaries | Keep the linked counter with `p2.Cog(period_us)`. Port trusted PASM2 source to the managed HUBEXEC mailbox ABI, declare its pins, and pack its position-independent entry as a P2D1 image for `p2.Driver(image, pins=())`. Linked firmware, COGEXEC/LUT overlays and RISC-V binaries require source and protocol changes. [HUBEXEC ABI and build example](../drivers/README.md#loadable-hubexec-drivers) |
| Rayman display, Wi-Fi module, MQTT, WebREPL | The SPI SSD1306 example streams one 128-byte page. VGA, external network transports and the legacy Wi-Fi module are unimplemented. Sensor and screen operation on external peripherals remains unverified. |

## Optional applications

| Application | Working configuration and evidence | Equipment or implementation still needed |
| --- | --- | --- |
| File editing and startup | Full Edge, p2edit, serial terminal and writable FAT or LittleFS2. Installed with mip, edited and executed a file on a volatile volume. Startup script order and raw recovery were tested separately on SD. [Editor test](../validation/audit-editor_midi.json) · [SD startup](../validation/audit-sd.json) | The line editor uses the serial prompt. A USB keyboard and standalone video UI need separate native drivers. |
| MIDI output | Full Edge, p2midi and UART at 31,250 baud. Tested all bytes of note on, control and note off using the P2 RX pin mux. [MIDI test](../validation/audit-editor_midi.json) | DIN electrical output and audible playback require a 3.3 V-compatible MIDI interface and instrument. SID synthesis needs an audio engine and measured output. |
| WS2812 | Version 1 P2D1 HUBEXEC service. On-board Smart Pins measured 768 pulses per frame, 49/105 system clocks high. [Driver and resources](../drivers/README.md) · [Board capture](../validation/audit-final-bench.json) | Test actual colors/latch timing with a strip, compatible data-level interface and independent power supply. |
| Threaded pulse input and WS2812 output | Share one `EdgeCounter` and one `Strip` across the primary cog and a Python worker. The counter on P1 measured 24 worker-frame edges and 48 main-frame edges on P0. Concurrent writes returned busy and both pins were released. [Setup and resource costs](../drivers/README.md#count-pulses-from-either-python-cog) · [Threaded board test](../validation/thread-peripheral.json) | Two native cogs and two pins for the pair. The counter returns 32-bit snapshots. Per-edge times and individual callbacks need a separate capture service. |
| HTTP via USB | Full Edge received exact HTTP payload from a loopback HTTP server on the computer. Host resolves a configured endpoint and handles TLS for HTTPS. [Host bridge results](../validation/audit-http_bridge.json) | Standalone sockets, TLS, Wi-Fi and WebREPL need a network interface, its transport driver and memory budget. |
| Deferred edges | Full Edge, one Smart Pin and a VM timer. Board test counted four successive 25-edge batches. [Fixture and result](../validation/audit-final-bench.json) | Edges coalesce by count. Timestamped edge capture requires a counter/timestamp service with an explicit queue and overflow policy. |
| Compiled extensions | Standard portable .mpy bytecode and position-independent P2D1 services have separate ABIs. [Interpreter and ABI](../VM.md) | Native and Viper emitters need P2 machine-code generation, relocations, GC-root and unwind rules before executable native .mpy can be supported. |

[Install and use these optional packages](APPLICATIONS.md)

The legacy wrapper was checked with recording PWM/GPIO objects on the host.
The current hardware PWM and frequency-capture primitives have a separate
no-jumper P2 test. `examples/legacy_led.py` is finite and releases its pin.

Sources: [Rayman's LED examples](https://www.rayslogic.com/Propeller2/upy/Micropy_LEDs.html),
[Team Oz P2 quick reference at the inspected commit](https://github.com/team-oz/p2-native-micropython/blob/1ccb02008146d5fa87b491eefc20d3ebe763c818/docs/p2/quickref.rst)
and [Parallax's description of Team Oz's distribution](https://classic.parallax.com/propeller-2/get-started/micropython/).
