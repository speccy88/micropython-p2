# Small applications for the P2

These optional Python packages live on a mounted volume. Their code takes hub heap when imported. Installing a package adds no bytes to the full Edge firmware. Start a RAM session, then use the normal host terminal for package installation. Substitute the path of your writable volume. For the automatically mounted SD card, use `/lib`.

```sh
mpremote connect socket://127.0.0.1:8122 resume mip install --target /lib ports/p2/packages/p2edit/package.json
mpremote connect socket://127.0.0.1:8122 resume mip install --target /lib ports/p2/packages/p2midi/package.json
```

## Edit a script at the serial prompt

```python
from p2edit import edit
edit("/blink.py")
```

Enter `a from time import sleep_ms`, then `a print("Ready!")`. Type `p` to see the line numbers. Use `r 2 print("Hello, P2!")` to replace the second line, `d 1` to delete the first, and `w` to save. At the prompt, `exec(open("/blink.py").read())` runs the file. A friendly soft reset runs `/boot.py` then `/main.py` from the mounted root. Enter raw REPL before a soft reset to bypass a broken startup script and repair it with mpremote. [Storage acceptance and recovery](../storage/)

The editor holds up to 4 KiB of UTF-8 text and 256 lines in hub RAM, with additional heap for the line list and edits. Saving writes LF line endings and a final newline. `q` discards your edits. If power goes away during a save, inspect the original path, its `.new` candidate and its `.bak` backup before another save.

## Play notes through a MIDI interface

Set the UART to 31,250 baud, 8N1. `p2midi.MidiOut(uart, channel=1)` sends note on, note off and continuous-controller messages on channels 1–16. The example uses P6 for transmit and reserves P7 for receive. The UART uses one service cog, two Smart Pins and its existing RX/TX rings. Connect a 3.3 V-compatible MIDI OUT interface between P6 and the instrument. The example releases the UART after the final note. [Three-note example](../examples/midi.py) · [MIDI Association message table](https://midi.org/summary-of-midi-1-0-messages)

## Count edges while Python is busy

Install `ports/p2/packages/p2events/package.json` the same way. A Smart Pin counts rising edges in hardware. A software timer delivers the delta on the VM, so a callback may report several edges. The count wraps after 2³² edges. Size the interval so fewer than 2³² edges arrive between actual deliveries, including time when Python is busy. There is no queue entry or timestamp per edge. The driver needs one input Smart Pin and a soft timer, with no dedicated cog.

```python
from p2events import RisingEdges
from time import sleep_ms

events = RisingEdges(1, lambda count: print("rises", count), period_ms=100)
try:
    sleep_ms(5000)
finally:
    events.deinit()
```

The on-board acceptance routes the neighboring PWM output into the Smart Pin's input selector. This checks counted edges, deferred delivery and cleanup without an external source. [Test program](../tests/drivers/edge_events.py)

## Read a web resource through USB

Install `ports/p2/packages/p2fetch/package.json` on the board. Save the following as `weather.py` on your computer. Launch it with the host helper against an HTTP(S) endpoint you choose.

```python
from p2fetch import get
import json

print(json.loads(get("weather").decode()))
```

```sh
python ports/p2/tools/p2_http.py --port socket://127.0.0.1:8122 --resource weather=https://example.org/your-weather.json weather.py
```

The computer performs DNS, HTTP and TLS. The P2 requests a named resource, receives at most 8 KiB into hub RAM over the existing console, and waits for one short block at a time. The host command owns the console for that invocation. Endpoint names come from the host command line. A missing resource or a timed-out host raises an exception on the board. This is a host-assisted application transport. Standalone Wi-Fi, TCP sockets, TLS and WebREPL still require a separate network device and driver.
