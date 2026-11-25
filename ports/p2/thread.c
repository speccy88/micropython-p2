// SPDX-License-Identifier: MIT
#include <string.h>
#include "py/gc.h"
#include "py/mpthread.h"
#include "py/mperrno.h"
#include "py/runtime.h"

#define MAX_C_STACK (16 * 1024u)
extern uint8_t _stack_bottom[], _stack_top[];
extern int p2_thread_launch(void *base);
extern uintptr_t p2_thread_capture(void **regs);
extern void p2_scan_stack(const void *base, size_t bytes);

static uint8_t worker_stack[MAX_C_STACK] __attribute__((aligned(8)));
static mp_obj_t worker_pystack[768] __attribute__((aligned(8)));
static mp_state_thread_t *worker_state;
static void *(*volatile worker_entry)(void *);
MP_REGISTER_ROOT_POINTER(void *p2_worker_arg);
static volatile int worker_id = -1;
static volatile int stopping, worker_stopped;
static int ticket_guard = -1;
static bool worker_has_gil_state;

typedef struct {
    void *regs[35];
    uint8_t stack[MAX_C_STACK] __attribute__((aligned(8)));
    size_t stack_size;
    void **pystack;
    size_t pywords;
    bool valid;
} snapshot_t;
static snapshot_t snapshots[2];

// Index 0 is the primary interpreter; the firmware permits one worker.
static unsigned worker_index(void) {
    unsigned id;
    __asm__ volatile ("cogid %0" : "=r"(id));
    return id != 0;
}

static void check_stop(void) {
    if (stopping && worker_index()) {
        // Called only when outside the hardware ticket lock and without GIL.
        // Main waits for this acknowledgement before stopping the cog.
        worker_stopped = 1;
        for (;;) {
            __asm__ volatile ("waitx #128");
        }
    }
}

static void guard_enter(void) {
    unsigned ok;
    do {
        check_stop();
        __asm__ volatile ("locktry %1 wc\n\twrc %0" : "=r"(ok) : "r"(ticket_guard) : "memory");
    } while (!ok);
}

static void guard_exit(void) {
    __asm__ volatile ("lockrel %0" :: "r"(ticket_guard) : "memory");
}

void *p2_thread_stack_base(void) {
    return worker_index() ? worker_stack : _stack_bottom;
}

void p2_thread_pystack_init(void) {
    mp_pystack_init(worker_pystack, worker_pystack + MP_ARRAY_SIZE(worker_pystack));
}

mp_state_thread_t *mp_thread_get_state(void) {
    return worker_index() ? worker_state : &mp_state_ctx.thread;
}

void mp_thread_set_state(mp_state_thread_t *state) {
    if (worker_index()) {
        worker_state = state;
    }
}

mp_uint_t mp_thread_get_id(void) {
    return worker_index() ? (mp_uint_t)(worker_id + 1) : 1;
}

void p2_thread_init(void) {
    if ((uintptr_t)_stack_top - (uintptr_t)_stack_bottom > MAX_C_STACK) {
        nlr_jump_fail(NULL);
    }
    if (ticket_guard < 0) {
        __asm__ volatile ("locknew %0 wc\n\tif_c neg %0, #1" : "=r"(ticket_guard));
        if (ticket_guard < 0) {
            nlr_jump_fail(NULL);
        }
    }
    stopping = worker_stopped = 0;
    worker_has_gil_state = false;
    snapshots[0].valid = snapshots[1].valid = false;
}

void mp_thread_mutex_init(mp_thread_mutex_t *mutex) {
    mutex->serving = mutex->next = 0;
}

int mp_thread_mutex_lock(mp_thread_mutex_t *mutex, int wait) {
    guard_enter();
    if (!wait && mutex->next != mutex->serving) {
        guard_exit();
        return 0;
    }
    uint32_t ticket = mutex->next++;
    guard_exit();
    while (mutex->serving != ticket) {
        check_stop();
        __asm__ volatile ("waitx #64" ::: "memory");
    }
    __asm__ volatile ("" ::: "memory");
    return 1;
}

