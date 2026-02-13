#!/usr/bin/env python3
"""
watchdog_e16.py — Background monitor for Enlightenment e16 health.

Polls every POLL_INTERVAL seconds and auto-recovers from:
  - e16 stopped by rogue signal (SIGTSTP) → SIGCONT
  - Keyboard/pointer grabbed by orphaned dialogs → kills unmapped holders
  - Unresponsive eesh IPC → soft restart

Launched from ~/.e16/Init, stopped from ~/.e16/Exit via PID file.

Usage:
    python3 watchdog_e16.py [--interval 10] [--log ~/.e16/watchdog.log]
    python3 watchdog_e16.py --stop

PID file: /tmp/e16-watchdog.pid
"""

import sys
import os
import time
import signal
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from e16_health import (
    log, find_e16_pid, get_process_state, resume_if_stopped,
    test_eesh, test_keyboard_grab, test_pointer_grab,
    ungrab_keyboard_pointer, kill_orphan_grab_holders,
    kill_all_grab_holders, soft_restart_e16,
)

PID_FILE = "/tmp/e16-watchdog.pid"
SHUTDOWN = False


def handle_signal(signum, frame):
    global SHUTDOWN
    SHUTDOWN = True


def write_pid():
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def remove_pid():
    try:
        os.remove(PID_FILE)
    except FileNotFoundError:
        pass


def stop_existing():
    """Stop a running watchdog instance via PID file."""
    try:
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
        os.kill(pid, signal.SIGTERM)
        print(f"Sent SIGTERM to watchdog PID {pid}")
        return True
    except (FileNotFoundError, ValueError):
        print("No running watchdog found (no PID file).")
        return False
    except ProcessLookupError:
        print("Stale PID file — process already dead. Cleaning up.")
        remove_pid()
        return False


def poll_once(log_file=None):
    """Single poll iteration. Returns True if a recovery action was taken."""
    acted = False

    pid = find_e16_pid()
    if not pid:
        return False

    # Check 1: Is e16 stopped?
    state = get_process_state(pid)
    if state == "T":
        resume_if_stopped(pid)
        log(f"WATCHDOG: e16 was stopped (State: T) — sent SIGCONT", log_file)
        acted = True
        time.sleep(1)

    # Check 2: Are keyboard/pointer grabbed?
    kb_grabbed = test_keyboard_grab()
    ptr_grabbed = test_pointer_grab()

    if not kb_grabbed and not ptr_grabbed:
        return acted

    # Grabs are held — check if e16 is responsive
    eesh_ok = test_eesh(timeout=3)

    if not eesh_ok:
        # Full lockup: e16 unresponsive + grabs held
        killed = kill_all_grab_holders()
        ungrab_keyboard_pointer()
        log(f"WATCHDOG: Full lockup detected. Killed grab holders: {killed}. Released grabs.", log_file)
        time.sleep(1)
        if not test_eesh(timeout=3):
            soft_restart_e16()
            log("WATCHDOG: Soft-restarted e16.", log_file)
        acted = True
    else:
        # e16 is fine but something is grabbing — kill only orphaned dialogs
        killed = kill_orphan_grab_holders()
        if killed:
            ungrab_keyboard_pointer()
            log(f"WATCHDOG: Killed orphaned grab holders: {killed}. Released grabs.", log_file)
            acted = True
        # If all grab holders are mapped (visible/legitimate), leave them alone

    return acted


def main():
    parser = argparse.ArgumentParser(description="e16 health watchdog daemon")
    parser.add_argument("--interval", type=int, default=10, help="Poll interval in seconds (default: 10)")
    parser.add_argument("--log", default=os.path.expanduser("~/.e16/watchdog.log"), help="Log file path")
    parser.add_argument("--stop", action="store_true", help="Stop a running watchdog")
    args = parser.parse_args()

    if args.stop:
        stop_existing()
        return

    # Check for existing instance
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE) as f:
                old_pid = int(f.read().strip())
            os.kill(old_pid, 0)  # Check if alive
            print(f"Watchdog already running (PID {old_pid}). Use --stop to stop it.")
            return
        except (ProcessLookupError, ValueError):
            remove_pid()  # Stale PID file

    # Wait for e16 to be ready
    log("Watchdog starting — waiting for e16...", args.log)
    for _ in range(60):
        if find_e16_pid() and test_eesh(timeout=2):
            break
        time.sleep(2)
    else:
        log("FATAL: e16 not found after 120s. Exiting.", args.log)
        return

    # Register signal handlers and write PID
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    write_pid()

    log(f"Watchdog active (PID {os.getpid()}, interval {args.interval}s).", args.log)

    try:
        while not SHUTDOWN:
            try:
                poll_once(log_file=args.log)
            except Exception as e:
                log(f"WATCHDOG ERROR: {e}", args.log)
            time.sleep(args.interval)
    finally:
        remove_pid()
        log("Watchdog stopped.", args.log)


if __name__ == "__main__":
    main()
