// SPDX-License-Identifier: MIT
// P2 Edge SPI-mode SD. P58/P59 are shared data, P60 is SD CS and flash CLK,
// P61 is SD CLK and flash CS. Change SD CS only while P61 is high.
#include <stdint.h>
#include "py/runtime.h"
#include "py/mperrno.h"
#include "extmod/vfs.h"
#include "drivers/p2resources.h"

#if MICROPY_VFS_FAT
enum { MISO, MOSI, CS, CLK };
typedef struct {
    mp_obj_base_t base;
    uint8_t pins[4];
    uint32_t sectors;
    uint32_t multiplier;
    unsigned delay;
} p2_sd_t;
MP_REGISTER_ROOT_POINTER(void *p2_sd_active);
extern const mp_obj_type_t p2_sdcard_type;

static void drive(unsigned pin, unsigned high) {
    if (high) {
        __asm__ volatile ("drvh %0" :: "r"(pin) : "memory");
    } else {
        __asm__ volatile ("drvl %0" :: "r"(pin) : "memory");
    }
}
static unsigned transfer(p2_sd_t *s, unsigned value) {
    unsigned received = 0;
    for (unsigned mask = 128; mask; mask >>= 1) {
        drive(s->pins[CLK], 0);
        drive(s->pins[MOSI], value & mask);
        __asm__ volatile ("waitx %0" :: "r"(s->delay));
        drive(s->pins[CLK], 1);
        unsigned bit;
        __asm__ volatile ("waitx %1\n\ttestp %2 wc\n\twrc %0"
            : "=r"(bit) : "r"(s->delay), "r"((unsigned)s->pins[MISO]) : "memory");
        received = (received << 1) | bit;
    }
    return received;
}
static void deselect(p2_sd_t *s) {
    drive(s->pins[CS], 1);
    transfer(s, 255);
}
static unsigned command(p2_sd_t *s, unsigned cmd, uint32_t arg) {
    deselect(s);
    drive(s->pins[CS], 0);
    unsigned start = p2_ct();
    while (transfer(s, 255) != 255) {
        if (p2_ct() - start > P2_CLOCK_HZ / 2) { return 255; }
    }
    transfer(s, 0x40 | cmd);
    for (int shift = 24; shift >= 0; shift -= 8) { transfer(s, arg >> shift); }
    transfer(s, cmd == 0 ? 0x95 : cmd == 8 ? 0x87 : 1);
    for (unsigned i = 0; i < 16; ++i) {
        unsigned r = transfer(s, 255);
        if (r < 128) { return r; }
    }
    return 255;
}
static int read_data(p2_sd_t *s, uint8_t *dst, size_t len) {
    uint32_t start = p2_ct();
    unsigned token;
    do {
        token = transfer(s, 255);
        if (p2_ct() - start > P2_CLOCK_HZ / 2) { return MP_ETIMEDOUT; }
    } while (token == 255);
    if (token != 0xfe) { return MP_EIO; }
    while (len--) { *dst++ = transfer(s, 255); }
    transfer(s, 255);
    transfer(s, 255);
    return 0;
}
static int init_card(p2_sd_t *s) {
    s->delay = 512;
    drive(s->pins[CLK], 1);
    drive(s->pins[CS], 1);
    for (unsigned i = 0; i < 12; ++i) { transfer(s, 255); }
    unsigned r = 255;
    for (unsigned i = 0; i < 5 && r != 1; ++i) { r = command(s, 0, 0); }
    if (r != 1) { return MP_ENODEV; }
    r = command(s, 8, 0x1aa);
    int v2 = r == 1;
    if (v2) {
        transfer(s, 255); transfer(s, 255);
        if (transfer(s, 255) != 1 || transfer(s, 255) != 0xaa) { return MP_EIO; }
    } else if (r != 5) { return MP_EIO; }
    uint32_t start = p2_ct();
    do {
        if (command(s, 55, 0) > 1) { return MP_EIO; }
        r = command(s, 41, v2 ? 0x40000000u : 0);
        if (p2_ct() - start > 2u * P2_CLOCK_HZ) { return MP_ETIMEDOUT; }
    } while (r == 1);
    if (r || command(s, 58, 0)) { return MP_EIO; }
    s->multiplier = (transfer(s, 255) & 64) ? 1 : 512;
    for (unsigned i = 0; i < 3; ++i) { transfer(s, 255); }
    if (s->multiplier == 512 && command(s, 16, 512)) { return MP_EIO; }
    if (command(s, 9, 0)) { return MP_EIO; }
    uint8_t csd[16];
    int err = read_data(s, csd, sizeof(csd));
    if (err) { return err; }
    if ((csd[0] >> 6) == 1) {
        uint32_t size = ((csd[7] & 63u) << 16) | (csd[8] << 8) | csd[9];
        if (size == 0x3fffff) { return MP_EINVAL; }
        s->sectors = (size + 1) << 10;
    } else if ((csd[0] >> 6) == 0) {
        uint32_t size = ((csd[6] & 3u) << 10) | (csd[7] << 2) | (csd[8] >> 6);
        unsigned shift = ((csd[9] & 3u) << 1) | (csd[10] >> 7);
        unsigned bits = (csd[5] & 15) + shift + 2;
        if (bits < 9 || bits > 20) { return MP_EINVAL; }
        s->sectors = (size + 1) << (bits - 9);
    } else { return MP_EINVAL; }
    s->delay = 8;
    deselect(s);
    return 0;
}
static mp_obj_t sd_make(const mp_obj_type_t *type, size_t n, size_t nk, const mp_obj_t *args) {
    mp_arg_check_num(n, nk, 0, 1, false);
    if (MP_STATE_PORT(p2_sd_active)) { mp_raise_OSError(MP_EBUSY); }
    uint8_t pins[] = {58, 59, 60, 61};
    if (n) {
        mp_obj_t *items;
        mp_obj_get_array_fixed_n(args[0], 4, &items);
        for (unsigned i = 0; i < 4; ++i) {
            mp_int_t pin = mp_obj_get_int(items[i]);
            if ((mp_uint_t)pin >= 64 || (pin >= 58 && pin != 58 + (mp_int_t)i)) {
                mp_raise_ValueError(MP_ERROR_TEXT("invalid SD pin mapping"));
            }
            pins[i] = pin;
        }
    }
    p2_sd_t *s = mp_obj_malloc(p2_sd_t, type);
    for (unsigned i = 0; i < 4; ++i) { s->pins[i] = pins[i]; }
    int err = p2_pins_claim(pins, 4, P2_OWNER_SD);
    if (err) { mp_raise_OSError(err == -2 ? MP_EBUSY : MP_EINVAL); }
    err = init_card(s);
    if (err) {
        deselect(s);
        p2_pins_release(pins, 4, P2_OWNER_SD);
        mp_raise_OSError(err);
    }
    MP_STATE_PORT(p2_sd_active) = s;
    return MP_OBJ_FROM_PTR(s);
}
void p2_storage_reset(void) {
    p2_sd_t *s = MP_STATE_PORT(p2_sd_active);
    if (s) {
        deselect(s);
        p2_pins_release(s->pins, 4, P2_OWNER_SD);
        MP_STATE_PORT(p2_sd_active) = NULL;
    }
}
void p2_storage_mount(void) {
    nlr_buf_t nlr;
    if (nlr_push(&nlr) == 0) {
        mp_obj_t dev = sd_make(&p2_sdcard_type, 0, 0, NULL);
        if (mp_vfs_mount_and_chdir_protected(dev, MP_OBJ_NEW_QSTR(MP_QSTR__slash_)) != 0) {
            p2_storage_reset();
        }
        nlr_pop();
    }
}
static mp_obj_t blocks(mp_obj_t self, mp_obj_t block, mp_obj_t data, int write) {
    p2_sd_t *s = MP_OBJ_TO_PTR(self);
    if (s != MP_STATE_PORT(p2_sd_active)) { mp_raise_OSError(MP_ENODEV); }
    mp_buffer_info_t buf;
    mp_get_buffer_raise(data, &buf, write ? MP_BUFFER_READ : MP_BUFFER_WRITE);
    mp_int_t index = mp_obj_get_int(block);
    unsigned count = buf.len / 512;
    if (index < 0 || buf.len % 512 || !count || (uint32_t)index >= s->sectors ||
        count > s->sectors - (uint32_t)index) { mp_raise_ValueError(MP_ERROR_TEXT("invalid SD block range")); }
    uint8_t *p = buf.buf;
    for (unsigned i = 0; i < count; ++i, p += 512) {
        int err = command(s, write ? 24 : 17, ((uint32_t)index + i) * s->multiplier) ? MP_EIO : 0;
        if (!err && write) {
            transfer(s, 0xfe);
            for (unsigned j = 0; j < 512; ++j) { transfer(s, p[j]); }
            transfer(s, 255); transfer(s, 255);
            if ((transfer(s, 255) & 31) != 5) { err = MP_EIO; }
            uint32_t start = p2_ct();
            while (!err && transfer(s, 255) != 255) {
                if (p2_ct() - start > P2_CLOCK_HZ) { err = MP_ETIMEDOUT; }
            }
        } else if (!err) { err = read_data(s, p, 512); }
        deselect(s);
        if (err) { mp_raise_OSError(err); }
        if (i + 1 < count) {
            mp_event_handle_nowait();
            if (s != MP_STATE_PORT(p2_sd_active)) { mp_raise_OSError(MP_ENODEV); }
        }
    }
    return MP_OBJ_NEW_SMALL_INT(0);
}
static mp_obj_t sd_read(mp_obj_t s, mp_obj_t i, mp_obj_t b) { return blocks(s, i, b, 0); }
static mp_obj_t sd_write(mp_obj_t s, mp_obj_t i, mp_obj_t b) { return blocks(s, i, b, 1); }
static mp_obj_t sd_ioctl(mp_obj_t self, mp_obj_t op, mp_obj_t arg) {
    (void)arg;
    p2_sd_t *s = MP_OBJ_TO_PTR(self);
    if (s != MP_STATE_PORT(p2_sd_active)) { mp_raise_OSError(MP_ENODEV); }
    switch (mp_obj_get_int(op)) {
        case MP_BLOCKDEV_IOCTL_INIT: case MP_BLOCKDEV_IOCTL_SYNC: break;
        case MP_BLOCKDEV_IOCTL_DEINIT: p2_storage_reset(); break;
        case MP_BLOCKDEV_IOCTL_BLOCK_COUNT: return mp_obj_new_int_from_uint(s->sectors);
        case MP_BLOCKDEV_IOCTL_BLOCK_SIZE: return MP_OBJ_NEW_SMALL_INT(512);
        default: return mp_const_none;
    }
    return MP_OBJ_NEW_SMALL_INT(0);
}
static MP_DEFINE_CONST_FUN_OBJ_3(read_obj, sd_read);
static MP_DEFINE_CONST_FUN_OBJ_3(write_obj, sd_write);
static MP_DEFINE_CONST_FUN_OBJ_3(ioctl_obj, sd_ioctl);
static const mp_rom_map_elem_t sd_methods[] = {
    {MP_ROM_QSTR(MP_QSTR_readblocks), MP_ROM_PTR(&read_obj)},
    {MP_ROM_QSTR(MP_QSTR_writeblocks), MP_ROM_PTR(&write_obj)},
    {MP_ROM_QSTR(MP_QSTR_ioctl), MP_ROM_PTR(&ioctl_obj)},
};
static MP_DEFINE_CONST_DICT(sd_locals, sd_methods);
MP_DEFINE_CONST_OBJ_TYPE(p2_sdcard_type, MP_QSTR_SDCard, MP_TYPE_FLAG_NONE,
    make_new, sd_make, locals_dict, &sd_locals);
static mp_obj_t sd_active(void) {
    void *device = MP_STATE_PORT(p2_sd_active);
    return device ? MP_OBJ_FROM_PTR(device) : mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(sd_active_obj, sd_active);
static const mp_rom_map_elem_t sd_globals[] = {
    {MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_p2sd)},
    {MP_ROM_QSTR(MP_QSTR_SDCard), MP_ROM_PTR(&p2_sdcard_type)},
    {MP_ROM_QSTR(MP_QSTR_active), MP_ROM_PTR(&sd_active_obj)},
};
static MP_DEFINE_CONST_DICT(sd_dict, sd_globals);
const mp_obj_module_t p2_sd_module = {.base = {&mp_type_module}, .globals = (void *)&sd_dict};
MP_REGISTER_MODULE(MP_QSTR_p2sd, p2_sd_module);
#endif
