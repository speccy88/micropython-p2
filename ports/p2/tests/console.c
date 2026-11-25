// Standalone RAM smoke test. Link in place of the VM with the same startup.
#include <stdint.h>
extern uint8_t raw_p2_uart_getc(void);
extern void raw_p2_uart_putc(uint8_t);
void main(void) {
    const char *s = "P2 console ready\r\n";
    while (*s) {
        raw_p2_uart_putc(*s++);
    }
    for (;;) {
        raw_p2_uart_putc(raw_p2_uart_getc());
    }
}
