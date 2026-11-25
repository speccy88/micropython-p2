"""Cross-check the burst and scalar PSRAM paths, including partial hub buffers."""

from p2 import PSRAM


def check():
    ram = PSRAM()
    region = ram.alloc(4352)
    try:
        # 128 logical bytes span 32 bytes on each chip; 4096 span 1024.
        for boundary in (16, 128, 4096):
            for offset in (boundary - 1, boundary, boundary + 1):
                for count in (15, 16, 17, 33):
                    src = bytearray(count + 2)
                    for i in range(count + 2):
                        src[i] = (offset + i * 73) & 255
                    for skew in (0, 1):
                        payload = memoryview(src)[skew : skew + count]
                        region.fill(offset - 1, count + 2, 0x5A)
                        assert region.write(offset, payload) == count
                        assert region.diagnostics()["completed"] == count
                        assert region.read(offset - 1, 1) == b"Z"
                        assert region.read(offset + count, 1) == b"Z"
                        # Read one byte per transaction through the independent path.
                        for i in range(count):
                            assert region.read(offset + i, 1)[0] == payload[i]
                        # Read back through a view with the opposite alignment.
                        dst = bytearray(count + 2)
                        view = memoryview(dst)[1 - skew : 1 - skew + count]
                        assert region.readinto(offset, view) == count
                        assert bytes(view) == bytes(payload)
        print("P2_BURST_BOUNDS_PASS", region.diagnostics()["max_cycles"])
    finally:
        region.close()


check()
