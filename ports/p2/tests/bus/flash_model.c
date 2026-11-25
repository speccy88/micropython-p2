// SPDX-License-Identifier: MIT
// A JEDEC SPI command model runs the firmware's actual NOR command engine
// against LittleFS2. All storage in this executable is a host RAM array.
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "lfs2.h"

#define SECTOR 4096u
#define PAGE 256u
#define GUARD (2u * SECTOR)
#define BLOCKS 32u
#define MP_EIO 5
#define MP_ETIMEDOUT 110
#define P2_CLOCK_HZ 1000u
static uint8_t cells[GUARD + BLOCKS * SECTOR + GUARD];
static unsigned cmd, pos, addr, clock_count, selected, wel, protected, stuck, busy_reads;
static unsigned programs, erases;

static uint32_t p2_ct(void) { return ++clock_count; }
static void select_chip(void) {
    assert(!selected);
    selected = 1;
    pos = 0;
    addr = 0;
    cmd = 0;
}
static unsigned shift(unsigned value) {
    assert(selected);
    value &= 255;
    if (pos++ == 0) { cmd = value; return 255; }
    if (cmd == 5) {
        if (stuck || busy_reads) {
            if (busy_reads) { --busy_reads; }
            return (wel << 1) | 1;
        }
        return wel << 1;
    }
    if (cmd == 2 || cmd == 3 || cmd == 0x20) {
        if (pos <= 4) { addr = (addr << 8) | value; return 255; }
        assert(addr < sizeof(cells));
        if (cmd == 3) { return cells[addr++]; }
        assert(cmd == 2 && wel);
        if (!protected) { cells[addr] &= value; }
        // NOR wraps within a single page when the host crosses a page boundary.
        addr = (addr & ~(PAGE - 1)) | ((addr + 1) & (PAGE - 1));
    }
    return 255;
}
static void deselect_chip(void) {
    assert(selected);
    selected = 0;
    if (cmd == 6) { wel = 1; return; }
    if (cmd == 0x20 || cmd == 2) {
        assert(wel);
        if (cmd == 0x20) {
            assert(pos == 4 && addr % SECTOR == 0 && addr <= sizeof(cells) - SECTOR);
            if (!protected) { memset(cells + addr, 255, SECTOR); }
            ++erases;
        } else { assert(pos > 4 && pos <= PAGE + 4); ++programs; }
        wel = 0;
        busy_reads = 3;
    }
}

#include "../../storage/w25q128.h"

static uint32_t location(lfs2_block_t block, lfs2_off_t off, lfs2_size_t size) {
    assert(block < BLOCKS && off + size <= SECTOR);
    return GUARD + block * SECTOR + off;
}
static int read_cb(const struct lfs2_config *c, lfs2_block_t b, lfs2_off_t off, void *buf, lfs2_size_t n) {
    (void)c;
    address_command(3, location(b, off, n));
    for (size_t i = 0; i < n; ++i) { ((uint8_t *)buf)[i] = shift(255); }
    deselect_chip();
    return 0;
}
static int program_cb(const struct lfs2_config *c, lfs2_block_t b, lfs2_off_t off, const void *buf, lfs2_size_t n) {
    (void)c;
    uint32_t addr = location(b, off, n);
    const uint8_t *p = buf;
    while (n) {
        size_t chunk = PAGE - addr % PAGE;
        if (chunk > n) { chunk = n; }
        int err = program(addr, p, chunk);
        if (err) { return -err; }
        addr += chunk; p += chunk; n -= chunk;
    }
    return 0;
}
static int erase_cb(const struct lfs2_config *c, lfs2_block_t block) {
    (void)c;
    return -erase(location(block, 0, SECTOR));
}
static int sync_cb(const struct lfs2_config *c) { (void)c; return -ready(); }

int main(void) {
    struct lfs2_config cfg = {
        .read = read_cb, .prog = program_cb, .erase = erase_cb, .sync = sync_cb,
        .read_size = 16, .prog_size = 16, .block_size = SECTOR, .block_count = BLOCKS,
        .block_cycles = 100, .cache_size = 256, .lookahead_size = 16,
    };
    memset(cells, 0xa5, sizeof(cells));
    lfs2_t fs;
    lfs2_file_t file;
    uint8_t block[591], actual[591];
    for (unsigned i = 0; i < sizeof(block); ++i) { block[i] = 47 * i + 3; }
    assert(lfs2_format(&fs, &cfg) == 0);
    assert(lfs2_mount(&fs, &cfg) == 0);
    assert(lfs2_file_open(&fs, &file, "test.bin", LFS2_O_CREAT | LFS2_O_RDWR) == 0);
    for (unsigned j = 0; j < 23; ++j) {
        block[0] = j;
        assert(lfs2_file_write(&fs, &file, block, sizeof(block)) == sizeof(block));
    }
    assert(lfs2_file_close(&fs, &file) == 0 && lfs2_unmount(&fs) == 0);
    assert(lfs2_mount(&fs, &cfg) == 0);
    assert(lfs2_file_open(&fs, &file, "test.bin", LFS2_O_RDONLY) == 0);
    for (unsigned j = 0; j < 23; ++j) {
        block[0] = j;
        assert(lfs2_file_read(&fs, &file, actual, sizeof(actual)) == sizeof(actual));
        assert(!memcmp(block, actual, sizeof(block)));
    }
    assert(lfs2_file_close(&fs, &file) == 0 && lfs2_unmount(&fs) == 0);
    for (unsigned i = 0; i < GUARD; ++i) {
        assert(cells[i] == 0xa5 && cells[GUARD + BLOCKS * SECTOR + i] == 0xa5);
    }
    stuck = 1;
    assert(ready() == MP_ETIMEDOUT);
    stuck = 0;
    protected = 1;
    cells[GUARD] = 0;
    assert(erase(GUARD) == MP_EIO);
    cells[GUARD] = 255;
    uint8_t zero = 0;
    assert(program(GUARD, &zero, 1) == MP_EIO);
    printf("{\"passed\":true,\"backend\":\"host NOR model\",\"file_bytes\":%u,\"page_programs\":%u,\"sector_erases\":%u}\n",
        (unsigned)(sizeof(block) * 23), programs, erases);
    return 0;
}
