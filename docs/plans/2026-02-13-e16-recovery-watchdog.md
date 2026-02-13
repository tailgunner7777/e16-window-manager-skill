# E16 Recovery & Watchdog Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add auto-recovery and background watchdog scripts to the e16-window-manager skill, so keyboard/pointer lockups caused by rogue signals or orphaned grab-holding dialogs are detected and fixed automatically.

**Architecture:** A shared detection library (`e16_health.py`) provides all diagnostic/fix primitives. `recover_e16.py` is the one-shot CLI tool. `watchdog_e16.py` is the background daemon using the same primitives in a poll loop. The watchdog launches from `~/.e16/Init` and shuts down from `~/.e16/Exit` via PID file.

**Tech Stack:** Python 3, python-xlib, subprocess (eesh/xdotool), /proc filesystem

**Dependencies:** `python-xlib` (already installed), `eesh`, `xdotool`, `xprop`

---

### Task 1: Create shared health detection library

**Files:**
- Create: `scripts/e16_health.py`

**Step 1: Write `e16_health.py`**

This module contains all diagnostic and fix primitives used by both recovery and watchdog scripts.

```python
#!/usr/bin/env python3
"""
e16_health.py — Shared detection and recovery primitives for Enlightenment e16.

Provides:
- find_e16_pid()       → int or None
- get_process_state()  → str ('S', 'T', 'R', etc.) or None
- resume_if_stopped()  → bool (True if SIGCONT was sent)
- test_eesh()          → bool (True if eesh responds within timeout)
- test_keyboard_grab() → bool (True if keyboard is currently grabbed)
- test_pointer_grab()  → bool (True if pointer is currently grabbed)
- ungrab_keyboard_pointer() → None
- find_grab_holders()  → list of dict with keys: wid, name, wm_class, mapped
- kill_orphan_grab_holders() → list of names killed
- soft_restart_e16()   → bool (True if eesh restart succeeded)
- full_recovery()      → dict with summary of all actions taken
"""

import subprocess
import signal
import os
import re
import datetime


def log(msg, log_file=None):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_msg = f"[{timestamp}] {msg}"
    print(full_msg)
    if log_file:
        try:
            with open(log_file, "a") as f:
                f.write(full_msg + "\n")
        except Exception:
            pass


def _run(cmd, timeout=5):
    try:
        result = subprocess.run(
            cmd, shell=True, text=True, capture_output=True, timeout=timeout
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return None
    except Exception:
        return ""


def find_e16_pid():
    """Find the PID of the running e16 process."""
    out = _run("pgrep -x e16")
    if out:
        # Take first PID if multiple
        return int(out.splitlines()[0].strip())
    return None


def get_process_state(pid):
    """Read process state from /proc. Returns single char: S, T, R, Z, etc."""
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("State:"):
                    # Format: "State:\tT (stopped)"
                    return line.split()[1]
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        pass
    return None


def resume_if_stopped(pid):
    """Send SIGCONT if process is in stopped state. Always safe."""
    state = get_process_state(pid)
    if state == "T":
        os.kill(pid, signal.SIGCONT)
        return True
    return False


def test_eesh(timeout=3):
    """Test if eesh can communicate with e16."""
    result = _run(f"DISPLAY=:0 eesh -e version", timeout=timeout)
    return result is not None and "e16" in result


def _get_xlib_display():
    """Get a python-xlib Display connection."""
    from Xlib import display
    return display.Display(":0")


def test_keyboard_grab():
    """Return True if keyboard is currently grabbed by another client."""
    from Xlib import X
    d = _get_xlib_display()
    root = d.screen().root
    result = root.grab_keyboard(False, X.GrabModeAsync, X.GrabModeAsync, X.CurrentTime)
    d.sync()
    d.ungrab_keyboard(X.CurrentTime)
    d.flush()
    d.sync()
    d.close()
    # 0 = Success (we got it, so it was free), 1 = AlreadyGrabbed
    return result == 1


def test_pointer_grab():
    """Return True if pointer is currently grabbed by another client."""
    from Xlib import X
    d = _get_xlib_display()
    root = d.screen().root
    result = root.grab_pointer(
        False, 0, X.GrabModeAsync, X.GrabModeAsync, X.NONE, X.NONE, X.CurrentTime
    )
    d.sync()
    d.ungrab_pointer(X.CurrentTime)
    d.flush()
    d.sync()
    d.close()
    return result == 1


def ungrab_keyboard_pointer():
    """Force-release keyboard and pointer grabs."""
    from Xlib import X
    d = _get_xlib_display()
    d.ungrab_keyboard(X.CurrentTime)
    d.ungrab_pointer(X.CurrentTime)
    d.flush()
    d.sync()
    d.close()


# Known grab-holding WM_CLASS values (password dialogs, prompts)
GRAB_HOLDER_CLASSES = {"gcr-prompter", "Gcr-prompter", "pinentry", "Pinentry",
                       "ssh-askpass", "Ssh-askpass", "polkit-gnome-authentication-agent-1"}


def find_grab_holders():
    """Find windows from known grab-holding classes. Returns list of dicts."""
    holders = []
    for cls in ["Gcr-prompter", "Pinentry", "Ssh-askpass"]:
        out = _run(f"DISPLAY=:0 xdotool search --class '{cls}'")
        if not out:
            continue
        for wid_str in out.splitlines():
            wid = wid_str.strip()
            if not wid:
                continue
            name = _run(f"DISPLAY=:0 xdotool getwindowname {wid}") or "(unnamed)"
            # Check if window is mapped (visible) via xprop
            map_out = _run(f"DISPLAY=:0 xprop -id {wid} WM_STATE")
            mapped = "Normal" in (map_out or "")
            wm_class = cls
            holders.append({
                "wid": wid, "name": name, "wm_class": wm_class, "mapped": mapped
            })
    return holders


def kill_orphan_grab_holders():
    """Kill grab-holding dialogs that are NOT mapped (orphaned/invisible).
    Returns list of names of killed windows."""
    holders = find_grab_holders()
    killed = []
    for h in holders:
        if not h["mapped"]:
            _run(f"DISPLAY=:0 xdotool windowclose {h['wid']}")
            killed.append(f"{h['name']} ({h['wm_class']})")
    return killed


def kill_all_grab_holders():
    """Kill ALL known grab-holding dialogs regardless of map state.
    Use only during full recovery when input is confirmed locked.
    Returns list of names of killed windows."""
    holders = find_grab_holders()
    killed = []
    for h in holders:
        _run(f"DISPLAY=:0 xdotool windowclose {h['wid']}")
        killed.append(f"{h['name']} ({h['wm_class']})")
    return killed


def soft_restart_e16():
    """Tell e16 to restart in-place (preserves all windows)."""
    _run("DISPLAY=:0 eesh -e restart", timeout=5)
    import time
    time.sleep(3)
    return test_eesh()


def full_recovery(log_file=None):
    """Run the complete recovery sequence. Returns summary dict."""
    summary = {
        "e16_pid": None,
        "was_stopped": False,
        "sigcont_sent": False,
        "keyboard_grabbed": False,
        "pointer_grabbed": False,
        "grabs_released": False,
        "grab_holders_killed": [],
        "eesh_responsive_before": False,
        "eesh_responsive_after": False,
        "soft_restarted": False,
        "recovered": False,
    }

    # Step 1: Find e16
    pid = find_e16_pid()
    if not pid:
        log("FATAL: e16 process not found.", log_file)
        return summary
    summary["e16_pid"] = pid
    log(f"Found e16 PID: {pid}", log_file)

    # Step 2: Check if stopped, send SIGCONT
    state = get_process_state(pid)
    log(f"e16 process state: {state}", log_file)
    if state == "T":
        summary["was_stopped"] = True
        os.kill(pid, signal.SIGCONT)
        summary["sigcont_sent"] = True
        log("e16 was STOPPED — sent SIGCONT.", log_file)
        import time
        time.sleep(1)

    # Step 3: Check eesh
    summary["eesh_responsive_before"] = test_eesh()
    log(f"eesh responsive: {summary['eesh_responsive_before']}", log_file)

    # Step 4: Check grabs
    summary["keyboard_grabbed"] = test_keyboard_grab()
    summary["pointer_grabbed"] = test_pointer_grab()
    log(f"Keyboard grabbed: {summary['keyboard_grabbed']}, Pointer grabbed: {summary['pointer_grabbed']}", log_file)

    # Step 5: If grabs are held, find and kill holders
    if summary["keyboard_grabbed"] or summary["pointer_grabbed"]:
        holders = find_grab_holders()
        log(f"Found {len(holders)} grab-holding dialogs: {[h['name'] for h in holders]}", log_file)

        if not summary["eesh_responsive_before"]:
            # e16 is unresponsive + grabs held = confirmed lockup, kill all holders
            summary["grab_holders_killed"] = kill_all_grab_holders()
            log(f"Killed ALL grab holders (e16 unresponsive): {summary['grab_holders_killed']}", log_file)
        else:
            # e16 responds but grabs held = kill only orphaned/unmapped
            summary["grab_holders_killed"] = kill_orphan_grab_holders()
            log(f"Killed orphaned grab holders: {summary['grab_holders_killed']}", log_file)

        # Force ungrab
        ungrab_keyboard_pointer()
        summary["grabs_released"] = True
        log("Force-released keyboard and pointer grabs.", log_file)

    # Step 6: Test eesh again, soft restart if needed
    import time
    time.sleep(1)
    if not test_eesh():
        log("eesh still unresponsive — attempting soft restart...", log_file)
        summary["soft_restarted"] = True
        soft_restart_e16()

    summary["eesh_responsive_after"] = test_eesh()
    summary["recovered"] = summary["eesh_responsive_after"] and not test_keyboard_grab()
    log(f"Recovery {'SUCCEEDED' if summary['recovered'] else 'FAILED'}.", log_file)
    return summary
```

