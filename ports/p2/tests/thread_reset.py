"""Check soft reboot while a worker is parked on a lock."""

import argparse
import json
from pathlib import Path
from mpremote.transport_serial import SerialTransport

p = argparse.ArgumentParser()
p.add_argument("--port", required=True)
p.add_argument("--output", type=Path, required=True)
args = p.parse_args()
board = SerialTransport(args.port)
samples = []
try:
    for i in range(6):
        board.enter_raw_repl(soft_reset=True)
        result = board.exec("""import _thread,time
lock=_thread.allocate_lock()
lock.acquire()
ready=[]
def worker():
    ready.append(_thread.get_ident())
    lock.acquire()
t=_thread.start_new_thread(worker,())
start=time.ticks_ms()
while not ready and time.ticks_diff(time.ticks_ms(),start)<2000:
    time.sleep_ms(5)
assert ready==[t]
print(t)""")
        samples.append(int(result.strip()))
    board.enter_raw_repl(soft_reset=True)
    ok = board.exec("print(123)").strip() == b"123"
finally:
    board.close()
report = {"worker_ids": samples, "passes": len(samples), "recovered": ok}
args.output.write_text(json.dumps(report, indent=2) + "\n")
print(report)
