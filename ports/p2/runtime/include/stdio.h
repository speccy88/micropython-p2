// SPDX-License-Identifier: MIT
#ifndef MICROPY_P2_STDIO_H
#define MICROPY_P2_STDIO_H
#include <stdarg.h>
#include <stddef.h>

#define EOF (-1)
#define SEEK_SET 0
#define SEEK_CUR 1
#define SEEK_END 2
int printf(const char *format, ...);
int vprintf(const char *format, va_list args);
int snprintf(char *dst, size_t size, const char *format, ...);
int vsnprintf(char *dst, size_t size, const char *format, va_list args);
int putchar(int ch);
int puts(const char *str);
#endif
