// SPDX-License-Identifier: MIT
#include "p2resources.h"
#include "py/mpconfig.h"
#if P2_ENABLE_BUSES
extern void p2_buses_reset(void);
#endif

// Callers hold the interpreter GIL. Only the primary cog can drive these pins.
// Autonomous drivers must stop driving before the interpreter releases a claim.
static uint8_t claims[64];
#define RELEASE_PENDING 0x80
volatile bool p2_pin_release_pending;
bool p2_vm_resetting;
void p2_pins_poll(void) {
    if (!p2_pin_release_pending || !p2_on_vm_cog()) {
        return;
    }
    for (unsigned pin = 0; pin < 64; ++pin) {
        if (claims[pin] & RELEASE_PENDING) {
            p2_pin_float(pin);
            claims[pin] = P2_OWNER_FREE;
        }
    }
    p2_pin_release_pending = false;
}
static uint8_t reserved(unsigned pin) {
    if (pin >= 62) {
        return P2_OWNER_CONSOLE;
    }
    if (pin >= 58) {
        return P2_OWNER_SD;
    }
    if (P2_BOARD_HAS_PSRAM && pin >= 40 && pin <= 57) {
        return P2_OWNER_PSRAM;
    }
    return P2_OWNER_FREE;
}
uint8_t p2_pin_owner(unsigned pin) {
    p2_pins_poll();
    return claims[pin] ? claims[pin] & ~RELEASE_PENDING : reserved(pin);
}
int p2_pins_claim(const uint8_t *pins, size_t count, uint8_t owner) {
    if (!owner || p2_vm_resetting || !p2_on_vm_cog()) {
        return -1;
    }
    p2_pins_poll();
    for (size_t i = 0; i < count; ++i) {
        unsigned pin = pins[i];
        if (pin >= 64) {
            return -1;
        }
        unsigned board_owner = reserved(pin);
        bool shared_flash = board_owner == P2_OWNER_SD && owner == P2_OWNER_FLASH;
        if (board_owner && board_owner != owner && !shared_flash) {
            return -1;
        }
        if (claims[pin]) {
            return -2;
        }
        for (size_t j = 0; j < i; ++j) {
            if (pins[j] == pin) {
                return -1;
            }
        }
    }
    for (size_t i = 0; i < count; ++i) { claims[pins[i]] = owner;
    }
    return 0;
}
void p2_pins_release(const uint8_t *pins, size_t count, uint8_t owner) {
    for (size_t i = 0; i < count; ++i) {
        unsigned pin = pins[i];
        if (pin < 64 && claims[pin] == owner) {
            if (p2_on_vm_cog()) {
                p2_pin_float(pin);
                claims[pin] = P2_OWNER_FREE;
            } else {
                // GC finalisers may run on a Python worker holding the GIL.
                // Only cog zero can actually remove its DIR/OUT contribution.
                claims[pin] |= RELEASE_PENDING;
                p2_pin_release_pending = true;
            }
        }
    }
}
void p2_drivers_reset(void) {
    p2_pins_poll();
    #if P2_ENABLE_BUSES
    p2_buses_reset();
    #endif
    #if !P2_PROFILE_THREADED
    p2_cogs_reset();
    p2_psram_reset();
    #endif
    p2_hubdrivers_reset();
    for (unsigned pin = 0; pin < 64; ++pin) {
        if (claims[pin]) {
            p2_pin_float(pin);
            claims[pin] = P2_OWNER_FREE;
        }
    }
}