**Step 2: Verify the module loads**

Run: `DISPLAY=:0 python3 -c "import sys; sys.path.insert(0, 'scripts'); from e16_health import find_e16_pid, test_eesh; print(f'e16 PID: {find_e16_pid()}'); print(f'eesh ok: {test_eesh()}')" `

Expected: Prints the e16 PID and `eesh ok: True`

**Step 3: Commit**

```bash
git add scripts/e16_health.py
git commit -m "feat: add shared e16 health detection library"
```

---

### Task 2: Create one-shot recovery script

**Files:**
- Create: `scripts/recover_e16.py`

**Step 1: Write `recover_e16.py`**

```python
#!/usr/bin/env python3
"""
recover_e16.py — One-shot recovery for a locked-up Enlightenment e16 session.

Diagnoses and fixes:
  - e16 process stopped by rogue signal (SIGTSTP) → sends SIGCONT
  - Keyboard/pointer grabbed by orphaned dialogs (gcr-prompter, pinentry) → kills them
  - Stale X grabs → force-releases via python-xlib
  - Unresponsive e16 IPC → soft-restarts e16 (preserves all windows)

Usage:
    python3 recover_e16.py [--log /path/to/logfile]

Dependencies: python-xlib, eesh, xdotool, xprop
"""

import sys
import os
import argparse

# Allow importing from same directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from e16_health import full_recovery, log


def main():
    parser = argparse.ArgumentParser(description="Recover a locked-up e16 session")
    parser.add_argument("--log", help="Path to log file")
    args = parser.parse_args()

    log("=" * 50, args.log)
    log("e16 Recovery — starting diagnostics", args.log)
    log("=" * 50, args.log)

    summary = full_recovery(log_file=args.log)

    log("", args.log)
    log("--- Recovery Summary ---", args.log)
    log(f"  e16 PID:              {summary['e16_pid']}", args.log)
    log(f"  Was stopped (T):      {summary['was_stopped']}", args.log)
    log(f"  SIGCONT sent:         {summary['sigcont_sent']}", args.log)
    log(f"  Keyboard was grabbed: {summary['keyboard_grabbed']}", args.log)
    log(f"  Pointer was grabbed:  {summary['pointer_grabbed']}", args.log)
    log(f"  Grabs released:       {summary['grabs_released']}", args.log)
    log(f"  Dialogs killed:       {summary['grab_holders_killed']}", args.log)
    log(f"  Soft restarted:       {summary['soft_restarted']}", args.log)
    log(f"  Final status:         {'RECOVERED' if summary['recovered'] else 'FAILED'}", args.log)

    sys.exit(0 if summary["recovered"] else 1)


if __name__ == "__main__":
    main()
```

