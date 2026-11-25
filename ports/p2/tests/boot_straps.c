// SPDX-License-Identifier: MIT
// RAM diagnostic for the P2 ROM's initial boot selection. Link with
// --wrap=p2_primary_entry so the samples precede PLL and console startup.
#include <stdint.h>

extern void __real_p2_primary_entry(void);
extern void raw_p2_uart_putc(uint8_t);

// .data survives the bootstrap's BSS clear. A dash means the ROM would
// already have chosen a branch before sampling that pin.
static char samples[] = "---";

static unsigned pull_up(unsigned pin) {
    unsigned high;
    __asm__ volatile ("drvl %1\n\twaitx #30\n\tfltl %1\n\twaitx #150\n\ttestp %1 wc\n\twrc %0"
        : "=r" (high) : "r" (pin) : "memory");
    return high;
}

void __wrap_p2_primary_entry(void) {
    __asm__ volatile ("hubset #0" ::: "memory"); // RCFAST, as at ROM reset
    const unsigned pins[] = {59, 61, 60}; // serial, flash, SD
    for (unsigned i = 0; i < sizeof(pins) / sizeof(pins[0]); ++i) {
        unsigned high = pull_up(pins[i]);
        samples[i] = '0' + high;
        if (high) {
            break;
        }
    }
    __real_p2_primary_entry();
}

void main(void) {
    for (const char *p = "P59 P61 P60: "; *p; ++p) {
        raw_p2_uart_putc(*p);
    }
    for (const char *p = samples; *p; ++p) {
        raw_p2_uart_putc(*p);
    }
    raw_p2_uart_putc('\r');
    raw_p2_uart_putc('\n');
}
