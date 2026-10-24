#!/usr/bin/env python3
"""PC test of software/board/uart_capture.py and board_run.sh, no board needed: a pseudo-terminal plays the ZedBoard's UART and a fake `xsdb` plays the JTAG tool.

    .venv/bin/python software/board/test_uart_capture.py        (from the project root; ~15 s; exit 0 = all PASS)

What it proves: lines (also split across reads, CRLF, an unterminated tail) arrive in order with timestamps; the wrapper starts the capture before xsdb, keeps the per-frame lines,
writes the meta file, stops the capture by PID, fails with exit 1 when xsdb hangs (hard timeout), and exit 3 when the port cannot be opened.
What it does NOT prove: anything about the real /dev/ttyACM0, the real xsdb, or the board.
"""
import os
import pty
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAP = ROOT / "software/board/uart_capture.py"
RUN = ROOT / "software/board/board_run.sh"
PY = ROOT / ".venv/bin/python"
fails = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + ("  " + extra if extra and not cond else ""))
    if not cond:
        fails.append(name)


def feeder(master, chunks, t_between=0.3):
    def run():
        time.sleep(1.0)  # the capture must be open (it announces that in the log; the wrapper waits for it)
        for c in chunks:
            os.write(master, c)
            time.sleep(t_between)
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


