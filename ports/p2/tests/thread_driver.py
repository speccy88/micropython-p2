"""Threaded hardware acceptance. Prepend DRIVER_IMAGE = <checksum.p2d bytes>."""

import _thread
import gc
import p2
import time


def wait(predicate, label):
    start = time.ticks_ms()
    while not predicate():
        if time.ticks_diff(time.ticks_ms(), start) >= 5000:
            raise RuntimeError(label)
        time.sleep_ms(1)


def rejected(code, function, *args):
    try:
        function(*args)
    except OSError as exc:
        assert exc.args[0] == code, exc
    else:
        raise AssertionError("missing driver error")


def requests(client, base):
    for i in range(12):
        # A request spans several mailbox operations. Serialize the packet
        # and its matching response, including the native completion wait.
        with gate:
            sequence = client.word(2) + 1
            client.word(6, base + i)
            client.word(4, 1)
            client.word(1, sequence)
            wait(lambda: client.word(2) == sequence, "native service timeout")
            assert client.word(3) == 0 and client.word(5) == base + i
        garbage = bytearray(257 + i)
        gc.collect()
        assert len(garbage) == 257 + i


def worker():
    try:
        client = p2.get_driver(cog)
        rejected(1, client.stop)
        rejected(1, p2.Driver, DRIVER_IMAGE)
        requests(client, 7000)
        status.append("ready")
        wait(lambda: len(status) == 2, "stop timeout")
        rejected(19, client.word, 0)
        status.append("done")
    except Exception as exc:
        status.append(repr(exc))


gate = _thread.allocate_lock()
status = []
driver = p2.Driver(DRIVER_IMAGE, pins=(5,))
cog = driver.id()
del driver
gc.collect()
try:
    _thread.start_new_thread(worker, ())
    requests(p2.get_driver(cog), 500)
    wait(lambda: status, "worker timeout")
    assert status == ["ready"], status
    assert p2.get_driver(cog).word(2) == 24
finally:
    p2.get_driver(cog).stop()
assert p2.pin_owner(5) == "free"
status.append("stopped")
wait(lambda: len(status) == 3, "worker shutdown")
assert status[-1] == "done", status
print("P2_THREADED_SERVICE_PASS", cog, 24)
