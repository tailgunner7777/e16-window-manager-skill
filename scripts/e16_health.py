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
