"""External block storage for a region returned by p2.PSRAM().alloc()."""
# SPDX-License-Identifier: MIT


class BlockDevice:
    """512-byte sectors implementing MicroPython simple and extended protocols."""

    def __init__(self, region):
        size = region.capacity()
        if size == 0 or size % 512:
            raise ValueError("region must contain whole 512-byte sectors")
        self.region = region
        self.blocks = size // 512

    def _address(self, block, buf, offset):
        if block < 0 or block >= self.blocks:
            raise ValueError("block outside region")
        if offset is None:
            if len(buf) % 512:
                raise ValueError("transfer must contain whole sectors")
            offset = 0
        elif not 0 <= offset < 512:
            raise ValueError("offset outside sector")
        return block * 512 + offset

    def readblocks(self, block, buf, offset=None):
        self.region.readinto(self._address(block, buf, offset), buf)
        return 0

    def writeblocks(self, block, buf, offset=None):
        self.region.write(self._address(block, buf, offset), buf)
        return 0

    def ioctl(self, op, arg):
        if op in (1, 2, 3):
            return 0
        if op == 4:
            return self.blocks
        if op == 5:
            return 512
        if op == 6:
            if not 0 <= arg < self.blocks:
                raise ValueError("block outside region")
            self.region.fill(arg * 512, 512, 255)
            return 0
        return None
