#!/usr/bin/env python3
"""Host-side UART capture for the ZedBoard (J14, /dev/ttyACM0, 115200 8N1): every line with a timestamp, flushed at once.

    software/board/uart_capture.py --out data/board/2026-10-25/t3_r0.log [--port /dev/ttyACM0] [--baud 115200] [--seconds N]

Each line of the log:  <ISO time, ms> +<seconds since the capture opened>s | <text from the board>
The first line is a '# capture started ...' header; it is written only AFTER the port is open, so a caller can wait for it before starting the ARM program.
Stops on SIGTERM / SIGINT (or after --seconds) and writes a '# capture stopped' line.  Only one program may read the port: close picocom first.
The firmware is not touched: the per-frame lines ('  frame N: total ... us') are already printed by software/board/sr_app/main.c (T3, T7).
"""
import argparse
import signal
import sys
import time
from datetime import datetime

import serial


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--seconds", type=float, default=0, help="stop after this many seconds (0 = until SIGTERM/SIGINT)")
    a = ap.parse_args()

    try:
        ser = serial.Serial(a.port, a.baud, timeout=0.2)
    except (serial.SerialException, OSError) as e:
        print(f"uart_capture: cannot open {a.port}: {e}", file=sys.stderr)
        return 3

    stop = []
    for s in (signal.SIGTERM, signal.SIGINT):
        signal.signal(s, lambda *_: stop.append(1))

    t0 = time.monotonic()
    buf = b""
    nlines = 0
    with open(a.out, "w", buffering=1) as f:
        def put(text: str) -> None:
            nonlocal nlines
            now = datetime.now()
            f.write(f"{now.strftime('%Y-%m-%d %H:%M:%S.')}{now.microsecond // 1000:03d} +{time.monotonic() - t0:9.3f}s | {text}\n")
            nlines += 1

        f.write(f"# capture started {datetime.now().isoformat(timespec='milliseconds')} port {a.port} {a.baud} 8N1\n")
        f.flush()
        while not stop and not (a.seconds and time.monotonic() - t0 >= a.seconds):
            try:
                chunk = ser.read(4096)
            except (serial.SerialException, OSError) as e:
                f.write(f"# read error: {e}\n")
                break
            if not chunk:
                continue
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                put(line.rstrip(b"\r").decode("ascii", "replace"))
        # drain what is still in the driver, then the unterminated tail
        try:
            buf += ser.read(ser.in_waiting)
        except (serial.SerialException, OSError):
            pass
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            put(line.rstrip(b"\r").decode("ascii", "replace"))
        if buf.strip():
            put(buf.rstrip(b"\r").decode("ascii", "replace") + "   [no line end]")
        f.write(f"# capture stopped {datetime.now().isoformat(timespec='milliseconds')}, {nlines} lines\n")
    ser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
