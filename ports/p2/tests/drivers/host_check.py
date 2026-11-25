"""Run host package tests and compile examples with the matching mpy-cross."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
PORT = HERE.parents[1]
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mpy-cross", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    status = {}
    class Result(unittest.TextTestResult):
        def addSuccess(self, test):
            super().addSuccess(test)
            status[test.id()] = "pass"
        def addFailure(self, test, error):
            super().addFailure(test, error)
            status[test.id()] = self._exc_info_to_string(error, test)
        def addError(self, test, error):
            super().addError(test, error)
            status[test.id()] = self._exc_info_to_string(error, test)
    suite = unittest.defaultTestLoader.discover(str(HERE))
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, resultclass=Result).run(suite)
    compiler = args.mpy_cross.resolve()
    version = subprocess.check_output([compiler, "--version"], text=True).strip()
    sources = sorted((*PORT.glob("modules/*.py"), *PORT.glob("packages/*/*.py"), *PORT.glob("examples/*.py"),
                      HERE / "api.py", HERE / "array_smoke.py", HERE / "pwm_capture.py",
                      HERE / "bounds32.py", HERE / "factorial_bench.py", HERE / "borrowed_io.py",
                      PORT / "examples/hubdriver/checksum.py"))
    bytecode = {}
    with tempfile.TemporaryDirectory() as tmp:
        for source in sources:
            dest = Path(tmp) / (source.stem + ".mpy")
            name = source.relative_to(PORT).as_posix()
            subprocess.run([compiler, "-s", name, "-o", dest, source], check=True)
            payload = dest.read_bytes()
            bytecode[name] = {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
    report = {"scope": "CPython recording devices and host bytecode compilation",
              "mpy_cross": version, "tests": status, "compiled": bytecode}
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(stream.getvalue().rstrip())
    print(f"{len(bytecode)} sources compiled with {version}")
    return 0 if result.wasSuccessful() else 1

if __name__ == "__main__":
    raise SystemExit(main())
