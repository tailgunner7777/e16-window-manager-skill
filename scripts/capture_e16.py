#!/usr/bin/env python3
"""
capture_e16.py — Captures the current Enlightenment e16 desktop layout.

Usage:
    python3 capture_e16.py --dashboard # ONLY update apps already in dashboard_config.json
    python3 capture_e16.py --all       # Discovery mode: Capture EVERYTHING
    python3 capture_e16.py "AppName"   # Capture only a specific application
"""

import subprocess
import json
import re
import sys
import os

OUTPUT_FILE = "dashboard_config_captured.json"
MASTER_CONFIG = "dashboard_config.json"

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

    # Detect e16-specific states
    border_style = "DEFAULT"
    b_match = re.search(r"Border\s+(\S+)", eesh_out)
    if b_match: border_style = b_match.group(1)
    
    iconified = re.search(r"Iconified\s+[1-9]", eesh_out) is not None
    sticky = re.search(r"Sticky\s+[1-9]", eesh_out) is not None
    shaded = re.search(r"Shaded\s+[1-9]", eesh_out) is not None

    # Frame Geometry: Uses e16 Frame coordinates (includes decorations)
    f_match = re.search(r"Frame window\s+\S+\s+x,y\s*(-?\d+),\s*(-?\d+)\s+wxh\s*(\d+)x\s*(\d+)", eesh_out)
    if not f_match: return None
    
    f_x, f_y = int(f_match.group(1)), int(f_match.group(2))
    f_width, f_height = int(f_match.group(3)), int(f_match.group(4))

    # Client Geometry
    c_match = re.search(r"Client window\s+\S+\s+x,y\s*(-?\d+),\s*(-?\d+)\s+wxh\s*(\d+)x\s*(\d+)", eesh_out)
    if not c_match: return None
    c_width, c_height = int(c_match.group(3)), int(c_match.group(4))

    # Border sizes (Left, Right, Top, Bottom)
    l, r, t, b = 0, 0, 0, 0
    lrtb_match = re.search(r"Border\s+\S+\s+lrtb\s+(\d+),(\d+),(\d+),(\d+)", eesh_out)
    if lrtb_match:
        l, r, t, b = int(lrtb_match.group(1)), int(lrtb_match.group(2)), int(lrtb_match.group(3)), int(lrtb_match.group(4))

    # Calculate unshaded frame size
    true_f_width = c_width + l + r
    true_f_height = c_height + t + b

    # Attempt to find the launch command via the process ID
    pid_out = run_command(f"xprop -id {wid} _NET_WM_PID")
    cmd = ""
    pid_match = re.search(r"=\s*(\d+)", pid_out)
    if pid_match:
        pid = pid_match.group(1)
        cmd = run_command(f"ps -p {pid} -o args=")

    # Skip system windows like the desktop itself
    if name in ["Desktop", "e16"] or true_f_width < 10: return None

    return {
        "name": name,
        "search_term": name, 
        "command": cmd, 
        "class": app_class,
        "desktop": desktop,
        "x": f_x, "y": f_y, 
        "width": true_f_width, "height": true_f_height,
        "client_w": c_width, "client_h": c_height,
        "border": border_style,
        "border_l": l, "border_r": r, "border_t": t, "border_b": b,
        "iconified": iconified, "sticky": sticky, "shaded": shaded
    }

def main():
    # Handle Arguments
    args = sys.argv[1:]
    
    if not args:
        print(__doc__)
        return

    mode = "specific"
    filter_target = args[0]

    if "--all" in args:
        mode = "all"
    elif "--dashboard" in args:
        mode = "dashboard"

    # Load filters if in dashboard mode
    dashboard_names = set()
    dashboard_classes = set()
    if mode == "dashboard":
        if os.path.exists(MASTER_CONFIG):
            with open(MASTER_CONFIG, 'r') as f:
                cfg = json.load(f)
                for app in cfg:
                    if app.get("name"): dashboard_names.add(app["name"].lower())
                    if app.get("class"): dashboard_classes.add(app["class"].lower())
        else:
            print(f"Error: {MASTER_CONFIG} not found. Cannot run in --dashboard mode.")
            return

    print(f"Capturing window state (Mode: {mode})...")
    wids = get_window_ids()
    apps = []
    
    for wid in wids:
        info = get_window_info(wid)
        if not info: continue

        should_capture = False
        if mode == "all":
            should_capture = True
        elif mode == "specific":
            if filter_target.lower() in info["name"].lower() or filter_target.lower() in info["class"].lower():
                should_capture = True
        elif mode == "dashboard":
            if info["name"].lower() in dashboard_names or info["class"].lower() in dashboard_classes:
                should_capture = True

        if should_capture:
            print(f"Captured: {info['name']} ({info['class']})")
            apps.append(info)
            
    with open(OUTPUT_FILE, "w") as f:
        json.dump(apps, f, indent=4)
        
    print(f"\nSaved {len(apps)} entries to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
