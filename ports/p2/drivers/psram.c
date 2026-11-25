// SPDX-License-Identifier: MIT
// Service follows tinygo-p2's striped four-bank word layout, checked tCEM,
// and locked read-modify-write semantics. The single VM cog owns P40..P57.
#include <string.h>
#include "modp2.h"
#if P2_BOARD_HAS_PSRAM
#define CAPACITY (32u << 20)
#define MAX_REGIONS 32
static uint32_t ids[8], max_cycles, last_complete;
static bool active;
typedef struct { uint32_t start, size; } extent_t;
static extent_t extents[MAX_REGIONS];
typedef struct { mp_obj_base_t base; extent_t *region; bool closed; } memory_obj_t;
extern void p2_psram_init(uint32_t *ids);
extern uint64_t p2_psram_read_word(uint32_t address);
extern uint32_t p2_psram_write_word(uint32_t address, uint32_t value);

static void require_vm_cog(void) {
    unsigned id;
    __asm__ volatile ("cogid %0" : "=r"(id));
    if (id) { mp_raise_OSError(MP_EPERM); }
}
static void init(void) {
    require_vm_cog();
    if (active) { return; }
    uint8_t pins[18];
    for (size_t i = 0; i < sizeof(pins); ++i) { pins[i] = i + 40; }
    if (p2_pins_claim(pins, sizeof(pins), P2_OWNER_PSRAM)) { mp_raise_OSError(MP_EBUSY); }
    p2_psram_init(ids);
    if (ids[0] != 0x0d0d0d0d || ids[1] != 0x5d5d5d5d) {
        p2_pins_release(pins, sizeof(pins), P2_OWNER_PSRAM);
        mp_raise_OSError(MP_ENODEV);
    }
    active = true;
}
void p2_psram_reset(void) {
    active = false;
    max_cycles = last_complete = 0;
    memset(extents, 0, sizeof(extents));
}
static memory_obj_t *checked(mp_obj_t obj) {
    require_vm_cog();
    memory_obj_t *self = MP_OBJ_TO_PTR(obj);
    if (self->closed) { mp_raise_OSError(MP_ENODEV); }
    return self;
}
static uint32_t capacity(memory_obj_t *self) { return self->region ? self->region->size : CAPACITY; }
static uint32_t span(memory_obj_t *self, uint32_t off, size_t size) {
    uint32_t cap = capacity(self);
    if (off > cap || size > cap - off) { mp_raise_ValueError(MP_ERROR_TEXT("PSRAM range")); }
    if (self->region) { return self->region->start + off; }
    // Raw access cannot trespass on a live allocation.
    if (size) {
        for (size_t i = 0; i < MAX_REGIONS; ++i) {
            extent_t *r = &extents[i];
            if (r->size && off < r->start + r->size && r->start < off + size) { mp_raise_OSError(MP_EBUSY); }
        }
    }
    return off;
}
static void check_ticks(uint32_t elapsed) {
    if (elapsed > max_cycles) { max_cycles = elapsed; }
    if (elapsed >= P2_CLOCK_HZ / 125000) { mp_raise_OSError(MP_ETIMEDOUT); }
}
// Cog 0 uses polling and runs a single VM. IRQs remain disabled only during
// a word transaction. No ISR or other cog is permitted to change the RAM pins.
// Long transfers poll for Ctrl-C, without running Python callbacks while a hub
// buffer is borrowed. last_complete counts destination bytes confirmed valid.
static void poll_abort(void) {
    p2_console_poll_interrupt();
    if (MP_STATE_THREAD(mp_pending_exception) != MP_OBJ_NULL) {
        mp_handle_pending(MP_HANDLE_PENDING_CALLBACKS_AND_EXCEPTIONS);
    }
}
static void transfer(uint32_t addr, uint8_t *buf, size_t size, bool write, bool record) {
    size_t done = 0;
    unsigned budget = 0;
    while (done < size) {
        unsigned lane = addr & 3, n = 4 - lane;
        if (n > size - done) { n = size - done; }
        uint32_t word = 0;
        if (!write || n < 4) {
            __asm__ volatile ("stalli" ::: "memory");
            uint64_t pair = p2_psram_read_word(addr >> 2);
            __asm__ volatile ("allowi" ::: "memory");
            check_ticks(pair >> 32);
            word = (uint32_t)pair;
        }
        for (unsigned i = 0; i < n; ++i) {
            unsigned shift = (lane + i) * 8;
            if (write) { word = (word & ~(0xffu << shift)) | ((uint32_t)buf[done + i] << shift); }
            else { buf[done + i] = word >> shift; }
        }
        if (write) {
            __asm__ volatile ("stalli" ::: "memory");
            uint32_t ticks = p2_psram_write_word(addr >> 2, word);
            __asm__ volatile ("allowi" ::: "memory");
            check_ticks(ticks);
        }
        done += n;
        addr += n;
        if (record) { last_complete += n; }
        if (++budget == 64) { budget = 0; poll_abort(); }
    }
}
static mp_obj_t ram_make_new(const mp_obj_type_t *type, size_t n, size_t nk, const mp_obj_t *args) {
    mp_arg_check_num(n, nk, 0, 0, false);
    init();
    memory_obj_t *self = mp_obj_malloc_with_finaliser(memory_obj_t, type);
    self->closed = false;
    self->region = NULL;
    return MP_OBJ_FROM_PTR(self);
}
static mp_obj_t ram_alloc(mp_obj_t obj, mp_obj_t amount) {
    unsigned size = p2_arg_range(amount, CAPACITY);
    memory_obj_t *root = checked(obj);
    if (root->region || !size) { mp_raise_ValueError(MP_ERROR_TEXT("allocate on root with positive size")); }
    memory_obj_t *child = mp_obj_malloc_with_finaliser(memory_obj_t, &p2_psram_type);
    child->closed = true;
    child->region = NULL;
    extent_t *slot = NULL;
    uint32_t start = 0;
    for (;;) {
        uint32_t next = start;
        if (size > CAPACITY - start) { break; }
        for (size_t i = 0; i < MAX_REGIONS; ++i) {
            extent_t *r = &extents[i];
            if (!r->size) { slot = r; continue; }
            if (r->start < start + size && r->start + r->size > next) { next = r->start + r->size; }
        }
        if (start == next) {
            if (!slot) { break; }
            slot->start = start;
            slot->size = size;
            child->region = slot;
            child->closed = false;
            return MP_OBJ_FROM_PTR(child);
        }
        start = next;
    }
    mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("PSRAM regions exhausted"));
}
static MP_DEFINE_CONST_FUN_OBJ_2(alloc_obj, ram_alloc);
static mp_obj_t ram_close(mp_obj_t obj) {
    memory_obj_t *self = MP_OBJ_TO_PTR(obj);
    if (!self->closed && self->region) { self->region->size = 0; }
    self->region = NULL;
    self->closed = true;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(close_obj, ram_close);
static mp_obj_t ram_size(mp_obj_t obj) { return mp_obj_new_int_from_uint(capacity(checked(obj))); }
static MP_DEFINE_CONST_FUN_OBJ_1(size_obj, ram_size);
static mp_obj_t buffer_io(mp_obj_t obj, mp_obj_t offset, mp_obj_t buffer, bool write) {
    unsigned off = p2_arg_range(offset, CAPACITY);
    mp_buffer_info_t b;
    mp_get_buffer_raise(buffer, &b, write ? MP_BUFFER_READ : MP_BUFFER_WRITE);
    uint32_t addr = span(checked(obj), off, b.len);
    last_complete = 0;
    transfer(addr, b.buf, b.len, write, true);
    return mp_obj_new_int_from_uint(b.len);
}
static mp_obj_t ram_readinto(mp_obj_t obj, mp_obj_t off, mp_obj_t buf) { return buffer_io(obj, off, buf, false); }
static mp_obj_t ram_write(mp_obj_t obj, mp_obj_t off, mp_obj_t buf) { return buffer_io(obj, off, buf, true); }
static MP_DEFINE_CONST_FUN_OBJ_3(readinto_obj, ram_readinto);
static MP_DEFINE_CONST_FUN_OBJ_3(write_obj, ram_write);
static mp_obj_t ram_read(mp_obj_t obj, mp_obj_t offset, mp_obj_t amount) {
    unsigned off = p2_arg_range(offset, CAPACITY), size = p2_arg_range(amount, CAPACITY);
    uint32_t addr = span(checked(obj), off, size);
    vstr_t v;
    vstr_init_len(&v, size);
    last_complete = 0;
    transfer(addr, (uint8_t *)v.buf, size, false, true);
    return mp_obj_new_bytes_from_vstr(&v);
}
static MP_DEFINE_CONST_FUN_OBJ_3(read_obj, ram_read);
static mp_obj_t ram_fill(size_t n, const mp_obj_t *args) {
    unsigned off = p2_arg_range(args[1], CAPACITY), len = p2_arg_range(args[2], CAPACITY);
    unsigned byte_value = p2_arg_range(args[3], 255);
    uint32_t addr = span(checked(args[0]), off, len);
    uint8_t tile[64];
    memset(tile, byte_value, sizeof(tile));
    last_complete = 0;
    for (unsigned pos = 0; pos < len;) {
        unsigned chunk = len - pos < sizeof(tile) ? len - pos : sizeof(tile);
        transfer(addr + pos, tile, chunk, true, true);
        pos += chunk;
        poll_abort();
    }
    return mp_obj_new_int_from_uint(len);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(fill_obj, 4, 4, ram_fill);
static mp_obj_t ram_copy(size_t n, const mp_obj_t *args) {
    unsigned dest = p2_arg_range(args[1], CAPACITY), src = p2_arg_range(args[2], CAPACITY);
    unsigned len = p2_arg_range(args[3], CAPACITY);
    memory_obj_t *self = checked(args[0]);
    src = span(self, src, len);
    dest = span(self, dest, len);
    uint8_t tile[64];
    last_complete = 0;
    for (unsigned left = len; left;) {
        unsigned chunk = left < sizeof(tile) ? left : sizeof(tile);
        unsigned pos = dest > src && dest - src < len ? left - chunk : len - left;
        transfer(src + pos, tile, chunk, false, false);
        transfer(dest + pos, tile, chunk, true, true);
        left -= chunk;
        poll_abort();
    }
    return mp_obj_new_int_from_uint(len);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(copy_obj, 4, 4, ram_copy);
static mp_obj_t ram_diag(mp_obj_t obj) {
    checked(obj);
    uint8_t banks[32];
    for (unsigned bank = 0; bank < 4; ++bank) {
        for (unsigned i = 0; i < 8; ++i) { banks[bank * 8 + i] = ids[i] >> (bank * 8); }
    }
    mp_obj_t d = mp_obj_new_dict(3);
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_ids), mp_obj_new_bytes(banks, sizeof(banks)));
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_max_cycles), mp_obj_new_int_from_uint(max_cycles));
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_completed), mp_obj_new_int_from_uint(last_complete));
    return d;
}
static MP_DEFINE_CONST_FUN_OBJ_1(diag_obj, ram_diag);
static const mp_rom_map_elem_t ram_locals[] = {
    {MP_ROM_QSTR(MP_QSTR_alloc), MP_ROM_PTR(&alloc_obj)},
    {MP_ROM_QSTR(MP_QSTR_close), MP_ROM_PTR(&close_obj)},
    {MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&close_obj)},
    {MP_ROM_QSTR(MP_QSTR_capacity), MP_ROM_PTR(&size_obj)},
    {MP_ROM_QSTR(MP_QSTR_readinto), MP_ROM_PTR(&readinto_obj)},
    {MP_ROM_QSTR(MP_QSTR_write), MP_ROM_PTR(&write_obj)},
    {MP_ROM_QSTR(MP_QSTR_read), MP_ROM_PTR(&read_obj)},
    {MP_ROM_QSTR(MP_QSTR_copy), MP_ROM_PTR(&copy_obj)},
    {MP_ROM_QSTR(MP_QSTR_fill), MP_ROM_PTR(&fill_obj)},
    {MP_ROM_QSTR(MP_QSTR_diagnostics), MP_ROM_PTR(&diag_obj)},
};
static MP_DEFINE_CONST_DICT(ram_dict, ram_locals);
MP_DEFINE_CONST_OBJ_TYPE(p2_psram_type, MP_QSTR_PSRAM, MP_TYPE_FLAG_NONE, make_new, ram_make_new, locals_dict, &ram_dict);
#else
void p2_psram_reset(void) { }
#endif
