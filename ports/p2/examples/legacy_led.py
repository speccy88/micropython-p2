# Install p2legacy first. Wire P0 through 330 ohms and an LED to ground.
import p2legacy as p2

try:
    p2.pinh(0)
    p2.delay(150)
    p2.pint(0)
    p2.freepin(0)
    p2.startled(0, 0)
    for level in (32, 128, 255, 0):
        p2.setled(0, level)
        p2.delay(150)
finally:
    p2.freepin(0)
