# Serial buses

Build with `PROFILE=edge` to include these buses. Constructors accept integer GPIO numbers. Board-reserved pins and overlapping claims raise errors. Call `deinit()` when finished. A new instance can then claim the pins. Elapsed-time limits refer to the 160 MHz clock profile.

| Class | Configuration and behavior | Hardware resources |
| --- | --- | --- |
| `UART(id, baudrate=115200, *, tx, rx, timeout=1000, timeout_char=10)` | IDs 1 and 2, 8 data bits, no parity, one stop bit. 2,500–1,000,000 requested baud. Millisecond read and write timeouts, stream read/readinto/readline/write, flush, txdone, any and RX overruns. Recreate the instance to change its configuration. | One driver cog, two Smart Pins, two 256-byte static rings per slot. Two slots occupy 1,120 bytes of hub RAM. Driver survives GC. Reset stops the cog before releasing the pads. |
| `SoftSPI(baudrate=500000, *, sck, mosi, miso, polarity=0, phase=0, bits=8, firstbit=0)` | All four clock modes, 8-bit transfers, MSB/LSB order. read, readinto, write and write_readinto. Actual clock depends on instruction overhead. Supply chip select separately with Pin. Devices on the same bus should share the instance and use separate selects. | Runs on VM cog. Claims three pins (two if miso=mosi). No buffering beyond caller-provided arrays and requested read results. |
| `SoftI2C(*, scl, sda, freq=400000, timeout=50000)` | Upstream MicroPython software I²C with open-drain SCL/SDA. Addresses use 7 bits. Standard read/write, vector write, memory read/write, scan, start/stop, ACK detection, repeated starts and clock stretching. Timeout is in nominal microseconds. Both pins release on transfer errors. | Runs on VM cog using two pins. Fit external pull-ups to 3.3 V, typically 4.7 kΩ at low bus capacitance. |

Use `UART(..., loopback=True)` for P2 internal testing: choose pins in the same 32-pin bank separated by one to three pins. The RX Smart Pin routes the TX pad into its input. TX is driven in this mode. The GPIO pads used by `tests/bus/loopback.py` should be unconnected. Its SPI check uses one driven data pad and reads the same pad back. This checks the software data path, not the timing of a separate SPI peripheral. Test I²C target ACK, repeated starts and clock stretching with an attached target. No hardware SPI/I²C aliases are exported.

```sh
mpremote connect socket://127.0.0.1:8122 run tests/bus/loopback.py
```

The COM12 receipt in `validation/edge.json` records success for this script on the P2-EC32MB. It exercised a 192-byte UART packet at 115,200 baud while GC ran, SPI loopback in eight mode/bit-order combinations, and I²C claim/release and invalid-address handling. Transfer timing and interoperability with an external I²C target or SPI display require those peripherals.

The UART ring is single producer/single consumer. The worker continues when the VM is blocked. New bytes are dropped if its RX ring fills, and `overruns()` reports the count. A read timeout with an empty ring returns `None`. A partial `readinto` returns the number of bytes copied and leaves later destination bytes untouched. SPI checks for Ctrl-C between chunks of 32 bytes. UART and SPI defer scheduled Python callbacks until they release the caller's hub buffer. I²C clock stretching uses upstream's bounded microsecond delay loop. A stretched transaction can delay Python interruption until the transaction ends. Electrical bus rates, framing errors, and analog signal quality require an external measurement.
### I²C host fixture

Run `python3 ports/p2/tests/bus/i2c_model.py` from a Linux checkout with a C compiler. It compiles the firmware's upstream SoftI2C transfer section and the P2 error-release helper against a line-level model. A scripted target checks the address and each data bit, two-buffer reads across a repeated START, data and address NACK handling, and the final controller NACK. It stretches clock edges, holds SCL past the configured timeout, then releases it for a successful retry. This exercises transaction semantics and bounded polling. Electrical pull-ups, line timing and target compatibility require hardware measurements.
