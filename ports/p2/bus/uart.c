// SPDX-License-Identifier: MIT
#include "py/mpconfig.h"
#if P2_ENABLE_BUSES
#include <stddef.h>
#include <string.h>
#include "common.h"
#include "py/stream.h"

#define UART_RING 256
typedef struct {
    volatile uint32_t ready, rx_pin, tx_pin, rate, rx_mode;
    volatile uint32_t rx_in, rx_out, tx_in, tx_out, tx_busy, overruns;
    volatile uint8_t rx[UART_RING], tx[UART_RING];
    int cog_plus_one;
} uart_slot_t;
_Static_assert(offsetof(uart_slot_t, rx) == 44 && offsetof(uart_slot_t, tx) == 300, "UART mailbox layout");
static uart_slot_t slots[2];
extern int p2_driver_launch(const void *entry, volatile void *mailbox);
extern const uint8_t p2_uart_worker[];

typedef struct {
    mp_obj_base_t base;
    uart_slot_t *slot;
    unsigned timeout, timeout_char;
} uart_obj_t;

static void stop_slot(uart_slot_t *s) {
    if (s->cog_plus_one) {
        __asm__ volatile ("cogstop %0" :: "r"(s->cog_plus_one - 1) : "memory");
        s->cog_plus_one = 0;
        uint8_t pins[] = { s->rx_pin, s->tx_pin };
        p2_pins_release(pins, 2, P2_OWNER_UART);
    }
}
void p2_buses_reset(void) {
    for (size_t i = 0; i < MP_ARRAY_SIZE(slots); ++i) { stop_slot(&slots[i]); }
}
static uart_slot_t *active(uart_obj_t *s) {
    if (!s->slot || !s->slot->cog_plus_one) { mp_raise_OSError(MP_ENODEV); }
    return s->slot;
}
static mp_obj_t make(const mp_obj_type_t *type, size_t n, size_t nk, const mp_obj_t *args) {
    enum { ID, BAUD, BITS, PARITY, STOP, TX, RX, TIMEOUT, TIMEOUT_CHAR, LOOPBACK };
    static const mp_arg_t fields[] = {
        {MP_QSTR_id, MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0}},
        {MP_QSTR_baudrate, MP_ARG_INT, {.u_int = 115200}},
        {MP_QSTR_bits, MP_ARG_INT, {.u_int = 8}},
        {MP_QSTR_parity, MP_ARG_OBJ, {.u_obj = mp_const_none}},
        {MP_QSTR_stop, MP_ARG_INT, {.u_int = 1}},
        {MP_QSTR_tx, MP_ARG_KW_ONLY | MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0}},
        {MP_QSTR_rx, MP_ARG_KW_ONLY | MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0}},
        {MP_QSTR_timeout, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 1000}},
        {MP_QSTR_timeout_char, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 10}},
        {MP_QSTR_loopback, MP_ARG_KW_ONLY | MP_ARG_BOOL, {.u_bool = false}},
    };
    mp_arg_val_t v[MP_ARRAY_SIZE(fields)];
    mp_arg_parse_all_kw_array(n, nk, args, MP_ARRAY_SIZE(fields), fields, v);
    int id = v[ID].u_int, baud = v[BAUD].u_int;
    if (id < 1 || id > 2 || baud < 2500 || baud > 1000000 ||
        v[BITS].u_int != 8 || v[PARITY].u_obj != mp_const_none || v[STOP].u_int != 1 ||
        (unsigned)v[TIMEOUT].u_int > 60000 || (unsigned)v[TIMEOUT_CHAR].u_int > 60000) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid UART settings"));
    }
    uint8_t pins[] = { bus_pin(v[RX].u_int), bus_pin(v[TX].u_int) };
    uint32_t rx_mode = 0x3e;
    if (v[LOOPBACK].u_bool) {
        // P2 A-input mux can route a physical pad within +/-3 on this pin group.
        int delta = pins[1] - pins[0];
        if (pins[1] / 32 != pins[0] / 32 || delta == 0 || delta < -3 || delta > 3) {
            mp_raise_ValueError(MP_ERROR_TEXT("loopback requires nearby pins"));
        }
        rx_mode |= ((unsigned)delta & 7) << 28;
    }
    uart_obj_t *self = mp_obj_malloc_with_finaliser(uart_obj_t, type);
    self->slot = NULL;
    self->timeout = v[TIMEOUT].u_int;
    self->timeout_char = v[TIMEOUT_CHAR].u_int;
    uart_slot_t *slot = &slots[id - 1];
    if (slot->cog_plus_one) { mp_raise_OSError(MP_EBUSY); }
    claim_bus(pins, 2, P2_OWNER_UART);
    memset(slot, 0, sizeof(*slot));
    slot->rx_pin = pins[0];
    slot->tx_pin = pins[1];
    slot->rx_mode = rx_mode;
    slot->rate = (((P2_CLOCK_HZ + baud / 2) / (unsigned)baud) << 16) | 7;
    int cog = p2_driver_launch(p2_uart_worker, slot);
    if (cog < 0) {
        p2_pins_release(pins, 2, P2_OWNER_UART);
        mp_raise_OSError(MP_EBUSY);
    }
    slot->cog_plus_one = cog + 1;
    uint32_t start = p2_ct();
    while (!slot->ready) {
        if (p2_ct() - start > P2_CLOCK_HZ / 100) {
            stop_slot(slot);
            mp_raise_OSError(MP_ETIMEDOUT);
        }
    }
    self->slot = slot;
    return MP_OBJ_FROM_PTR(self);
}
static mp_obj_t release(mp_obj_t o) {
    uart_obj_t *s = MP_OBJ_TO_PTR(o);
    if (s->slot) { stop_slot(s->slot); s->slot = NULL; }
    return mp_const_none;
}
static mp_obj_t available(mp_obj_t o) {
    uart_slot_t *s = active(MP_OBJ_TO_PTR(o));
    return MP_OBJ_NEW_SMALL_INT(s->rx_in - s->rx_out);
}
static bool drained(uart_slot_t *s) { return s->tx_in == s->tx_out && !s->tx_busy; }
static mp_obj_t txdone(mp_obj_t o) { return mp_obj_new_bool(drained(active(MP_OBJ_TO_PTR(o)))); }
static mp_obj_t overrun_count(mp_obj_t o) {
    return mp_obj_new_int_from_uint(active(MP_OBJ_TO_PTR(o))->overruns);
}
static mp_uint_t uart_read(mp_obj_t o, void *dst, mp_uint_t n, int *err) {
    uart_obj_t *self = MP_OBJ_TO_PTR(o);
    uart_slot_t *s = active(self);
    unsigned i = 0, timeout = self->timeout;
    uint32_t start = mp_hal_ticks_ms();
    while (i < n) {
        if (s->rx_out != s->rx_in) {
            ((uint8_t *)dst)[i++] = s->rx[s->rx_out & (UART_RING - 1)];
            s->rx_out++;
            start = mp_hal_ticks_ms();
            timeout = self->timeout_char;
        } else {
            if (mp_hal_ticks_ms() - start >= timeout) { break; }
            mp_event_handle_nowait();
            s = active(self);
        }
    }
    if (!i && n) { *err = MP_EAGAIN; return MP_STREAM_ERROR; }
    return i;
}
static mp_uint_t uart_write(mp_obj_t o, const void *src, mp_uint_t n, int *err) {
    uart_obj_t *self = MP_OBJ_TO_PTR(o);
    uart_slot_t *s = active(self);
    unsigned i = 0;
    uint32_t start = mp_hal_ticks_ms();
    while (i < n) {
        if (s->tx_in - s->tx_out < UART_RING) {
            s->tx[s->tx_in & (UART_RING - 1)] = ((const uint8_t *)src)[i++];
            s->tx_in++;
        } else {
            if (mp_hal_ticks_ms() - start >= self->timeout) { break; }
            mp_event_handle_nowait();
            s = active(self);
        }
    }
    if (!i && n) { *err = MP_EAGAIN; return MP_STREAM_ERROR; }
    return i;
}
static mp_uint_t uart_ioctl(mp_obj_t o, mp_uint_t req, uintptr_t arg, int *err) {
    uart_obj_t *self = MP_OBJ_TO_PTR(o);
    uart_slot_t *s = active(self);
    if (req == MP_STREAM_POLL) {
        unsigned bits = 0;
        if (s->rx_in != s->rx_out) { bits |= MP_STREAM_POLL_RD; }
        if (s->tx_in - s->tx_out < UART_RING) { bits |= MP_STREAM_POLL_WR; }
        return arg & bits;
    }
    if (req == MP_STREAM_FLUSH) {
        uint32_t start = mp_hal_ticks_ms();
        while (!drained(s)) {
            if (mp_hal_ticks_ms() - start >= self->timeout) { *err = MP_ETIMEDOUT; return MP_STREAM_ERROR; }
            mp_event_handle_nowait();
            s = active(self);
        }
        return 0;
    }
    *err = MP_EINVAL;
    return MP_STREAM_ERROR;
}
static MP_DEFINE_CONST_FUN_OBJ_1(release_obj, release);
static MP_DEFINE_CONST_FUN_OBJ_1(any_obj, available);
static MP_DEFINE_CONST_FUN_OBJ_1(txdone_obj, txdone);
static MP_DEFINE_CONST_FUN_OBJ_1(overruns_obj, overrun_count);
static const mp_rom_map_elem_t locals[] = {
    { MP_ROM_QSTR(MP_QSTR_deinit), MP_ROM_PTR(&release_obj) },
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&release_obj) },
    { MP_ROM_QSTR(MP_QSTR_read), MP_ROM_PTR(&mp_stream_read_obj) },
    { MP_ROM_QSTR(MP_QSTR_readinto), MP_ROM_PTR(&mp_stream_readinto_obj) },
    { MP_ROM_QSTR(MP_QSTR_readline), MP_ROM_PTR(&mp_stream_unbuffered_readline_obj) },
    { MP_ROM_QSTR(MP_QSTR_write), MP_ROM_PTR(&mp_stream_write_obj) },
    { MP_ROM_QSTR(MP_QSTR_flush), MP_ROM_PTR(&mp_stream_flush_obj) },
    { MP_ROM_QSTR(MP_QSTR_txdone), MP_ROM_PTR(&txdone_obj) },
    { MP_ROM_QSTR(MP_QSTR_any), MP_ROM_PTR(&any_obj) },
    { MP_ROM_QSTR(MP_QSTR_overruns), MP_ROM_PTR(&overruns_obj) },
};
static MP_DEFINE_CONST_DICT(locals_dict, locals);
static const mp_stream_p_t protocol = { .read = uart_read, .write = uart_write, .ioctl = uart_ioctl };
MP_DEFINE_CONST_OBJ_TYPE(p2_uart_type, MP_QSTR_UART, MP_TYPE_FLAG_ITER_IS_STREAM,
    make_new, make, protocol, &protocol, locals_dict, &locals_dict);
#endif
