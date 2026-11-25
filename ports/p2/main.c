// SPDX-License-Identifier: MIT
#include <stdint.h>
#include <string.h>
#include "py/runtime.h"
#include "py/cstack.h"
#include "py/gc.h"
#include "py/mphal.h"
#include "py/pystack.h"
#include "shared/runtime/pyexec.h"
#include "drivers/p2resources.h"
#if !P2_PROFILE_THREADED
#include "shared/runtime/softtimer.h"
#endif

extern uint8_t _stack_bottom[], _stack_top[], _heap_start[], _heap_end[];
#if MICROPY_VFS_FAT
extern void p2_storage_mount(void);
extern void p2_storage_reset(void);
extern void p2_unmount_filesystems(void);
#endif
// 8 KiB traced by gc_collect_start and rewound by the upstream NLR unwinder.
static mp_obj_t pystack[2048] __attribute__((aligned(8)));
void *p2_gc_registers[36] __attribute__((aligned(4)));

void p2_scan_stack(const void *base, size_t bytes) {
    // P2 LLVM permits byte-aligned C frames. Only load a candidate when all
    // four bytes lie in the active stack; memcpy has no alignment contract.
    uintptr_t end = (uintptr_t)base + bytes;
    for (uintptr_t addr = (uintptr_t)base; addr + sizeof(void *) <= end; ++addr) {
        uintptr_t candidate;
        __builtin_memcpy(&candidate, (void *)addr, sizeof(candidate));
        if (candidate >= (uintptr_t)_heap_start && candidate < (uintptr_t)_heap_end
            && (candidate & (sizeof(void *) - 1)) == 0) {
            void *root = (void *)candidate;
            gc_collect_root(&root, 1);
        }
    }
}

void p2_gc_collect_saved(void) {
    #if MICROPY_VFS_FAT
    // File finalisers can call Python block-device methods which allocate.
    // Keep the finaliser table stable without locking out such allocations.
    if (p2_vm_resetting) {
        return;
    }
    #endif
    gc_collect_start();
    #if !P2_PROFILE_THREADED
    soft_timer_gc_mark_all();
    #endif
    gc_collect_root(p2_gc_registers, 35);
    #if P2_PROFILE_THREADED
    uint8_t *base = p2_thread_stack_base();
    p2_thread_gc_other();
    #else
    uint8_t *base = _stack_bottom;
    #endif
    p2_scan_stack(base, (uintptr_t)p2_gc_registers[35] - (uintptr_t)base);
    gc_collect_end();
}

#if !P2_PROFILE_THREADED
// gc_sweep_all calls this after user finalisers, while every hub object is
// still intact. A finaliser cannot leave an existing pin or driver running.
void p2_quiesce_devices(void) {
    p2_timer_reset();
    #if MICROPY_VFS_FAT
    p2_storage_reset();
    #endif
    p2_drivers_reset();
}
#endif

void main(void) {
    for (;;) {
        #if P2_PROFILE_THREADED
        p2_thread_init();
        #else
        p2_vm_resetting = false;
        #endif
        mp_cstack_init_with_top(_stack_bottom, (uintptr_t)_stack_top - (uintptr_t)_stack_bottom);
        mp_pystack_init(pystack, pystack + MP_ARRAY_SIZE(pystack));
        gc_init(_heap_start, _heap_end);
        mp_init();
        #if P2_TEST_GC_ROOTS
        extern unsigned p2_gc_test_roots(void);
        mp_printf(&mp_plat_print, "P2 GC roots: %u/7\n", p2_gc_test_roots());
        #endif
        mp_obj_list_append(mp_sys_path, MP_OBJ_NEW_QSTR(MP_QSTR__slash_lib));
        #if MICROPY_VFS_FAT
        p2_storage_mount();
        #endif

        // A raw-mode soft reboot skips startup scripts for filesystem repair.
        int status = 0;
        if (pyexec_mode_kind == PYEXEC_MODE_FRIENDLY_REPL) {
            status = pyexec_file_if_exists("boot.py");
            if (status != 0 && !(status & PYEXEC_FORCED_EXIT)) {
                status = pyexec_file_if_exists("main.py");
            }
        }
        while (!(status & PYEXEC_FORCED_EXIT)) {
            int ret = pyexec_mode_kind == PYEXEC_MODE_RAW_REPL ? pyexec_raw_repl() : pyexec_friendly_repl();
            if (ret) {
                break;
            }
        }
        mp_hal_set_interrupt_char(-1);
        #if !P2_PROFILE_THREADED
        p2_vm_resetting = true;
        #endif
        mp_sched_lock();
        #if MICROPY_VFS_FAT
        gc_run_reset_finalisers();
        p2_unmount_filesystems();
        #endif
        #if P2_PROFILE_THREADED
        p2_thread_stop_other();
        #endif
        gc_sweep_all();
        mp_sched_unlock();
        mp_deinit();
        mp_hal_stdout_tx_str("MPY: soft reboot\r\n");
    }
}

void nlr_jump_fail(void *value) {
    (void)value;
    mp_hal_stdout_tx_str("\r\nFATAL: uncaught exception in the P2 runtime\r\n");
    for (;;) {
        __asm__ volatile ("waitx #511");
    }
}
