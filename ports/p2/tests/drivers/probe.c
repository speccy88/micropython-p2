// SPDX-License-Identifier: MIT
// Standalone native RAM-load probe. Restores both striped words after testing.
#include <stdint.h>
extern void raw_p2_uart_putc(uint8_t c);
extern void p2_psram_init(uint32_t *ids);
extern uint64_t p2_psram_read_word(uint32_t offset);
extern uint32_t p2_psram_write_word(uint32_t offset, uint32_t value);
extern const uint8_t p2_counter_driver[];
extern int p2_driver_launch(const void *entry, volatile void *mb);
static volatile uint32_t box[3];
static void out(const char *p) {
    while (*p) {
        raw_p2_uart_putc(*p++);
    }
}
static void hex(uint32_t val) {
    for (int i = 28; i >= 0; i -= 4) { raw_p2_uart_putc("0123456789abcdef"[(val >> i) & 15]);
    }
}
static uint32_t ticks(void) {
    uint32_t v;
    __asm__ volatile ("getct %0" : "=r" (v));
    return v;
}
void main(void) {
    uint32_t ids[8];
    p2_psram_init(ids);
    out("RAM_ID ");
    hex(ids[0]);
    out(" ");
    hex(ids[1]);
    out("\r\n");
    if (ids[0] == 0x0d0d0d0d && ids[1] == 0x5d5d5d5d) {
        const uint32_t end = (32u * 1024 * 1024 - 4) / 4;
        uint32_t old0 = p2_psram_read_word(0), old1 = p2_psram_read_word(end);
        uint32_t wt = p2_psram_write_word(0, 0xfca75123u);
        p2_psram_write_word(end, 0x1352c7bau);
        uint64_t low = p2_psram_read_word(0), hi = p2_psram_read_word(end);
        p2_psram_write_word(0, old0);
        p2_psram_write_word(end, old1);
        union { uint64_t pair;
                uint32_t words[2];
        } result = {.pair = low};
        out("RAM_DATA ");
        hex(low);
        out(" ");
        hex(hi);
        out(" TICKS ");
        hex(wt);
        out(" ");
        hex(result.words[1]);
        out("\r\n");
    }
    // Repository mode uses an input-only pin, without external wiring.
    unsigned pin = 0;
    uint32_t z;
    __asm__ volatile ("dirl %1\n\twrpin #2,%1\n\tdirh %1\n\twxpin %2,%1\n\tnop\n\trdpin %0,%1\n\tdirl %1\n\twrpin #0,%1"
        : "=&r" (z) : "r" (pin), "r" (0x8321badc) : "memory");
    out("SMART ");
    hex(z);
    out("\r\n");
    box[2] = 16000;
    int cog = p2_driver_launch(p2_counter_driver, box);
    uint32_t start = ticks();
    while (ticks() - start < 1600000) {
    }
    if (cog >= 2 && cog < 8) {
        __asm__ volatile ("cogstop %0" : : "r" (cog) : "memory");
    }
    out("COG ");
    hex(cog);
    out(" ");
    hex(box[0]);
    out(" ");
    hex(box[1]);
    out("\r\nEND\r\n");
}
