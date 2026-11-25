// SPDX-License-Identifier: MIT
#ifndef MICROPY_INCLUDED_P2_RESOURCES_H
#define MICROPY_INCLUDED_P2_RESOURCES_H
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#ifndef P2_BOARD_HAS_PSRAM
#define P2_BOARD_HAS_PSRAM 1
#endif
#ifndef P2_CLOCK_HZ
#define P2_CLOCK_HZ 160000000u
#endif
enum { P2_OWNER_FREE, P2_OWNER_PIN, P2_OWNER_SMARTPIN, P2_OWNER_SD, P2_OWNER_PSRAM, P2_OWNER_CONSOLE,
    P2_OWNER_UART, P2_OWNER_SPI, P2_OWNER_I2C, P2_OWNER_FLASH, P2_OWNER_DRIVER };
int p2_pins_claim(const uint8_t *pins, size_t count, uint8_t owner);
void p2_pins_release(const uint8_t *pins, size_t count, uint8_t owner);
uint8_t p2_pin_owner(unsigned pin);
void p2_pins_poll(void);
extern volatile bool p2_pin_release_pending;
extern bool p2_vm_resetting;
static inline bool p2_on_vm_cog(void) {
    unsigned id;
    __asm__ volatile ("cogid %0" : "=r"(id));
    return id == 0;
}
void p2_drivers_reset(void);
void p2_cogs_reset(void);
void p2_hubdrivers_reset(void);
void p2_psram_reset(void);
static inline uint32_t p2_ct(void) {
    uint32_t v;
    __asm__ volatile ("getct %0" : "=r"(v));
    return v;
}
static inline void p2_pin_float(unsigned pin) {
    __asm__ volatile ("dirl %0\n\twrpin #0, %0\n\toutl %0" :: "r"(pin) : "memory");
}
#endif
