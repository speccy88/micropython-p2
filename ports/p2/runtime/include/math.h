// SPDX-License-Identifier: MIT
#ifndef MICROPY_P2_MATH_H
#define MICROPY_P2_MATH_H
#include_next <math.h>
#include <stdint.h>

// MicroPython's fdlibm sources use newlib/BSD internal type spellings.
typedef uint8_t __uint8_t;
typedef uint32_t __uint32_t;
typedef int32_t __int32_t;
#undef HUGE
#undef isnan
#undef isinf
#define isnan(x) __builtin_isnan(x)
#define isinf(x) __builtin_isinf(x)
#undef fpclassify
#define fpclassify(x) __builtin_fpclassify(FP_NAN, FP_INFINITE, FP_NORMAL, FP_SUBNORMAL, FP_ZERO, (x))
#endif
