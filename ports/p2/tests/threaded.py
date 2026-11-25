"""Volatile, two-cog regression. Run only with PROFILE=threaded."""
import _thread
import gc
import json
import time


def wait_for(state):
    start = time.ticks_ms()
    while status[0] != state:
        if time.ticks_diff(time.ticks_ms(), start) > 5000:
            raise AssertionError(("thread handshake timeout", state, status))
        time.sleep_ms(2)


def worker():
    # The main thread sees only the acknowledgement and a checksum. The
    # allocation remains reachable solely from the worker frame during GC.
    retained = bytearray(117)
    retained[0] = 17
    retained[-1] = 97
    status[0] = 1
    gate.acquire()
    gate.release()
    gc.collect()  # Other cog must retain the main function's local object.
    status[1] = retained[0] + retained[-1]
    status[2] = _thread.get_ident()
    status[0] = 2


def run():
    retained = bytearray(63)
    retained[-1] = 211
    if not gate.acquire(0) or gate.acquire(0):
        raise AssertionError("nonblocking mutex")
    ident = _thread.start_new_thread(worker, ())
    wait_for(1)
    try:
        _thread.start_new_thread(worker, ())
    except OSError:
        pass
    else:
        raise AssertionError("accepted second worker")
    start = time.ticks_us()
    for i in range(25):
        bytearray(187 + i)
        gc.collect()
    gc_elapsed = time.ticks_diff(time.ticks_us(), start)
    gate.release()
    wait_for(2)
    if (retained[-1], status[1], status[2]) != (211, 114, ident):
        raise AssertionError("cross-cog GC or return identity")
    print(json.dumps({"test": "two_threads", "passed": True,
                      "main_id": _thread.get_ident(), "worker_id": ident,
                      "gc_25_wall_us": gc_elapsed}))


gate = _thread.allocate_lock()
status = [0, 0, 0]
run()
