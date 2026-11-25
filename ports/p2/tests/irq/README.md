# P2 IRQ bench fixtures

Run these tests with the board's normal 160 MHz clock. They use volatile RAM. Disconnect external circuitry from P0 and P1. For the Edge `--io` checks also disconnect P6 through P11, and use a readable SD card for the mounted-media check. The test cog drives the pad that cog 0 uses for input. Its mailbox and pin assignments are deliberately specific to this bench setup.

From `ports/p2`, load the matching IRQ-enabled image with the serial relay. Keep it running while a second terminal runs the test.

```sh
python tools/ram_session.py build-irq/edge/firmware.bin --port COM12
python tests/irq/run.py --port socket://127.0.0.1:8122 --image build-irq/edge/firmware.bin --output hil.json --io
```

Use the lean image and omit `--io` for the lean profile. The host needs the same pyserial and mpremote dependencies as the other hardware tests. For the bench's matching image and raw results see the [validation records](../../validation/IRQ.md).

The `IRQ_LATENCY_CT` pairs give the ISR and callback times in cycles from the stimulus cog's GETCT immediately before the output transition. `IRQ_WORKLOAD_CT` triples give the foreground operation's duration and the two delays. The fixture checks that the stimulus occurs within each measured GC, sum or 4 KiB PSRAM operation. Pin propagation, stimulus instructions and the ISR prologue contribute to these measurements. The Ctrl-C figures also include the host serial relay and transport.

The SPI observer samples SCK and MOSI on the chip. It checks mode-0 edge order, recovered data and minimum setup/hold with the IRQ inside the transfer. The SoftI2C timeout check holds the master's released SCL low until START times out, then supplies a high input for a successful START/STOP retry. Measurements with passive pull-ups, an external target and a logic analyzer are still needed for target-specific ACK, clock-stretch and electrical timing limits.

## Standalone CT and context test

Stop the relay before starting the native fixture. This image uses the firmware's actual ISR, memory routines, startup and linker script. Build it with the pinned P2 Clang installation, then upload and capture from the USB host.

```sh
make -f tests/irq/Makefile BUILD=build-irq-native P2_WORK="$P2_WORK" P2_LLVM_BIN="$P2_BIN"
python tests/irq/native_run.py --image build-irq-native/irq-native.bin --port COM12 --output native.json
```

The test records hexadecimal CT ticks. Each CONTROL/WITH pair runs the same COG foreground loop, first with INT1 disconnected, then with a real CT1 event routed to the installed vector. WITH's second number measures scheduled CT1 expiry to the production ISR's GETCT. The duration difference includes interrupt entry, the whole handler and return. The loop checks flags, registers, FIFO, CORDIC results and nested hardware CALL return. MEMORY_INTERRUPTS counts publications during 112 verified memmove trials spanning byte alignment, both overlap directions and the 512-byte scratch boundary.

To regenerate the HUBEXEC stimulus images from their assembly in this directory, run the following commands from `ports/p2`.

```sh
"$P2_BIN/clang" --target=p2 -c tests/irq/stimulus.S -o /tmp/stimulus.o
python tools/cog_image.py pack /tmp/stimulus.o tests/irq/stimulus.p2d --words 7
"$P2_BIN/clang" --target=p2 -c tests/irq/bus_probe.S -o /tmp/bus_probe.o
python tools/cog_image.py pack /tmp/bus_probe.o tests/irq/bus_probe.p2d --words 132
```
