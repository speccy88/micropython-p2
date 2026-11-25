// Read-only sector comparison using the original P2LLVM smart-pin SD driver.
// The only media operation after card initialization is CMD17.
#include <stdint.h>
#include <string.h>
#include "sdmmc.h"
#define WORD SHA256_WORD
#include "sha256.h"
#undef WORD

extern void raw_p2_uart_putc(uint8_t ch);
extern uint8_t raw_p2_uart_getc(void);
extern int sd_init(BYTE *card_type);

unsigned _cnt(void) {
    unsigned ticks;
    __asm__ volatile ("getct %0" : "=r"(ticks));
    return ticks;
}

static const uint32_t lbas[] = {0, 2048, 31916, 31917, 31918};
static uint8_t first[5][512] __attribute__((aligned(4)));
static uint8_t repeat[512] __attribute__((aligned(4)));
static uint8_t names[48][11];
static const char digits[] = "0123456789abcdef";

static void text(const char *s) {
    while (*s) { raw_p2_uart_putc(*s++); }
}

static void hexbyte(uint8_t b) {
    raw_p2_uart_putc(digits[b >> 4]);
    raw_p2_uart_putc(digits[b & 15]);
}

static void hexword(uint32_t value) {
    for (unsigned i = 0; i < 4; ++i) {
        hexbyte(value >> 24);
        value <<= 8;
    }
}

static void sha256(const uint8_t *buffer) {
    CRYAL_SHA256_CTX ctx;
    uint8_t digest[32];
    sha256_init(&ctx);
    sha256_update(&ctx, buffer, 512);
    sha256_final(&ctx, digest);
    for (unsigned i = 0; i < sizeof(digest); ++i) { hexbyte(digest[i]); }
}

static int read_sector(uint32_t lba, uint8_t *dest, uint8_t type) {
    uint32_t address = (type & CT_BLOCK) ? lba : lba * 512;
    int ok = sd_send_cmd(CMD17, address) == 0 && sd_rcvr_datablock(dest, 512);
    sd_deselect();
    return ok;
}

// Expose only status classes. The 11-byte raw aliases stay in hub RAM.
static void directory(void) {
    unsigned live = 0, unique = 0, ended = 0;
    for (unsigned sector = 2; sector < 5; ++sector) {
        text("DIR "); hexword(lbas[sector]); text(" ");
        for (unsigned slot = 0; slot < 16; ++slot) {
            const uint8_t *entry = first[sector] + 32 * slot;
            char status;
            if (ended) {
                status = '-';
            } else if (entry[0] == 0) {
                status = 'E';
                ended = 1;
            } else if (entry[0] == 0xe5) {
                status = 'D';
            } else if (entry[11] == 15) {
                status = 'L';
            } else if (entry[11] & 8) {
                status = 'V';
            } else if (entry[0] == '.') {
                status = 'P';
            } else {
                status = 'S';
                ++live;
                unsigned i = 0;
                while (i < unique && memcmp(names[i], entry, 11)) { ++i; }
                if (i == unique) { memcpy(names[unique++], entry, 11); }
            }
            raw_p2_uart_putc(status);
        }
        text("\r\n");
    }
    text("SFN "); hexword(live); text(" "); hexword(unique); text(" "); hexword(ended); text("\r\n");
}

int main(void) {
    text("P2SD ready\r\n");
    uint32_t challenge = 0;
    for (unsigned i = 0; i < 4; ++i) { challenge = (challenge << 8) | raw_p2_uart_getc(); }
    text("RUN "); hexword(challenge); text("\r\n");
    uint8_t type = 0;
    if (sd_init(&type) || !type) { text("ERROR INIT\r\n"); return 1; }
    // Revisit each sector after four different reads, using separate input buffers.
    for (unsigned pass = 0; pass < 2; ++pass) {
        for (unsigned i = 0; i < 5; ++i) {
            uint8_t *buf = pass ? repeat : first[i];
            if (!read_sector(lbas[i], buf, type)) {
                text("ERROR READ "); hexword(lbas[i]); text("\r\n"); return 1;
            }
            text("SEC "); hexword(pass); text(" "); hexword(lbas[i]); text(" ");
            sha256(buf); text("\r\n");
            if (pass && memcmp(buf, first[i], 512)) { text("ERROR UNSTABLE\r\n"); return 1; }
        }
    }
    directory();
    text("DONE "); hexword(challenge); text("\r\n");
    return 0;
}
