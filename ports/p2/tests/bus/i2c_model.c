// SPDX-License-Identifier: MIT
// Strict wire transcript. One slot represents one SCL rising edge.
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

enum { SCL, SDA };
enum { MP_MACHINE_I2C_FLAG_READ = 1, MP_MACHINE_I2C_FLAG_STOP = 2 };
#define MP_ETIMEDOUT ETIMEDOUT
#define MP_ENODEV ENODEV

typedef struct { int unused;
} mp_obj_base_t;
typedef struct {
    mp_obj_base_t base;
    unsigned us_delay, us_timeout, scl, sda;
} mp_machine_soft_i2c_obj_t;
typedef struct { uint8_t *buf;
                 size_t len;
} mp_machine_i2c_buf_t;
typedef struct { mp_machine_soft_i2c_obj_t hw;
} p2_i2c_t;

enum driver { START, STOP, CONTROLLER, TARGET };
struct slot { enum driver driver;
              unsigned bit;
};
static struct slot script[128];
static unsigned cursor, slots, poll_delays;
static bool released[2], scl_high, target_bit;
static unsigned stretch, stretch_left;

static void expect(enum driver driver, unsigned bit) {
    assert(slots < sizeof(script) / sizeof(script[0]));
    script[slots++] = (struct slot) {driver, bit};
}

static void byte(enum driver driver, unsigned data, unsigned ack_bit) {
    for (unsigned mask = 128; mask; mask >>= 1) {
        expect(driver, (data & mask) != 0);
    }
    expect(driver == CONTROLLER ? TARGET : CONTROLLER, ack_bit);
}

static void reset(void) {
    cursor = slots = poll_delays = stretch = stretch_left = 0;
    released[SCL] = released[SDA] = scl_high = target_bit = true;
}

static void rising_edge(void) {
    scl_high = true;
    if (cursor == slots || script[cursor].driver == START || script[cursor].driver == STOP) {
        return;
    }
    struct slot s = script[cursor++];
    if (s.driver == TARGET) {
        assert(released[SDA]);
        target_bit = s.bit;
    } else {
        assert(released[SDA] == s.bit);
    }
}

static void mp_hal_pin_od_low(unsigned pin) {
    if (pin == SDA && scl_high && released[SDA]) {
        assert(cursor < slots && script[cursor++].driver == START);
    }
    released[pin] = false;
    if (pin == SCL) {
        scl_high = false;
        target_bit = true;
    }
}

static void mp_hal_pin_od_high(unsigned pin) {
    if (pin == SDA && scl_high && !released[SDA]) {
        assert(cursor < slots && script[cursor++].driver == STOP);
    }
    if (pin == SCL && !released[SCL]) {
        stretch_left = stretch;
        if (!stretch_left) {
            rising_edge();
        }
    }
    released[pin] = true;
}

static void mp_hal_pin_open_drain(unsigned pin) {
    mp_hal_pin_od_high(pin);
}

static unsigned mp_hal_pin_read(unsigned pin) {
    return pin == SCL ? scl_high : (released[SDA] && target_bit);
}

static void mp_hal_delay_us_fast(unsigned us) {
    if (us == 1) {
        ++poll_delays;
    }
    if (released[SCL] && !scl_high && stretch_left) {
        if (us >= stretch_left) {
            stretch_left = 0;
            rising_edge();
        } else {
            stretch_left -= us;
        }
    }
}

#include "wire.inc"

int main(void) {
    p2_i2c_t bus = {.hw = {.scl = SCL, .sda = SDA, .us_timeout = 10}};
    uint8_t reg = 0x42;
    mp_machine_i2c_buf_t reg_buf = {&reg, 1};
    reset();
    // The shared initialization function signals STOP before normal operation.
    expect(START, 0);
    expect(STOP, 0);
    mp_hal_i2c_init(&bus.hw, 250000);
    assert(cursor == slots);

    // Write one register address, repeated START, read two buffers. The first
    // read byte is acknowledged, the final byte is NACKed. Stretch SCL at
    // every rising edge long enough to enter the real polling loop.
    reset();
    stretch = 5;
    expect(START, 0);
    byte(CONTROLLER, 0xa0, 0);
    byte(CONTROLLER, reg, 0);
    expect(START, 0);
    byte(CONTROLLER, 0xa1, 0);
    byte(TARGET, 0x5a, 0);
    byte(TARGET, 0x89, 1);
    expect(STOP, 0);
    assert(mp_machine_soft_i2c_transfer(&bus.hw.base, 0x50, 1, &reg_buf, 0) == 1);
    uint8_t rx[2] = {0};
    mp_machine_i2c_buf_t bufs[2] = {{rx, 1}, {rx + 1, 1}};
    assert(mp_machine_soft_i2c_transfer(&bus.hw.base, 0x50, 2, bufs, MP_MACHINE_I2C_FLAG_READ | MP_MACHINE_I2C_FLAG_STOP) == 0);
    assert(cursor == slots && rx[0] == 0x5a && rx[1] == 0x89 && poll_delays > 0);

    reset();
    expect(START, 0);
    byte(CONTROLLER, 0xa0, 1);
    expect(STOP, 0);
    assert(mp_machine_soft_i2c_transfer(&bus.hw.base, 0x50, 1, &reg_buf, MP_MACHINE_I2C_FLAG_STOP) == -ENODEV);
    assert(cursor == slots && released[SDA] && released[SCL]);

    reset();
    expect(START, 0);
    byte(CONTROLLER, 0xa0, 0);
    byte(CONTROLLER, 0x10, 0);
    byte(CONTROLLER, 0x20, 1);
    expect(STOP, 0);
    uint8_t tx[] = {0x10, 0x20, 0x30};
    mp_machine_i2c_buf_t tx_buf = {tx, sizeof(tx)};
    assert(mp_machine_soft_i2c_transfer(&bus.hw.base, 0x50, 1, &tx_buf, MP_MACHINE_I2C_FLAG_STOP) == 1);
    assert(cursor == slots);

    reset();
    stretch = 1000;
    expect(START, 0);
    assert(checked(&bus, mp_machine_soft_i2c_transfer(&bus.hw.base, 0x50, 1, &reg_buf, 0)) == -ETIMEDOUT);
    assert(poll_delays == bus.hw.us_timeout && released[SCL] && released[SDA]);
    // The target lets go. Retry on the same controller object and pins.
    stretch = 0;
    mp_hal_delay_us_fast(1000);
    expect(START, 0);
    byte(CONTROLLER, 0xa0, 0);
    byte(CONTROLLER, reg, 0);
    expect(STOP, 0);
    assert(mp_machine_soft_i2c_transfer(&bus.hw.base, 0x50, 1, &reg_buf, MP_MACHINE_I2C_FLAG_STOP) == 1);
    assert(cursor == slots && released[SCL] && released[SDA]);
    puts("I2C HAL model passed: repeated START, reads, write ACK count, address/data NACK, stretch, timeout cleanup");
    return 0;
}
