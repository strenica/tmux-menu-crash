#!/usr/bin/env python3
"""Deterministic reproducer: tmux server SIGSEGV when Kill is chosen from
the choose-tree popup menu (right-click -> x).

Usage: ./repro.py [/path/to/tmux]

Exit status: 1 if the server crashed (bug present), 0 if it survived.
"""
import fcntl
import os
import pty
import select
import struct
import subprocess
import sys
import termios
import time

TMUX = sys.argv[1] if len(sys.argv) > 1 else "tmux"
SOCK = "menu-crash-%d" % os.getpid()


def tmux(*args):
    return subprocess.run([TMUX, "-L", SOCK, *args], capture_output=True, text=True)


def alive():
    return tmux("ls").returncode == 0


def drain(fd, seconds=0.3):
    out = b""
    end = time.time() + seconds
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.05)
        if r:
            try:
                out += os.read(fd, 65536)
            except OSError:
                break
    return out


tmux("kill-server")

pid, fd = pty.fork()
if pid == 0:
    os.environ["TERM"] = "xterm-256color"
    os.execvp(TMUX, [TMUX, "-L", SOCK, "-f", "/dev/null", "new", "-s", "a"])
fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
time.sleep(0.6)
drain(fd, 0.3)

for name in ("b", "c"):
    tmux("new-session", "-d", "-s", name)
tmux("set", "-g", "mouse", "on")
time.sleep(0.3)

# open the session tree
os.write(fd, b"\x02s")
time.sleep(0.7)
drain(fd, 0.6)

# right-click a session (SGR mouse, right button = 2) and choose "Kill" (x)
os.write(fd, b"\x1b[<2;10;5M")
time.sleep(0.6)
drain(fd, 0.5)
os.write(fd, b"x")
time.sleep(1.0)
drain(fd, 0.8)

ok = alive()
print("server alive after menu->Kill:", ok)
if ok:
    tmux("kill-server")
    print("PATCHED / NOT AFFECTED")
    sys.exit(0)
else:
    print("CRASHED (SIGSEGV) - bug present")
    sys.exit(1)