**Step 2: Test the script runs (on a healthy system it should be a no-op)**

Run: `DISPLAY=:0 python3 scripts/recover_e16.py`

Expected: Shows diagnostics, reports all checks passed, exits with `RECOVERED`.

**Step 3: Commit**

```bash
git add scripts/recover_e16.py
git commit -m "feat: add one-shot e16 recovery script"
```

---

### Task 3: Create watchdog daemon

**Files:**
- Create: `scripts/watchdog_e16.py`

**Step 1: Write `watchdog_e16.py`**

```python
#!/usr/bin/env python3
"""
watchdog_e16.py — Background monitor for Enlightenment e16 health.

Polls every POLL_INTERVAL seconds and auto-recovers from:
  - e16 stopped by rogue signal (SIGTSTP from keyboard) → SIGCONT
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
```

**Step 2: Test the watchdog starts and stops cleanly**

Run: `DISPLAY=:0 python3 scripts/watchdog_e16.py --interval 5 &`
Then: `sleep 3 && python3 scripts/watchdog_e16.py --stop`

Expected: Watchdog starts, logs "Watchdog active", then cleanly shuts down.

**Step 3: Commit**

```bash
git add scripts/watchdog_e16.py
git commit -m "feat: add e16 health watchdog daemon"
```

---

