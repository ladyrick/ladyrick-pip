import signal
import sys
import time


def handle_signal(sig, frame):
    print(f"received signal {sig}, {signal.Signals(sig).name}", flush=True)
    if sig in {signal.SIGTERM, signal.SIGINT, signal.SIGHUP}:
        sys.exit(0)


for sig in [s for s in vars(signal).values() if isinstance(s, signal.Signals)]:
    try:
        signal.signal(sig, handle_signal)
    except OSError:
        pass


def main():
    while True:
        time.sleep(99999)


if __name__ == "__main__":
    main()
