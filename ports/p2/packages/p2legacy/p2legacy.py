"""Optional Rayman LED helper subset. Import as p2 after selecting a free pin."""

# SPDX-License-Identifier: MIT
from machine import Pin, PWM
from time import sleep_ms as delay

_outputs = {}
_leds = {}


def _output(number, level):
    state = _outputs.get(number)
    if state is None:
        pin = Pin(number, Pin.OUT, value=level)
        try:
            _outputs[number] = [pin, level]
        except BaseException:
            pin.deinit()
            raise
    else:
        state[0].value(level)
        state[1] = level


def pinh(number):
    _output(number, 1)


def pinl(number):
    _output(number, 0)


def pint(number):
    state = _outputs.get(number)
    _output(number, 1 if state is None else 1 - state[1])


def _brightness(level):
    if not isinstance(level, int) or not 0 <= level <= 255:
        raise ValueError("brightness outside 0..255")
    return level * 257


def startled(number, level=0):
    scaled = _brightness(level)
    if number in _leds:
        _leds[number].duty_u16(scaled)
        return
    pwm = PWM(number, freq=1000, duty_u16=scaled)
    try:
        _leds[number] = pwm
    except BaseException:
        pwm.deinit()
        raise


def setled(number, level):
    _leds[number].duty_u16(_brightness(level))


def freepin(number):
    if number in _outputs:
        _outputs.pop(number)[0].deinit()
    if number in _leds:
        _leds.pop(number).deinit()
