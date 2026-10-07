#!/usr/bin/env python3
"""
Hardware test of the mixer APPLY path (X command) + watchdog keepalive.

Safe when the ESC/PWM outputs are not connected. Arms the firmware, streams
mix commands exactly like the Ground Station does (20 Hz), lets the soft-start
ramp settle, then compares the motor telemetry against tools/mixer_ref.py.

Usage: python3 tools/mixer_hw_test.py [--port /dev/cu.usbmodem1102]
"""
import os, sys, time, termios, select, argparse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from mixer_ref import Mixer, HEXA_X, YAW_ALT


class Link:
    def __init__(self, port):
        self.fd = os.open(port, os.O_RDWR | os.O_NONBLOCK | os.O_NOCTTY)
        _, _, _, _, _, _, cc = termios.tcgetattr(self.fd)
        cc = list(cc); cc[termios.VMIN] = 0; cc[termios.VTIME] = 5
        termios.tcsetattr(self.fd, termios.TCSANOW,
                          [0, 0, termios.CS8 | termios.CREAD | termios.CLOCAL,
                           0, 115200, 115200, cc])
        termios.tcflush(self.fd, termios.TCIOFLUSH)
        self.lines = []

    def send(self, c):
        os.write(self.fd, (c + "\r\n").encode())

    def pump(self, secs):
        """Read for `secs`, keeping the bridge drained, and remember lines."""
        out = b""
        end = time.time() + secs
        while time.time() < end:
            if select.select([self.fd], [], [], 0.02)[0]:
                try:
                    d = os.read(self.fd, 4096)
                    if d:
                        out += d
                except OSError:
                    pass
        txt = out.decode("ascii", "replace")
        self.lines += [l for l in txt.splitlines() if l]
        return txt

    def last(self, prefix):
        for l in reversed(self.lines):
            if l.startswith(prefix):
                return l
        return None

    def last_motors(self):
        """Last *complete* T line -> [m1..m6] (ignores a partial trailing line)."""
        for l in reversed(self.lines):
            if not l.startswith("T"):
                continue
            f = l[1:].split(",")
            if len(f) == 7 and all(x.isdigit() for x in f):
                return [int(v) for v in f[:6]]
        return []

    def close(self):
        os.close(self.fd)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/cu.usbmodem1102")
    a = ap.parse_args()
    m = Mixer(HEXA_X, YAW_ALT)
    L = Link(a.port)
    ok = True

    L.pump(0.4)
    print("╔══ 1. KEEPALIVE (interleaved reads) ══╗")
    L.send("A"); L.pump(0.5)
    print("  armed:", L.last("T")[-1] if L.last("T") else "?")
    t0 = time.time(); timeouts = 0
    while time.time() - t0 < 2.5:
        L.send("K")          # keepalive only, no output change
        timeouts += L.pump(0.5).count("TIMEOUT")
    print(f"  5x K over 2.5s (watchdog is 1s) -> TIMEOUTs: {timeouts} "
          f"(expect 0)")
    ok &= (timeouts == 0)

    print("\n╔══ 2. WATCHDOG still fires when silent ══╗")
    to = L.pump(1.6).count("TIMEOUT")
    print(f"  1.6s silence -> TIMEOUTs: {to} (expect 1)")
    ok &= (to == 1)

    print("\n╔══ 3. APPLIED MIX (X) vs reference model ══╗")
    vectors = [(1400, 0, 0, 0), (1400, 100, 0, 0), (1400, 0, 100, 0),
               (1400, 0, 0, 100), (1400, 60, -40, 30), (1600, 120, 80, -60)]
    L.send("A"); L.pump(0.5)
    for thr, r, p, y in vectors:
        exp, lim, tu = m.apply(thr, r, p, y)
        # stream like the Ground Station does: 20 Hz for 2s so the ramp settles
        t0 = time.time()
        while time.time() - t0 < 2.0:
            L.send(f"X{thr},{r},{p},{y}")
            L.pump(0.05)
        tline = L.last_motors()
        got = tline if tline else []
        match = (got == exp)
        ok &= match
        print(f"  {'PASS' if match else 'FAIL'} X{thr},{r},{p},{y} limit={lim}")
        print(f"        expected {exp}")
        if not match:
            print(f"        got      {got}")
    L.send("D"); L.pump(0.6)
    print("\n  final state:", L.last("T")[-1] if L.last("T") else "?", "(0=DISARMED)")

    L.close()
    print("\n╔══ RESULT:", "PASS" if ok else "FAIL", "══╗")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
