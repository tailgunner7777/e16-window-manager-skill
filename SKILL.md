---
name: e16-window-manager
description: Manage and automate Enlightenment e16 window manager layouts, borders, and desktops. Includes portable Python scripts for capturing and restoring precisely positioned "Workstation Dashboards".
---

# Enlightenment e16 Window Management

## Overview
This skill provides deterministic tools for managing the Enlightenment e16 window manager. It uses `eesh` for style/desktop management and `xdotool` for window manipulation.

## Bundled Scripts
The following scripts are included in the skill and should be used to automate workflows:

### 1. `capture_e16.py`
Captures the current desktop layout into a portable JSON format.
- **Source of Truth**: Uses Enlightenment Frame coordinates (via `eesh`) for 100% accurate placement.
- **Usage**: `python3 scripts/capture_e16.py [output_file.json]`

### 2. `restore_e16.py`
Launches and repositions applications based on a configuration file.
- **Features**: 120s launch timeout, targeted restoration, and e16 style sync (sticky, shaded, border).
- **Usage**: `python3 scripts/restore_e16.py --config config.json [AppName]`

## Core Technical Lessons

### Frame vs. Client Geometry
- **CRITICAL**: Enlightenment requires **Frame** coordinates (which include decorations) for accurate placement. The bundled scripts handle this automatically.

### Hexadecimal Protocol
- Enlightenment's IPC tool (`eesh`) requires window IDs in Hexadecimal format (`0x...`). The bundled scripts automatically convert `xdotool` decimal IDs to hex.

## Workflows

### Setting up a Dashboard
1. Arrange all tools manually on your desktops.
2. Run `capture_e16.py` to generate the JSON config.
3. Edit the JSON to add the launch `command` for each app (if not automatically detected).
4. Run `restore_e16.py` to verify or automate the startup.
