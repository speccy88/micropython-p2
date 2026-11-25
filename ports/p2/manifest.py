# SPDX-License-Identifier: MIT
include("$(MPY_DIR)/extmod/asyncio")
require("unittest")
# Directory iteration differs between build hosts. Keep the order that was
# used to assign frozen qstrs and lay out the kit.2 Edge image.
freeze(
    "$(PORT_DIR)/modules",
    ("p2devices.py", "p2overlay.py", "p2signals.py", "p2memory.py", "p2array.py"),
)
