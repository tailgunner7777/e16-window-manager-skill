---
name: e16-window-manager
description: Manage and automate Enlightenment e16 window manager layouts, borders, desktops, and health recovery. Includes scripts for capturing/restoring dashboards, auto-recovering from lockups, and a background watchdog.
---

# Enlightenment e16 Window Management

## Overview
This skill provides deterministic tools for managing the Enlightenment e16 window manager. It uses `eesh` IPC for style/desktop/geometry management and `xdotool` for window discovery.

## Bundled Scripts

### 1. `capture_e16.py`
Captures the current desktop layout into a portable JSON format.
- **Precision**: Records both Frame and Client dimensions to ensure pixel-perfect restoration regardless of border style.
- **Calculated Height**: Corrects for shaded windows by capturing their unshaded height.
- **Modes**:
    - `python3 scripts/capture_e16.py --dashboard`: ONLY update apps already in `dashboard_config.json` (Prevents pollution).
    - `python3 scripts/capture_e16.py --all`: Discovery mode - capture every managed window.
    - `python3 scripts/capture_e16.py "AppName"`: Targeted mode - capture/update only one specific app.

### 2. `restore_e16.py`
Launches and repositions applications based on a configuration file.
- **Features**: 120s launch timeout, e16 style sync (sticky, shaded, border).
- **Stricter Matching**: Verifies windows by both **Name** and **Class** (`WM_CLASS`) to prevent accidental modification of unrelated windows.
- **Usage**: `python3 scripts/restore_e16.py --config config.json [AppName]`

### 3. `recover_e16.py`
One-shot auto-recovery for a locked-up e16 session.
- **Diagnoses and fixes**: Stopped process (SIGTSTP), grabbed keyboard/pointer, orphaned password dialogs, unresponsive IPC.
- **Usage**: `python3 scripts/recover_e16.py [--log /path/to/logfile]`

### 4. `watchdog_e16.py`
Background daemon that monitors e16 health and auto-recovers.
- **Poll interval**: 10 seconds (configurable via `--interval`).
- **Usage**: `python3 scripts/watchdog_e16.py [--interval 10] [--log ~/.e16/watchdog.log]`

### 5. `install_watchdog.py`
Sets up auto-start of the watchdog via e16 Init/Exit hooks.
- **Usage**: `python3 scripts/install_watchdog.py`

## Core Technical Lessons

### Frame vs. Client Geometry
- **CRITICAL**: Enlightenment's `eesh` command requires **Client** dimensions (the inner application area) for sizing, while coordinates are usually based on the **Frame**. The scripts handle this conversion automatically using captured border offsets.

### Robust Window Identification
- Always capture and verify the `WM_CLASS`. Titles like "Terminal" or "necromancer@hexabit:~" are often duplicated; the window Class is the reliable "DNA" of the application.

### eesh Command Format
- Use `eesh -e <command>` for single commands.
- Do NOT wrap the command in quotes: `eesh -e wl` (correct), `eesh -e "wl"` (incorrect).

## Workflows

### Setting up a Dashboard
1. Arrange your tools manually on your desktops.
2. Run `python3 scripts/capture_e16.py --all` to discover all windows.
3. Curate your `dashboard_config.json` with the apps you want.
4. Future updates: Use `python3 scripts/capture_e16.py --dashboard` to refresh coordinates without adding new clutter.

### Troubleshooting: e16 Lockup Recovery
1. **e16 stopped?** → Read `/proc/<pid>/status` for `State: T` → Send `SIGCONT`.
2. **Keyboard/pointer grabbed?** → Test via `python-xlib` grab attempt.
3. **Recovery**: Run `python3 scripts/recover_e16.py` to fix automatically.