### Task 4: Create Init/Exit integration scripts

**Files:**
- Create: `scripts/install_watchdog.py`

**Step 1: Write `install_watchdog.py`**

```python
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
```

**Step 2: Test the installer (dry-run check)**

Run: `python3 scripts/install_watchdog.py`
Then: `cat ~/.e16/Init && echo "---" && cat ~/.e16/Exit`

Expected: Both files contain the watchdog blocks.

**Step 3: Commit**

```bash
git add scripts/install_watchdog.py
git commit -m "feat: add watchdog installer for e16 Init/Exit hooks"
```

---

### Task 5: Update SKILL.md

**Files:**
- Modify: `SKILL.md`

**Step 1: Update SKILL.md with recovery and watchdog documentation**

Replace the entire SKILL.md with the updated version that includes the new sections:

```markdown
---
name: e16-window-manager
description: Manage and automate Enlightenment e16 window manager layouts, borders, desktops, and health recovery. Includes scripts for capturing/restoring dashboards, auto-recovering from lockups, and a background watchdog.
---

# Enlightenment e16 Window Management

## Overview
This skill provides deterministic tools for managing the Enlightenment e16 window manager. It uses `eesh` for style/desktop management, `xdotool` for window manipulation, and `python-xlib` for X11 grab detection.

## Bundled Scripts

### 1. `capture_e16.py`
Captures the current desktop layout into a portable JSON format.
- **Source of Truth**: Uses Enlightenment Frame coordinates (via `eesh`) for 100% accurate placement.
- **Usage**: `python3 scripts/capture_e16.py [output_file.json]`

### 2. `restore_e16.py`
Launches and repositions applications based on a configuration file.
- **Features**: 120s launch timeout, targeted restoration, and e16 style sync (sticky, shaded, border).
- **Usage**: `python3 scripts/restore_e16.py --config config.json [AppName]`

### 3. `recover_e16.py`
One-shot auto-recovery for a locked-up e16 session.
- **Diagnoses and fixes**: Stopped process (SIGTSTP), grabbed keyboard/pointer, orphaned password dialogs, unresponsive IPC.
- **Usage**: `python3 scripts/recover_e16.py [--log /path/to/logfile]`

### 4. `watchdog_e16.py`
Background daemon that monitors e16 health and auto-recovers.
- **Poll interval**: 10 seconds (configurable via `--interval`).
- **Safe detection**: Only kills orphaned/unmapped grab-holding dialogs. Leaves visible password prompts alone.
- **Usage**: `python3 scripts/watchdog_e16.py [--interval 10] [--log ~/.e16/watchdog.log]`
- **Stop**: `python3 scripts/watchdog_e16.py --stop`

### 5. `install_watchdog.py`
Sets up auto-start of the watchdog via e16 Init/Exit hooks.
- **Usage**: `python3 scripts/install_watchdog.py`

## Core Technical Lessons

### Frame vs. Client Geometry
- **CRITICAL**: Enlightenment requires **Frame** coordinates (which include decorations) for accurate placement. The bundled scripts handle this automatically.

### Hexadecimal Protocol
- Enlightenment's IPC tool (`eesh`) requires window IDs in Hexadecimal format (`0x...`). The bundled scripts automatically convert `xdotool` decimal IDs to hex.

### eesh Command Format
- Use `eesh -e <command>` for single commands (not interactive mode).
- Do NOT wrap the command in quotes: `eesh -e wl` (correct), `eesh -e "wl"` (creates IPC Error windows).

## Troubleshooting: e16 Lockup Recovery

### Root Cause: Keyboard Sends SIGTSTP
Some keyboards (e.g., Protoarc) have function keys that send `SIGTSTP` to the focused process. If e16 receives this signal, it enters **stopped state** (`State: T` in `/proc/<pid>/status`). The entire window manager freezes — no window movement, no keyboard input, no IPC.

### Root Cause: Orphaned Grab-Holding Dialogs
Password dialogs like `gcr-prompter` (GNOME Keyring), `pinentry` (GPG), or `ssh-askpass` perform **modal keyboard grabs** for secure input. If these dialogs crash or become orphaned (unmapped but still holding the grab), all keyboard and pointer input is blocked.

### Detection Logic (used by recovery and watchdog)
1. **e16 stopped?** → Read `/proc/<pid>/status` for `State: T` → Send `SIGCONT` (always safe)
2. **Keyboard/pointer grabbed?** → Test via `python-xlib` grab attempt (0=free, 1=grabbed)
3. **eesh responsive?** → `eesh -e version` with 3s timeout
4. **If grabs held + eesh unresponsive** → Kill ALL grab-holding dialogs, force-ungrab, soft-restart
5. **If grabs held + eesh responsive** → Kill only orphaned (unmapped) dialogs

### Manual Recovery
```bash
# Quick fix:
python3 scripts/recover_e16.py

