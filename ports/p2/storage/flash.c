// SPDX-License-Identifier: MIT
// W25Q128JV SPI mode 3. P60 is also SD /CS, P61 is also SD CLK.
// All P61 transitions occur with P60 high, keeping the SD card deselected.
#include <stdint.h>
#include <string.h>
#include "drivers/modp2.h"
#include "extmod/vfs.h"
#include "py/mphal.h"

#if MICROPY_VFS_LFS2
#define CLK 60
#define CS 61
#define MOSI 59
#define MISO 58
#define CAPACITY (16u * 1024 * 1024)
#define DEFAULT_SIZE (1024u * 1024)
#define BOOT_RESERVED (1024u * 1024)
#define SECTOR 4096u
#define PAGE 256u
#define W25Q128_Q_ID 0xef4018u
#define W25Q128_M_ID 0xef7018u
extern volatile unsigned p2_console_interrupt_count;
static const uint8_t pins[] = {MISO, MOSI, CLK, CS};
typedef struct {
    mp_obj_base_t base;
    uint32_t start, length;
    bool active, writable, busy;
} flash_t;

static void attach(void) {
    int result = p2_pins_claim(pins, 4, P2_OWNER_FLASH);
    if (result) {
        mp_raise_OSError(result == -2 ? MP_EBUSY : MP_EPERM);
    }
    __asm__ volatile ("drvh #60\n\tdrvh #61\n\tdirl #58\n\tdrvh #59" ::: "memory");
}
static inline void select_chip(void) {
    __asm__ volatile ("drvl #61" ::: "memory");
}
static inline void deselect_chip(void) {
    __asm__ volatile ("drvh #61" ::: "memory");
}
static unsigned shift(unsigned out) {
    unsigned in = 0;
    for (unsigned bit = 128; bit != 0; bit >>= 1) {
        __asm__ volatile ("drvl #60" ::: "memory");
        if (out & bit) {
            __asm__ volatile ("drvh #59" ::: "memory");
        } else {
            __asm__ volatile ("drvl #59" ::: "memory");
        }
        unsigned b;
        __asm__ volatile ("waitx #12\n\tdrvh #60\n\twaitx #12\n\ttestp #58 wc\n\twrc %0" : "=r" (b) :: "memory");
        in = (in << 1) | b;
    }
    return in;
}
static uint32_t jedec(void) {
    select_chip();
    shift(0x9f);
    uint32_t v = shift(255) << 16;
    v |= shift(255) << 8;
    v |= shift(255);
    deselect_chip();
    return v;
}
static mp_obj_t probe(void) {
    attach();
    uint32_t id = jedec();
    p2_pins_release(pins, 4, P2_OWNER_FLASH);
    return mp_obj_new_int_from_uint(id);
}
static MP_DEFINE_CONST_FUN_OBJ_0(probe_fun_obj, probe);
static MP_DEFINE_CONST_STATICMETHOD_OBJ(probe_obj, MP_ROM_PTR(&probe_fun_obj));

