#!/usr/bin/env python3
"""Bench test for MultiMotor + PMU: drives the firmware over serial and checks
the mixer against tools/mixer_ref.py. Uses only dry-run (Y) mixer commands, so
no motor output is ever changed."""
import os, sys, time, subprocess, termios, select

DEV = "/dev/cu.usbmodem1102"
CLI = "/opt/ST/STM32CubeCLT_1.22.0/STM32CubeProgrammer/bin/STM32_Programmer_CLI"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))


def open_port(dev=DEV):
    fd = os.open(dev, os.O_RDWR | os.O_NONBLOCK | os.O_NOCTTY)
    _, _, _, _, _, _, cc = termios.tcgetattr(fd)
    cc = list(cc)
    cc[termios.VMIN] = 0
    cc[termios.VTIME] = 5
    termios.tcsetattr(fd, termios.TCSANOW,
                      [0, 0, termios.CS8 | termios.CREAD | termios.CLOCAL, 0,
                       115200, 115200, cc])
    termios.tcflush(fd, termios.TCIOFLUSH)
    return fd


def drain(fd, secs, collect=True):
    buf = b""
    end = time.time() + secs
    while time.time() < end:
        if select.select([fd], [], [], 0.1)[0]:
            try:
                d = os.read(fd, 4096)
                if d:
                    buf += d
            except OSError:
                pass
    return buf.decode("ascii", "replace")


def cmd(fd, c, wait=0.6):
    os.write(fd, (c + "\r\n").encode())
    return drain(fd, wait)


def main():
    fd = open_port()
    drain(fd, 0.5)

    if "--noreset" not in sys.argv:
        subprocess.run([CLI, "-c", "port=SWD", "mode=UR", "-rst"],
                       capture_output=True)
        boot = drain(fd, 3.0)
        print("═══ BOOT MESSAGES ═══")
        print(boot.strip())
    else:
        boot = ""

    print("\n═══ MIXER GEOMETRY (Q) ═══")
    print(cmd(fd, "Q").strip())

    print("\n═══ MIXER GAINS (W) ═══")
    print(cmd(fd, "W", 0.8).strip())

    print("\n═══ DRY-RUN MIXER VECTORS (Y) — compared with mixer_ref.py ═══")
    from mixer_ref import Mixer, HEXA_X, YAW_ALT
    m = Mixer(HEXA_X, YAW_ALT)
    vectors = [(1500, 0, 0, 0), (1500, 100, 0, 0), (1500, 0, 100, 0),
               (1500, 0, 0, 100), (1500, 50, -50, 25), (1950, 100, 100, 0),
               (1100, 100, 100, 100), (1500, 600, 600, 600)]
    ok = True
    for thr, r, p, y in vectors:
        exp, lim, tu = m.apply(thr, r, p, y)
        exp_line = "Y," + ",".join(str(v) for v in exp) + f",{lim},{tu}"
        got = cmd(fd, f"Y{thr},{r},{p},{y}", 0.5)
        got_line = next((l for l in got.splitlines() if l.startswith("Y,")), got.strip())
        match = (got_line.strip() == exp_line)
        ok &= match
        print(f"  {'PASS' if match else 'FAIL'}  Y{thr},{r},{p},{y}")
        print(f"        expected {exp_line}")
        if not match:
            print(f"        got      {got_line.strip()}")

    print("\n═══ PMU / BATTERY (B) ═══")
    for _ in range(3):
        print("  " + cmd(fd, "B", 0.5).strip().replace("\r", ""))
        time.sleep(0.3)

    print("\n═══ PMU auto-report at 5 Hz (3 s listen) ═══")
    stream = drain(fd, 3.0)
    blines = [l for l in stream.splitlines() if l.startswith("B,")]
    tlines = [l for l in stream.splitlines() if l.startswith("T")]
    print(f"  B lines: {len(blines)} (expect ~15),  T lines: {len(tlines)} (expect ~30)")
    for l in blines[:4]:
        print("   ", l)

    print("\n═══ ERROR PATHS (safety) ═══")
    print("  X while disarmed ->", cmd(fd, "X1500,100,0,0", 0.5).strip())
    print("  M bad motor      ->", cmd(fd, "M9,45,1", 0.5).strip())
    print("  M bad dir        ->", cmd(fd, "M1,45,0", 0.5).strip())
    print("  M valid          ->", cmd(fd, "M1,30,1", 0.5).strip())

    os.close(fd)
    print("\n═══ RESULT:", "ALL MIXER VECTORS PASS" if ok else "MISMATCH — see FAIL lines", "═══")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
