#!/usr/bin/env python3
"""
capture_e16.py — Captures the current Enlightenment e16 desktop layout.

This script queries the X server and Enlightenment e16 (via eesh) to gather
information about all open windows, including their positions, sizes,
desktop assignments, and special e16 states (border, sticky, shaded, etc.).
The results are saved to a JSON configuration file for later restoration.
"""

import subprocess
import json
import re
import sys
import os

def run_command(cmd):
    """Executes a shell command and returns the stripped stdout."""
    try:
        result = subprocess.run(cmd, shell=True, text=True, capture_output=True)
        return result.stdout.strip()
    except Exception:
        return ""

def get_window_ids():
    """Retrieves a list of all client window IDs from the root window."""
    output = run_command("xprop -root _NET_CLIENT_LIST")
    if not output: return []
    # Extract hex window IDs from the xprop output
    match = re.search(r"window id # (.*)", output)
    if match:
        ids = match.group(1).split(",")
        return [x.strip() for x in ids]
    return []

def get_window_info(wid):
    """Gathers detailed information for a specific window ID."""
    # Get the window name (title)
    name = run_command(f"xdotool getwindowname {wid}")
    if not name: return None
    
    # Extract WM_CLASS to identify the application
    wm_class = run_command(f"xprop -id {wid} WM_CLASS")
    app_class = wm_class.split('"')[-2] if '"' in wm_class else ""

    # Determine which virtual desktop the window is on
    desktop = run_command(f"xdotool get_desktop_for_window {wid}")
    try: desktop = int(desktop)
    except: desktop = 0

    # Query Enlightenment e16 for detailed frame and state information
    eesh_out = run_command(f"eesh win_info {wid}")
    if not eesh_out: return None

    # Frame Geometry: Uses e16 Frame coordinates (includes decorations) for 100% accuracy
    f_match = re.search(r"Frame window\s+\S+\s+x,y\s+(-?\d+),\s+(-?\d+)\s+wxh\s+(\d+)x\s*(\d+)", eesh_out)
    if not f_match: return None
    
    x, y = int(f_match.group(1)), int(f_match.group(2))
    width, height = int(f_match.group(3)), int(f_match.group(4))

    # Detect e16-specific states
    border_style = "DEFAULT"
    b_match = re.search(r"Border\s+(\S+)", eesh_out)
    if b_match: border_style = b_match.group(1)
    
    iconified = "Iconified    1" in eesh_out
    sticky = "Sticky       1" in eesh_out
    shaded = "Shaded       1" in eesh_out

    # Attempt to find the launch command via the process ID
    pid_out = run_command(f"xprop -id {wid} _NET_WM_PID")
    cmd = ""
    pid_match = re.search(r"=\s*(\d+)", pid_out)
    if pid_match:
        pid = pid_match.group(1)
        cmd = run_command(f"ps -p {pid} -o args=")

    # Skip system windows like the desktop itself
    if name in ["Desktop", "e16"] or width < 10: return None

    return {
        "name": name,
        "search_term": name, 
        "command": cmd, 
        "class": app_class,
        "desktop": desktop,
        "x": x, "y": y, "width": width, "height": height,
        "border": border_style, "iconified": iconified, "sticky": sticky, "shaded": shaded
    }

def main():
    # Allow specifying an output file via command line argument
    output_file = sys.argv[1] if len(sys.argv) > 1 else "dashboard_config_captured.json"
    print(f"Capturing e16 layout to {output_file}...")
    
    wids = get_window_ids()
    apps = []
    for wid in wids:
        info = get_window_info(wid)
        if info: apps.append(info)
            
    # Save the captured layout to a JSON file
    with open(output_file, "w") as f:
        json.dump(apps, f, indent=4)
    print(f"Success: Captured {len(apps)} windows.")

if __name__ == "__main__":
    main()
