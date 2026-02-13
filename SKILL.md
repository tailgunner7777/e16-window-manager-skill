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