static void snapshot_active_stack(void) {
    unsigned index = worker_index();
    snapshot_t *out = &snapshots[index];
    uintptr_t end = p2_thread_capture(out->regs);
    uint8_t *base = p2_thread_stack_base();
    size_t size = end - (uintptr_t)base;
    if (size > sizeof(out->stack)) {
        nlr_jump_fail(NULL);
    }
    memcpy(out->stack, base, size);
    out->stack_size = size;
    out->pystack = (void **)MP_STATE_THREAD(pystack_start);
    out->pywords = (MP_STATE_THREAD(pystack_cur) - MP_STATE_THREAD(pystack_start)) / sizeof(void *);
    out->valid = true;
}

void mp_thread_mutex_unlock(mp_thread_mutex_t *mutex) {
    if (mutex == &MP_STATE_VM(gil_mutex) && worker_entry != NULL
        && (!worker_index() || worker_has_gil_state)) {
        snapshot_active_stack();
    }
    guard_enter();
    ++mutex->serving;
    guard_exit();
}

void p2_thread_gc_other(void) {
    snapshot_t *other = &snapshots[1 - worker_index()];
    if (other->valid) {
        gc_collect_root(other->regs, MP_ARRAY_SIZE(other->regs));
        p2_scan_stack(other->stack, other->stack_size);
        if (other->pywords) {
            gc_collect_root(other->pystack, other->pywords);
        }
    }
}

void p2_thread_yield(void) {
    if (worker_entry != NULL) {
        MP_THREAD_GIL_EXIT();
        __asm__ volatile ("waitx #128");
        MP_THREAD_GIL_ENTER();
    } else {
        __asm__ volatile ("waitx #128");
    }
}

mp_uint_t mp_thread_create(void *(*entry)(void *), void *arg, size_t *stack_size) {
    if (stopping || worker_index() || worker_entry != NULL) {
        mp_raise_OSError(MP_EBUSY);
    }
    if (*stack_size == 0) {
        *stack_size = MAX_C_STACK;
    }
    if (*stack_size < 8192 || *stack_size > MAX_C_STACK) {
        mp_raise_ValueError(MP_ERROR_TEXT("stack size must be 8192..16384"));
    }
    if (worker_id < 0) {
        worker_id = p2_thread_launch(worker_stack);
        if (worker_id < 0) {
            mp_raise_OSError(MP_EBUSY);
        }
    }
    MP_STATE_PORT(p2_worker_arg) = arg;
    __asm__ volatile ("" ::: "memory");
    worker_entry = entry;
    return (mp_uint_t)(worker_id + 1);
}

void p2_thread_worker(void) {
    for (;;) {
        while (worker_entry == NULL) {
            check_stop();
            __asm__ volatile ("waitx #128");
        }
        worker_entry(MP_STATE_PORT(p2_worker_arg));
        __asm__ volatile ("" ::: "memory");
        worker_entry = NULL;
    }
}

void mp_thread_start(void) {
    worker_has_gil_state = true;
}

void mp_thread_finish(void) {
    // The upstream thread entry only releases the GIL and returns after this.
    snapshots[1].valid = false;
    worker_has_gil_state = false;
    MP_STATE_PORT(p2_worker_arg) = NULL;
}

void p2_thread_stop_other(void) {
    stopping = 1;
    if (worker_id >= 0) {
        while (!worker_stopped) {
            __asm__ volatile ("waitx #128" ::: "memory");
        }
        __asm__ volatile ("cogstop %0" :: "r"(worker_id) : "memory");
        worker_id = -1;
    }
    worker_entry = NULL;
    worker_state = NULL;
    worker_has_gil_state = false;
    snapshots[0].valid = snapshots[1].valid = false;
    MP_STATE_PORT(p2_worker_arg) = NULL;
}
