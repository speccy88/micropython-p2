"""Exercise probe chains across deletion, tombstone reuse, growth and GC."""

import gc


class Key:
    def __init__(self, value):
        self.value = value

    def __hash__(self):
        return self.value & 3

    def __eq__(self, other):
        return type(other) is Key and other.value == self.value


seen = set()
mapping = {}
for cycle in range(5):
    for i in range(100):
        seen.add(Key(i))
        mapping[Key(i)] = i + cycle
    gc.collect()
    for i in range(100):
        assert Key(i) in seen and mapping[Key(i)] == i + cycle
    for i in range(cycle, 100, 3):
        seen.remove(Key(i))
        del mapping[Key(i)]
    assert len(mapping) == len(seen)
    for i in range(100):
        expected = i < cycle or (i - cycle) % 3 != 0
        assert (Key(i) in seen) == expected and (Key(i) in mapping) == expected
assert len(set([42] * 100)) == 1
print("COLLISIONS_PASS")
