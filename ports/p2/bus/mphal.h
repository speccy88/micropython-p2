// SPDX-License-Identifier: MIT
#pragma once
#if P2_ENABLE_BUSES
#include <stdint.h>
#define mp_hal_pin_obj_t uint8_t
#define MP_HAL_PIN_FMT "%u"
#define mp_hal_pin_name(pin) (unsigned)(pin)
#define mp_hal_get_pin_obj(pin) ((uint8_t)mp_obj_get_int(pin))
static inline int mp_hal_pin_read(unsigned pin) {
    unsigned sample;
    __asm__ volatile ("testp %1 wc\n\twrc %0" : "=r"(sample) : "r"(pin));
    return sample;
}
static inline void mp_hal_pin_write(unsigned pin, int high) {
    if (high) { __asm__ volatile ("outh %0" :: "r"(pin) : "memory"); }
    else { __asm__ volatile ("outl %0" :: "r"(pin) : "memory"); }
}
static inline void mp_hal_pin_input(unsigned pin) {
    __asm__ volatile ("dirl %0" :: "r"(pin) : "memory");
}
static inline void mp_hal_pin_output(unsigned pin) {
    __asm__ volatile ("dirh %0" :: "r"(pin) : "memory");
}
static inline void mp_hal_pin_open_drain(unsigned pin) {
    __asm__ volatile ("dirl %0\n\twrpin #0,%0\n\toutl %0" :: "r"(pin) : "memory");
}
#define mp_hal_pin_od_low(pin) mp_hal_pin_output(pin)
#define mp_hal_pin_od_high(pin) mp_hal_pin_input(pin)
static inline void mp_hal_delay_us_fast(unsigned us) {
    __asm__ volatile ("waitx %0" :: "r"(us * 160u));
}
#endif
