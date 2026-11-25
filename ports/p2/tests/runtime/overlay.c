// Optional silicon checks for the private LLVM15 overlay.
#include <stdint.h>

extern void *probe(void **table, unsigned count, void *key, int add);

unsigned hash(void *key) {
    (void)key;
    return 0;
}
int equal(void *a, void *b) {
    return a == b;
}

static int check_ptrb(void) {
    uint32_t words[] = {11, 22, 33, 44, 55, 66, 77};
    uint32_t saved, indexed, before, after, last;
    __asm__ volatile (
        "mov %[saved], ptrb\n"
        "mov ptrb, %[base]\n"
        "rdlong %[indexed], ptrb[-2]\n"
        "rdlong %[before], ++ptrb[3]\n"
        "rdlong %[after], ptrb--[2]\n"
        "rdlong %[last], ptrb[0]\n"
        "mov ptrb, %[saved]"
        : [saved] "=&r" (saved), [indexed] "=&r" (indexed), [before] "=&r" (before),
        [after] "=&r" (after), [last] "=&r" (last)
        : [base] "r" (words + 2) : "memory");
    return indexed == 11 && before == 66 && after == 66 && last == 44;
}

static __attribute__((noinline)) unsigned urem(unsigned n, unsigned d) {
    return n % d;
}
static __attribute__((noinline)) unsigned udiv(unsigned n, unsigned d) {
    return n / d;
}

int check_overlay(void) {
    uint32_t first, value, varied = 0;
    __asm__ volatile ("getrnd %0" : "=r" (first));
    for (unsigned i = 0; i < 8; ++i) {
        __asm__ volatile ("getrnd %0" : "=r" (value));
        varied |= value ^ first;
    }
    int used, key;
    void *slots[] = {&used, (void *)4, 0};
    return varied && check_ptrb() && urem(7001, 31) == 26 && udiv(7550, 41) == 184
           && probe(slots, 3, &key, 1) == &key && slots[0] == &used && slots[1] == &key;
}