static mp_obj_t make(const mp_obj_type_t *type, size_t n, size_t nk, const mp_obj_t *args) {
    enum { START, SIZE, WRITABLE };
    static const mp_arg_t allowed[] = {
        { MP_QSTR_start, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = CAPACITY - DEFAULT_SIZE} },
        { MP_QSTR_size, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = DEFAULT_SIZE} },
        { MP_QSTR_writable, MP_ARG_KW_ONLY | MP_ARG_BOOL, {.u_bool = false} },
    };
    mp_arg_val_t v[MP_ARRAY_SIZE(allowed)];
    mp_arg_parse_all_kw_array(n, nk, args, MP_ARRAY_SIZE(allowed), allowed, v);
    uint32_t start = v[START].u_int, length = v[SIZE].u_int;
    if (start < BOOT_RESERVED || start >= CAPACITY || !length || length > CAPACITY - start ||
        (start | length) % SECTOR != 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid flash partition"));
    }
    flash_t *s = mp_obj_malloc_with_finaliser(flash_t, type);
    s->active = false;
    s->busy = false;
    s->writable = v[WRITABLE].u_bool;
    s->start = start;
    s->length = length;
    attach();
    uint32_t id = jedec();
    if (id != W25Q128_Q_ID && id != W25Q128_M_ID) {
        p2_pins_release(pins, 4, P2_OWNER_FLASH);
        mp_raise_OSError(MP_ENODEV);
    }
    s->active = true;
    return MP_OBJ_FROM_PTR(s);
}
static void check(flash_t *s) {
    if (!s->active) {
        mp_raise_OSError(MP_ENODEV);
    }
    if (!p2_on_vm_cog()) {
        mp_raise_OSError(MP_EPERM);
    }
    if (s->busy) {
        mp_raise_OSError(MP_EBUSY);
    }
}
static mp_obj_t close(mp_obj_t o) {
    flash_t *s = MP_OBJ_TO_PTR(o);
    if (s->busy) {
        mp_raise_OSError(MP_EBUSY);
    }
    if (s->active) {
        p2_pins_release(pins, 4, P2_OWNER_FLASH);
        s->active = false;
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(close_obj, close);

#include "w25q128.h"
static uint32_t offset(flash_t *s, mp_int_t block, mp_int_t intra, size_t n) {
    if (block < 0 || (uint32_t)block >= s->length / SECTOR || (unsigned)intra >= SECTOR) {
        mp_raise_ValueError(MP_ERROR_TEXT("flash address out of range"));
    }
    uint32_t off = (uint32_t)block * SECTOR + intra;
    if (n > s->length - off) {
        mp_raise_ValueError(MP_ERROR_TEXT("flash length out of range"));
    }
    return s->start + off;
}
static mp_obj_t transfer(size_t n, const mp_obj_t *args, bool writing) {
    flash_t *s = MP_OBJ_TO_PTR(args[0]);
    mp_int_t block = mp_obj_get_int(args[1]);
    mp_int_t intra = n == 4 ? mp_obj_get_int(args[3]) : 0;
    mp_buffer_info_t buffer;
    mp_get_buffer_raise(args[2], &buffer, writing ? MP_BUFFER_READ : MP_BUFFER_WRITE);
    check(s);
    uint32_t addr = offset(s, block, intra, buffer.len);
    if (n == 3 && buffer.len % SECTOR) {
        mp_raise_ValueError(MP_ERROR_TEXT("expected full sectors"));
    }
    if (writing && !s->writable) {
        return MP_OBJ_NEW_SMALL_INT(-MP_EROFS);
    }
    int err = ready();
    uint8_t *buf = buffer.buf;
    size_t remaining = buffer.len;
    unsigned interrupt = p2_console_interrupt_count;
    s->busy = true;
    while (remaining && !err) {
        size_t chunk = PAGE - (addr % PAGE);
        if (chunk > remaining) {
            chunk = remaining;
        }
        if (writing) {
            if (n == 3 && addr % SECTOR == 0) {
                err = erase(addr);
            }
            if (!err) {
                err = program(addr, buf, chunk);
            }
        } else {
            address_command(3, addr);
            for (size_t i = 0; i < chunk; ++i) { buf[i] = shift(255);
            }
            deselect_chip();
        }
        buf += chunk;
        addr += chunk;
        remaining -= chunk;
        if (p2_console_interrupt_count != interrupt) {
            // Each complete chunk has released CS. Leave the handle reusable
            // before delivering a Python exception.
            s->busy = false;
            p2_poll_borrowed_io();
            return MP_OBJ_NEW_SMALL_INT(-MP_EINTR);
        }
    }
    s->busy = false;
    return MP_OBJ_NEW_SMALL_INT(-err);
}
static mp_obj_t readblocks(size_t n, const mp_obj_t *args) {
    return transfer(n, args, false);
}
static mp_obj_t writeblocks(size_t n, const mp_obj_t *args) {
    return transfer(n, args, true);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(read_obj, 3, 4, readblocks);
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(write_obj, 3, 4, writeblocks);
static mp_obj_t ioctl(mp_obj_t o, mp_obj_t op, mp_obj_t arg) {
    flash_t *s = MP_OBJ_TO_PTR(o);
    int operation = mp_obj_get_int(op);
    check(s);
    switch (operation) {
        case MP_BLOCKDEV_IOCTL_INIT:
        case MP_BLOCKDEV_IOCTL_SYNC:
            return MP_OBJ_NEW_SMALL_INT(-ready());
        case MP_BLOCKDEV_IOCTL_DEINIT:
            close(o);
            return MP_OBJ_NEW_SMALL_INT(0);
        case MP_BLOCKDEV_IOCTL_BLOCK_COUNT:
            return MP_OBJ_NEW_SMALL_INT(s->length / SECTOR);
        case MP_BLOCKDEV_IOCTL_BLOCK_SIZE:
            return MP_OBJ_NEW_SMALL_INT(SECTOR);
        case MP_BLOCKDEV_IOCTL_BLOCK_ERASE: {
            mp_int_t block = mp_obj_get_int(arg);
            check(s);
            uint32_t addr = offset(s, block, 0, SECTOR);
            return MP_OBJ_NEW_SMALL_INT(s->writable ? -erase(addr) : -MP_EROFS);
        }
        default:
            return mp_const_none;
    }
}
static MP_DEFINE_CONST_FUN_OBJ_3(ioctl_obj, ioctl);
static const mp_rom_map_elem_t locals[] = {
    { MP_ROM_QSTR(MP_QSTR_probe), MP_ROM_PTR(&probe_obj) },
    { MP_ROM_QSTR(MP_QSTR_deinit), MP_ROM_PTR(&close_obj) },
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&close_obj) },
    { MP_ROM_QSTR(MP_QSTR_readblocks), MP_ROM_PTR(&read_obj) },
    { MP_ROM_QSTR(MP_QSTR_writeblocks), MP_ROM_PTR(&write_obj) },
    { MP_ROM_QSTR(MP_QSTR_ioctl), MP_ROM_PTR(&ioctl_obj) },
};
static MP_DEFINE_CONST_DICT(locals_dict, locals);
MP_DEFINE_CONST_OBJ_TYPE(p2_flash_type, MP_QSTR_Flash, MP_TYPE_FLAG_NONE,
    make_new, make, locals_dict, &locals_dict);
#endif
