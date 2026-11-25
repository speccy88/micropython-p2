# Pick your physical board, then press F5 to blink its two LEDs.
EDGE_32MB = True  # True: P2-EC32MB (P38/P39). False: plain Edge (P56/P57).

from time import sleep_ms

try:
    from machine import Pin
except ImportError:
    raise RuntimeError("Choose the Edge or Lean firmware for this GPIO example")

pins = (38, 39) if EDGE_32MB else (56, 57)
print("Blinking P%d and P%d" % pins)

# Blink each LED in turn. Release the pin even if you stop the script early.
for _ in range(5):
    for number in pins:
        led = Pin(number, Pin.OUT)
        try:
            led.on()
            sleep_ms(250)
            led.off()
        finally:
            led.deinit()
print("Done! Press F5 to blink again.")
