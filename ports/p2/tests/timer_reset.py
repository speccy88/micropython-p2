"""Host-side soft-reset check for machine.Timer on a running RAM image."""

import argparse
from mpremote.transport_serial import SerialTransport


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    board = SerialTransport(parser.parse_args().port)
    try:
        board.enter_raw_repl(soft_reset=True)
        for _ in range(3):
            board.exec(
                "from machine import Timer\n"
                "old = Timer(period=200, callback=lambda _: print('stale callback'))"
            )
            board.enter_raw_repl(soft_reset=True)
            result = board.exec(
                "from machine import Timer\n"
                "import time\nseen = []\n"
                "Timer(period=10, mode=Timer.ONE_SHOT, "
                "callback=lambda _: seen.append(1))\n"
                "time.sleep_ms(230)\nprint(seen)"
            )
            assert result.strip() == b"[1]", result
        print("Timer passed three soft resets with an active periodic callback")
    finally:
        board.close()


if __name__ == "__main__":
    main()
