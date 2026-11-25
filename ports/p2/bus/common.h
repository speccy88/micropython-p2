// SPDX-License-Identifier: MIT
#pragma once
#include "drivers/modp2.h"
#include "py/mphal.h"
#include "extmod/modmachine.h"

static inline void claim_bus(const uint8_t *pins, size_t n, unsigned tag) {
    int error = p2_pins_claim(pins, n, tag);
    if (error != 0) {
        mp_raise_OSError(error == -2 ? MP_EBUSY : MP_EPERM);
    }
}
static inline void require_active(bool active) {
    if (!active) {
        mp_raise_OSError(MP_ENODEV);
    }
    if (!p2_on_vm_cog()) {
        mp_raise_OSError(MP_EPERM);
    }
}
static inline uint8_t bus_pin(mp_int_t pin) {
    if (pin < 0 || pin >= 64) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid pin"));
    }
    return pin;
}

// Include a finaliser alongside the generic MicroPython protocol methods.
static inline void bus_attr(mp_obj_t self, qstr attr, mp_obj_t *dest, const mp_obj_fun_builtin_fixed_t *release) {
    if (dest[0] == MP_OBJ_NULL) {
        if (attr == MP_QSTR___del__) {
            dest[0] = MP_OBJ_FROM_PTR(release);
            dest[1] = self;
        } else {
            dest[1] = MP_OBJ_SENTINEL;
        }
    }
}
