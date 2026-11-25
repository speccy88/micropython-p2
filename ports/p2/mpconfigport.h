// SPDX-License-Identifier: MIT
#pragma once
#include <stdint.h>
#include "bus/mpconfig.h"

#define MICROPY_HW_MCU_NAME "Propeller 2"
#ifndef MICROPY_HW_BOARD_NAME
#if P2_BOARD_HAS_PSRAM
#define MICROPY_HW_BOARD_NAME "P2-EC32MB"
#else
#define MICROPY_HW_BOARD_NAME "P2 Edge"
#endif
#endif
#define MICROPY_PY_SYS_PLATFORM "p2"
#define MICROPY_CONFIG_ROM_LEVEL MICROPY_CONFIG_ROM_LEVEL_CORE_FEATURES
#define MICROPY_ENABLE_COMPILER (1)
#define MICROPY_ENABLE_SOURCE_LINE (1)
#define MICROPY_ENABLE_GC (1)
#define MICROPY_ENABLE_FINALISER (1)
#define MICROPY_ENABLE_PYSTACK (1)
#define MICROPY_ENABLE_SCHEDULER (1)
#define MICROPY_ENABLE_EMERGENCY_EXCEPTION_BUF (1)
#define MICROPY_NLR_SETJMP (1)
#define MICROPY_CSTACK_GROWS_UP (1)
#define MICROPY_CSTACK_GET_SP() p2_stack_pointer()
#define MICROPY_STACK_CHECK (1)
#define MICROPY_STACK_CHECK_MARGIN (2048)
#define MICROPY_USE_INTERNAL_ERRNO (1)
#define MICROPY_KBD_EXCEPTION (1)
#define MICROPY_HELPER_REPL (1)
#define MICROPY_REPL_AUTO_INDENT (1)
#define MICROPY_PERSISTENT_CODE_LOAD (1)
#define MICROPY_READER_VFS (1)
#define MICROPY_VFS (1)
#define MICROPY_FATFS_RPATH (2)
#define MICROPY_FATFS_NORTC (1)
#define MICROPY_FATFS_ENABLE_LFN (2)
#if MICROPY_VFS_FAT
#define MICROPY_GC_RESET_FINALISER(obj) p2_is_filesystem_stream(obj)
int p2_is_filesystem_stream(const void *obj);
#endif
#define MICROPY_PY_MACHINE (0)
// Translate MP_STREAM_ERROR/EAGAIN to None or a partial count on UART timeout.
#define MICROPY_STREAMS_NON_BLOCK (P2_ENABLE_BUSES)
#define MICROPY_PY_OS (1)
#define MICROPY_PY_TIME (1)
#define MICROPY_PY_SYS_STDFILES (1)
#define MICROPY_PY_SYS_STDIO_BUFFER (1)
#define MICROPY_PY_JSON (1)
#define MICROPY_PY_BUILTINS_MEMORYVIEW (1)
#define MICROPY_PY_BUILTINS_BYTES_HEX (1)
#define MICROPY_PY_ARRAY_SLICE_ASSIGN (1)
#define MICROPY_PY_BUILTINS_ROUND_INT (1)
#define MICROPY_PY_SYS_MAXSIZE (1)
#define MICROPY_PY_MICROPYTHON_STACK_USE (1)
#if P2_PROFILE_THREADED
#define MICROPY_PY_THREAD (1)
#define MICROPY_PY_THREAD_GIL (1)
#define MICROPY_PY_THREAD_GIL_VM_DIVISOR (64)
#define MICROPY_THREAD_CSTACK_BASE() p2_thread_stack_base()
#define MICROPY_THREAD_PYSTACK_INIT() p2_thread_pystack_init()
void *p2_thread_stack_base(void);
void p2_thread_pystack_init(void);
#endif
#define MICROPY_LONGINT_IMPL MICROPY_LONGINT_IMPL_MPZ
#define MICROPY_ALLOC_PATH_MAX (128)
#define MICROPY_REPL_STDIN_BUFFER_MAX (256)
#define MICROPY_STACKLESS (0)
#define MP_SSIZE_MAX (0x7fffffff)
#define MP_STATE_PORT MP_STATE_VM
// Clang diagnoses upstream's sizeof(char[...]) on distinct extern addresses
// as a VLA. A bit-field preserves compile-time rejection of known-false tests
// while allowing -Werror=vla to reject real dynamic stack frames.
#define MP_STATIC_ASSERT_NONCONSTEXPR(cond) ((void)sizeof(struct { unsigned p2_check : \
                                                                   __builtin_choose_expr(__builtin_constant_p(cond), (cond), 1) ? 1 : -1; }))

#if P2_PROFILE_EDGE
#define MICROPY_PY_ERRNO (1)
#define MICROPY_FLOAT_IMPL MICROPY_FLOAT_IMPL_FLOAT
#define MICROPY_PY_BUILTINS_COMPLEX (0)
#define MICROPY_PY_MATH (1)
#define MICROPY_PY_SELECT (1)
#define MICROPY_PY_ASYNCIO (1)
#endif
#define MICROPY_VM_HOOK_LOOP p2_console_poll_interrupt();
#if !P2_PROFILE_THREADED
#define MICROPY_GC_RESET_QUIESCE() p2_quiesce_devices()
void p2_quiesce_devices(void);
#endif

typedef long mp_off_t;
uintptr_t p2_stack_pointer(void);
void p2_console_poll_interrupt(void);
