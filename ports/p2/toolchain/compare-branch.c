// A tombstone test and the independent candidate-slot test both use C/Z.
extern int equal(void *, void *);
extern unsigned hash(void *);

void *probe(void **table, unsigned count, void *key, int add) {
    unsigned pos = hash(key) % count;
    void **available = 0;
    for (;;) {
        void **slot = &table[pos];
        void *entry = *slot;
        if (entry == 0) {
            if (!add) {
                return 0;
            }
            if (!available) {
                available = slot;
            }
            *available = key;
            return key;
        } else if (entry == (void *)4) {
            if (!available) {
                available = slot;
            }
        } else if (equal(entry, key)) {
            return entry;
        }
        pos = (pos + 1) % count;
    }
}

