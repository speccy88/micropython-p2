// SPDX-License-Identifier: MIT
// Shared command engine; the includer provides byte SPI, CS and a cycle clock.
#pragma once

static unsigned status(void) {
    select_chip();
    shift(5);
    unsigned value = shift(255);
    deselect_chip();
    return value;
}
static int ready(void) {
    uint32_t begin = p2_ct();
    while (status() & 1) {
        if (p2_ct() - begin > 2u * P2_CLOCK_HZ) {
            return MP_ETIMEDOUT;
        }
    }
    return 0;
}
static int enable_write(void) {
    int err = ready();
    if (err) {
        return err;
    }
    select_chip();
    shift(6);
    deselect_chip();
    return (status() & 2) ? 0 : MP_EIO;
}
static void address_command(unsigned cmd, uint32_t addr) {
    select_chip();
    shift(cmd);
    shift(addr >> 16);
    shift(addr >> 8);
    shift(addr);
}
static int erase(uint32_t addr) {
    int err = enable_write();
    if (err) {
        return err;
    }
    address_command(0x20, addr);
    deselect_chip();
    if ((err = ready()) != 0) {
        return err;
    }
    // Some protection configurations silently ignore erase/program.
    address_command(3, addr);
    for (unsigned i = 0; i < SECTOR; ++i) {
        if (shift(255) != 255) {
            err = MP_EIO;
            break;
        }
    }
    deselect_chip();
    return err;
}
static int program(uint32_t addr, const uint8_t *buf, size_t n) {
    int err = enable_write();
    if (err) {
        return err;
    }
    address_command(2, addr);
    for (size_t i = 0; i < n; ++i) { shift(buf[i]);
    }
    deselect_chip();
    if ((err = ready()) != 0) {
        return err;
    }
    address_command(3, addr);
    for (size_t i = 0; i < n; ++i) {
        if (shift(255) != buf[i]) {
            err = MP_EIO;
            break;
        }
    }
    deselect_chip();
    return err;
}