def test_capture(tmp):
    master, slave = pty.openpty()
    port = os.ttyname(slave)
    log = tmp / "cap.log"
    p = subprocess.Popen([str(PY), str(CAP), "--out", str(log), "--port", port])
    for _ in range(50):
        if log.exists() and "# capture started" in log.read_text():
            break
        time.sleep(0.1)
    check("capture: header written once the port is open", "# capture started" in log.read_text())
    chunks = [b"\r\n--- SR accelerator test ---\r\ninit ok: VER", b"SION 0x53520602\r\n", b"  frame 1: total 1311000 us = pad 5900\r\n",
              b"  frame 2: total 1311500 us = pad 5900\r\n", b"unterminated tail"]
    for c in chunks:
        os.write(master, c)
        time.sleep(0.25)
    time.sleep(0.5)
    p.send_signal(signal.SIGTERM)
    rc = p.wait(timeout=10)
    txt = log.read_text()
    lines = [x for x in txt.splitlines() if " | " in x]
    check("capture: exit 0 on SIGTERM", rc == 0, str(rc))
    check("capture: line split across two reads is joined", any(x.endswith("| init ok: VERSION 0x53520602") for x in lines), txt)
    check("capture: both frame lines kept in order", [x.split("| ")[1][:10] for x in lines if "frame" in x] == ["  frame 1:", "  frame 2:"], txt)
    check("capture: CR removed", "\r" not in txt)
    check("capture: unterminated tail is kept and marked", any("unterminated tail   [no line end]" in x for x in lines), txt)
    check("capture: timestamps look like 'YYYY-MM-DD HH:MM:SS.mmm +x.xxxs'", all(re.match(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3} \+ *\d+\.\d{3}s \| ", x) for x in lines), txt)
    check("capture: footer with line count", re.search(r"# capture stopped .*, \d+ lines", txt) is not None, txt)
    os.close(master)
    os.close(slave)


def fake_xsdb(dirpath, body):
    f = dirpath / "xsdb"
    f.write_text("#!/usr/bin/env bash\n" + body + "\n")
    f.chmod(f.stat().st_mode | stat.S_IEXEC)


def run_wrapper(tmp, port, xsdb_body, day, extra_env=None, name="tx"):
    bindir = tmp / ("bin_" + name)
    bindir.mkdir()
    fake_xsdb(bindir, xsdb_body)
    env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}", UART_PORT=port, DAY=day, SR_BIT=str(ROOT / "software/board/uart_capture.py"))
    env.update(extra_env or {})
    t0 = time.time()
    tm, ts = pty.openpty()  # the wrapper's own stdin is a terminal, like at a prompt: only its `< /dev/null` keeps xsdb off it
    r = subprocess.run(["bash", str(RUN), name, str(ROOT / "software/board/uart_capture.py"), "-", "-"], cwd=ROOT, env=env,
                       capture_output=True, text=True, stdin=ts, timeout=120)
    os.close(tm)
    os.close(ts)
    return r, time.time() - t0


def test_wrapper(tmp):
    day = "test_uart_capture_tmp"
    d = ROOT / "data/board" / day
    shutil.rmtree(d, ignore_errors=True)
    try:
        # 1. normal run: fake xsdb takes 3 s and prints a marker line; the 'board' prints two frame lines meanwhile
        master, slave = pty.openpty()
        feeder(master, [b"T3: timing\r\n", b"  frame 0: total 1311400 us\r\n", b"  frame 1: total 1311900 us\r\n"], 0.4)
        r, dt = run_wrapper(tmp, os.ttyname(slave), 'sleep 3; echo "marker: result=0 bytes=0 tiles=1 fnv1a32=0x00000000"; test ! -t 0 || exit 9; exit 0', day)
        log = (d / "tx.log").read_text() if (d / "tx.log").exists() else ""
        meta = (d / "tx_meta.txt").read_text() if (d / "tx_meta.txt").exists() else ""
        check("wrapper: exit 0", r.returncode == 0, r.stdout + r.stderr)
        check("wrapper: fake xsdb got stdin closed although the wrapper's stdin is a terminal", r.returncode == 0, "rc " + str(r.returncode))
        check("wrapper: both per-frame lines in the UART log", log.count("frame ") == 2, log)
        check("wrapper: summary counts the per-frame lines", "2 per-frame lines" in r.stdout, r.stdout)
        check("wrapper: meta has git, elf md5, bitstream md5, command, xsdb_exit 0", all(k in meta for k in ("git ", "elf ", "bitstream ", "command xsdb", "xsdb_exit 0")), meta)
        check("wrapper: xsdb console saved", "marker: result=0" in (d / "tx_xsdb.log").read_text())
        check("wrapper: capture was stopped cleanly (footer present)", re.search(r"# capture stopped .*, \d+ lines\s*$", log) is not None, log)
        os.close(master)
        os.close(slave)
        # 2. hanging xsdb -> hard timeout, exit 1, message, no capture left
        master, slave = pty.openpty()
        r, dt = run_wrapper(tmp, os.ttyname(slave), "sleep 60", day, {"XSDB_TIMEOUT": "2"}, name="hang")
        check("wrapper: hanging xsdb -> exit 1 with a FAIL message", r.returncode == 1 and "FAIL xsdb did not exit within 2 s" in r.stdout, r.stdout + r.stderr)
        check("wrapper: hard timeout ends the run in well under 60 s", dt < 20, f"{dt:.1f} s")
        os.close(master)
        os.close(slave)
        # 3. port cannot be opened -> exit 3, xsdb never started
        r, dt = run_wrapper(tmp, "/dev/does_not_exist", "touch " + str(tmp / "xsdb_was_started"), day, name="noport")
        check("wrapper: missing port -> exit 3 and a clear message", r.returncode == 3 and "UART capture did not start" in r.stdout, r.stdout + r.stderr)
        check("wrapper: missing port -> xsdb not started", not (tmp / "xsdb_was_started").exists())
        # 3b. SR_TREE: another checkout (a fake one with its own run_board.tcl) -> files land in THAT tree, the meta file names THAT tree's default bitstream
        fake = tmp / "faketree"
        (fake / "software/board").mkdir(parents=True)
        (fake / "software/board/run_board.tcl").write_text('set BIT [expr {[info exists ::env(SR_BIT)] ? $::env(SR_BIT) : "/nowhere/R9q_artifacts/design_1_wrapper_R9q.bit"}]\n')
        master, slave = pty.openpty()
        feeder(master, [b"frame 0: total 1 us\r\n"], 0.3)
        bindir = tmp / "bin_tree"
        bindir.mkdir()
        fake_xsdb(bindir, "sleep 2; exit 0")
        env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}", UART_PORT=os.ttyname(slave), DAY=day)
        env["SR_TREE"] = str(fake)
        r = subprocess.run(["bash", str(RUN), "tree", str(ROOT / "software/board/uart_capture.py"), "-", "-"], cwd="/", env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
        check("SR_TREE: exit 0 and files saved under the other tree's data/board", r.returncode == 0 and (fake / "data/board" / day / "tree.log").exists(), r.stdout + r.stderr)
        check("SR_TREE: nothing written under this checkout for that run", not (d / "tree.log").exists())
        meta_t = (fake / "data/board" / day / "tree_meta.txt").read_text() if (fake / "data/board" / day / "tree_meta.txt").exists() else ""
        check("SR_TREE: meta names the other tree's default bitstream", "/nowhere/R9q_artifacts/design_1_wrapper_R9q.bit" in meta_t, meta_t)
        os.close(master)
        os.close(slave)
        # 4. SR_NO_UART=1 runs without capture
        r, dt = run_wrapper(tmp, "/dev/does_not_exist", "echo ok", day, {"SR_NO_UART": "1"}, name="nouart")
        check("wrapper: SR_NO_UART=1 -> exit 0 and says NO UART CAPTURE", r.returncode == 0 and "NO UART CAPTURE" in r.stdout, r.stdout + r.stderr)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        test_capture(tmp)
        test_wrapper(tmp)
    print(f"{'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
