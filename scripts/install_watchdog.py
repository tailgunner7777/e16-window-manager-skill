#!/usr/bin/env python3
"""
install_watchdog.py — Set up e16 Init/Exit hooks for the watchdog.

Adds watchdog launch to ~/.e16/Init and cleanup to ~/.e16/Exit.
Safe to run multiple times (idempotent).
"""

import os
import stat

E16_DIR = os.path.expanduser("~/.e16")
INIT_FILE = os.path.join(E16_DIR, "Init")
EXIT_FILE = os.path.join(E16_DIR, "Exit")
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
WATCHDOG_PATH = os.path.join(SCRIPTS_DIR, "watchdog_e16.py")

INIT_MARKER = "# >>> e16-watchdog >>>"
INIT_BLOCK = f"""{INIT_MARKER}
python3 {WATCHDOG_PATH} &
# <<< e16-watchdog <<<"""

EXIT_MARKER = "# >>> e16-watchdog >>>"
EXIT_BLOCK = f"""{EXIT_MARKER}
python3 {WATCHDOG_PATH} --stop
# <<< e16-watchdog <<<"""


def ensure_file(path):
    """Create file with shebang if it doesn't exist."""
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write("#!/bin/sh\n")
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
        print(f"Created {path}")


def add_block(path, marker, block):
    """Add a block to a file if the marker isn't already present."""
    with open(path, "r") as f:
        content = f.read()
    if marker in content:
        print(f"Already installed in {path}")
        return False
    with open(path, "a") as f:
        f.write("\n" + block + "\n")
    print(f"Installed watchdog hook in {path}")
    return True


def main():
    ensure_file(INIT_FILE)
    ensure_file(EXIT_FILE)
    add_block(INIT_FILE, INIT_MARKER, INIT_BLOCK)
    add_block(EXIT_FILE, EXIT_MARKER, EXIT_BLOCK)
    print(f"\nDone. Watchdog will auto-start with e16.")
    print(f"To start now: python3 {WATCHDOG_PATH} &")
    print(f"To stop:      python3 {WATCHDOG_PATH} --stop")


if __name__ == "__main__":
    main()
