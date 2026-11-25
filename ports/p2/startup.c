// Clock and Smart Pin initialization adapted from speccy88/tinygo-p2.
#include <stdint.h>

extern uint8_t _bss_start[], _bss_end[];
extern void main(void);
extern void __start(void);

#define RING_LEN 1024u
static volatile uint8_t rx[RING_LEN], tx[RING_LEN];
static volatile uint32_t rx_in, rx_out, tx_in, tx_out, console_ready;
volatile uint32_t p2_console_overruns;
volatile int p2_console_interrupt_char = -1;
volatile unsigned p2_console_interrupt_count;

static void uart_config(unsigned pin, unsigned mode) {
    unsigned period = ((160000000u / 115200u) << 16) | 7u;
    __asm__ volatile ("dirl %0\n\twrpin %1, %0\n\twxpin %2, %0\n\tdirh %0"
        :: "r"(pin), "r"(mode), "r"(period) : "memory");
}

void p2_console_service(void) {
    uart_config(62, 0x7c);
    uart_config(63, 0x3e);
    console_ready = 1;
    unsigned sending = 0;
    for (;;) {
        unsigned ready;
        __asm__ volatile ("testp #63 wc\n\twrc %0" : "=r"(ready));
        if (ready) {
            unsigned ch;
            __asm__ volatile ("rdpin %0, #63" : "=r"(ch));
            if ((int)(ch >> 24) == p2_console_interrupt_char) {
                ++p2_console_interrupt_count;
            } else if (rx_in - rx_out < RING_LEN) {
                rx[rx_in & (RING_LEN - 1)] = ch >> 24;
                ++rx_in;
            } else {
                ++p2_console_overruns;
            }
        }
        if (sending) {
            __asm__ volatile ("testp #62 wc\n\twrc %0" : "=r"(ready));
            if (ready) {
                sending = 0;
            }
        }
        if (!sending && tx_out != tx_in) {
            unsigned ch = tx[tx_out & (RING_LEN - 1)];
            __asm__ volatile ("wypin %0, #62\n\twaitx #20" :: "r"(ch) : "memory");
            ++tx_out;
            sending = 1;
        }
    }
}

unsigned raw_p2_uart_buffered(void) {
    return rx_in - rx_out;
}

uint8_t raw_p2_uart_getc(void) {
    while (rx_in == rx_out) {}
    uint8_t value = rx[rx_out & (RING_LEN - 1)];
    ++rx_out;
    return value;
}

void raw_p2_uart_putc(uint8_t ch) {
    while (tx_in - tx_out >= RING_LEN) {}
    tx[tx_in & (RING_LEN - 1)] = ch;
    ++tx_in;
}

void p2_primary_entry(void) {
    for (uint8_t *p = _bss_start; p < _bss_end; ++p) {
        *p = 0;
    }
    __asm__ volatile ("hubset #0xf0\n\twaitx ##200000\n\thubset %0\n\twaitx ##200000\n\thubset %1"
        :: "r"(0x010007f4u), "r"(0x010007f7u) : "memory");
    __asm__ volatile ("coginit #1, %0" :: "r"(__start) : "memory");
    while (!console_ready) {}
    main();
    for (;;) {}
}
