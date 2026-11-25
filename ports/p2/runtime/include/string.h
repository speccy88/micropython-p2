// SPDX-License-Identifier: MIT
#ifndef MICROPY_P2_STRING_H
#define MICROPY_P2_STRING_H
#include <stddef.h>

void *memcpy(void *restrict dst, const void *restrict src, size_t n);
void *memmove(void *dst, const void *src, size_t n);
void *memset(void *dst, int ch, size_t n);
int memcmp(const void *a, const void *b, size_t n);
void *memchr(const void *src, int ch, size_t n);
size_t strlen(const char *s);
char *strchr(const char *s, int ch);
char *strrchr(const char *s, int ch);
char *strstr(const char *s, const char *needle);
char *strcpy(char *restrict dst, const char *restrict src);
char *strncpy(char *restrict dst, const char *restrict src, size_t n);
int strcmp(const char *a, const char *b);
int strncmp(const char *a, const char *b, size_t n);
#endif
