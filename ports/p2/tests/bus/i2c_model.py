"""Compile the firmware's SoftI2C bit engine against a scripted open-drain bus."""

import os
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def between(source, begin, end):
    start = source.index(begin) + len(begin)
    return source[start : source.index(end, start)]


def main():
    # This is the same compilation unit as the Unix build uses for its Python
    # bindings. Select the complete low-level section without linking a VM or
    # maintaining a second copy of any firmware logic.
    core = (ROOT / "extmod/machine_i2c.c").read_text()
    engine = between(
        core, "#if MICROPY_PY_MACHINE_SOFTI2C\n", "#endif // MICROPY_PY_MACHINE_SOFTI2C"
    )
    adapter = (ROOT / "ports/p2/bus/i2c.c").read_text()
    cleanup = between(adapter, "\nstatic int checked(", "\nstatic int start(")
    with tempfile.TemporaryDirectory() as workspace:
        tmp = Path(workspace)
        (tmp / "wire.inc").write_text(engine + "\nstatic int checked(" + cleanup)
        exe = tmp / "i2c-model"
        subprocess.run(
            [
                os.environ.get("CC", "cc"),
                "-std=c11",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-I",
                str(tmp),
                HERE / "i2c_model.c",
                "-o",
                exe,
            ],
            check=True,
        )
        subprocess.run([exe], check=True)


if __name__ == "__main__":
    main()