# Or step-by-step:
kill -CONT $(pgrep -x e16)                           # Resume stopped e16
python3 -c "from Xlib import X, display; d=display.Display(':0'); d.ungrab_keyboard(X.CurrentTime); d.ungrab_pointer(X.CurrentTime); d.flush(); d.sync()"
DISPLAY=:0 eesh -e restart                           # Soft restart e16
```

## Workflows

### Setting up a Dashboard
1. Arrange all tools manually on your desktops.
2. Run `capture_e16.py` to generate the JSON config.
3. Edit the JSON to add the launch `command` for each app (if not automatically detected).
4. Run `restore_e16.py` to verify or automate the startup.

### Setting up the Watchdog
1. Run `python3 scripts/install_watchdog.py` to hook into e16 Init/Exit.
2. Start the watchdog now: `python3 scripts/watchdog_e16.py &`
3. Verify: `cat /tmp/e16-watchdog.pid` and check `~/.e16/watchdog.log`.
```

**Step 2: Commit**

```bash
git add SKILL.md
git commit -m "docs: update SKILL.md with recovery, watchdog, and troubleshooting"
```

---

### Task 6: Update README.md

**Files:**
- Modify: `README.md`

**Step 1: Add recovery and watchdog sections to README.md**

Add the following after the existing "Desktop Integration" section (before the sample config):

```markdown
## Recovery

If your e16 session locks up (windows won't move, keyboard unresponsive), run:
```bash
python3 scripts/recover_e16.py
```

This automatically diagnoses and fixes:
- **Stopped e16 process** (caused by rogue SIGTSTP from some keyboards)
- **Grabbed keyboard/pointer** (orphaned password dialogs holding modal grabs)
- **Unresponsive IPC** (soft-restarts e16 without losing any windows)

## Watchdog (Auto-Recovery)

For automatic detection and recovery, install the background watchdog:

```bash
python3 scripts/install_watchdog.py
```

This adds the watchdog to your e16 Init/Exit hooks. It polls every 10 seconds and auto-recovers from lockups. Legitimate password dialogs are left alone — only orphaned/invisible grab holders are killed.

**Manual control:**
```bash
python3 scripts/watchdog_e16.py &          # Start manually
python3 scripts/watchdog_e16.py --stop     # Stop
tail -f ~/.e16/watchdog.log                # Monitor
```
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add recovery and watchdog sections to README"
```

---

### Task 7: Rebuild the .skill archive

**Files:**
- Rebuild: `e16-window-manager.skill`

**Step 1: Rebuild the zip archive**

```bash
cd /home/necromancer/aiengineer/e16-window-manager-repo
rm -f e16-window-manager.skill
zip -r e16-window-manager.skill SKILL.md scripts/ assets/ references/
```

**Step 2: Verify the archive contents**

Run: `unzip -l e16-window-manager.skill`

Expected: Shows SKILL.md, all 5 scripts, assets/, references/

**Step 3: Copy to parent directory**

```bash
cp e16-window-manager.skill /home/necromancer/aiengineer/e16-window-manager.skill
```

**Step 4: Commit**

```bash
git add e16-window-manager.skill
git commit -m "release: rebuild skill archive with recovery and watchdog"
```
