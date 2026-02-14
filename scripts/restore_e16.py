#!/usr/bin/env python3
"""
restore_e16.py — Restores an Enlightenment e16 desktop layout from a config.

This script reads a JSON configuration file, launches any missing applications,
and then uses Enlightenment's eesh IPC to position windows and 
restore their states (desktop, border, sticky, shaded, etc.).
"""

import json
import subprocess
import time
import shutil
import sys
import os
import datetime

def log(msg, log_file=None):
    """Helper for logging progress to stdout and optionally a file."""
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    full_msg = f"[{timestamp}] {msg}"
    print(full_msg)
    if log_file:
        try:
            with open(log_file, "a") as f:
                f.write(full_msg + "\n")
        except Exception:
            pass

def run_eesh(cmd):
    """Executes an eesh command via IPC."""
    full_cmd = f"eesh -e {cmd}"
    return subprocess.run(full_cmd, shell=True, text=True, capture_output=True).stdout.strip()

def run_xdotool(cmd):
    """Executes an xdotool command."""
    full_cmd = f"xdotool {cmd}"
    return subprocess.run(full_cmd, shell=True, text=True, capture_output=True).stdout.strip()

def get_window_class(wid):
    """Returns the WM_CLASS for a window ID."""
    out = subprocess.run(f"xprop -id {wid} WM_CLASS", shell=True, text=True, capture_output=True).stdout.strip()
    # Format: WM_CLASS(STRING) = "name", "class"
    if "=" in out:
        return out.split("=")[1].strip().replace('"', '')
    return ""

def find_window(search_term, app_class=None):
    """Finds a window ID by name and class using xdotool and xprop."""
    # 1. Search by name first (fastest)
    wids = run_xdotool(f"search --name '{search_term}'").splitlines()
    
    # 2. Verify class if provided
    if app_class:
        for wid in wids:
            actual_class = get_window_class(wid)
            if app_class.lower() in actual_class.lower():
                return wid
        
        # If no name match with class, try searching by class directly
        c_wids = run_xdotool(f"search --class '{app_class}'").splitlines()
        for wid in c_wids:
            actual_class = get_window_class(wid)
            # Stricter check for class
            if app_class.lower() in actual_class.lower():
                # If search_term is provided, verify it too
                if search_term:
                    name = run_xdotool(f"getwindowname {wid}")
                    if search_term.lower() in name.lower():
                        return wid
                else:
                    return wid
    else:
        # No class provided, return first name match
        if wids:
            return wids[0]
            
    return None

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Restore e16 dashboard")
    parser.add_argument("--config", default="dashboard_config.json", help="Path to config JSON")
    parser.add_argument("--log", help="Path to log file")
    parser.add_argument("apps", nargs="*", help="Specific apps to restore (optional)")
    args = parser.parse_args()

    if not os.path.exists(args.config):
        print(f"Error: Config {args.config} not found.")
        return

    with open(args.config, 'r') as f:
        config = json.load(f)

    log(f"Restoring {len(args.apps) if args.apps else 'all'} apps...", args.log)

    for app in config:
        name = app.get("name", "Unknown")
        search = app.get("search_term", name)
        app_class = app.get("class", "")
        cmd = app.get("command")
        
        # Filter if specific apps were requested via command line
        if args.apps:
            match = False
            for a in args.apps:
                a_low = a.lower()
                if (a_low in name.lower() or 
                    a_low in search.lower() or 
                    a_low in app_class.lower()):
                    match = True
                    break
            if not match:
                continue

        # Check if the window is already open
        wid = find_window(search, app_class)
        
        # Launch the application if it's missing and a command is provided
        if not wid and cmd:
            log(f"Launching {name}...", args.log)
            # Use setsid to detach the process
            subprocess.Popen(f"setsid {cmd} > /dev/null 2>&1", shell=True)
            # Wait up to 60 seconds (reduced timeout for performance)
            for _ in range(120): 
                time.sleep(0.5)
                wid = find_window(search, app_class)
                if wid: break
        
        if wid:
            hex_wid = hex(int(wid))
            
            # CRITICAL: Verify this is EXACTLY the window we want one last time
            # by checking class before doing ANY eesh operations
            actual_class = get_window_class(wid)
            if app_class and app_class.lower() not in actual_class.lower():
                log(f"  [!] Skipping {name} - class mismatch: expected {app_class}, found {actual_class}", args.log)
                continue

            # 1. Bring window to front and ensure it's unshaded for state changes
            run_xdotool(f"windowactivate {wid}")
            run_eesh(f"win_op {hex_wid} shade off")
            
            # 2. Set Border Style
            border = app.get("border", "DEFAULT")
            run_eesh(f"win_op {hex_wid} border {border}")
            
            # 3. Restore Virtual Desktop
            desk = app.get("desktop")
            if desk is not None and desk != -1:
                run_eesh(f"win_op {hex_wid} desk {desk}")

            # 4. Restore Geometry (x, y, width, height)
            client_w = app.get("client_w")
            client_h = app.get("client_h")
            
            if client_w is None or client_h is None:
                l = app.get("border_l", 0)
                r = app.get("border_r", 0)
                t = app.get("border_t", 0)
                b = app.get("border_b", 0)
                client_w = app['width'] - (l + r)
                client_h = app['height'] - (t + b)
            
            # Set size (client-based)
            run_eesh(f"win_op {hex_wid} size {client_w} {client_h}")
            # Set position (frame-based)
            run_eesh(f"win_op {hex_wid} move {app['x']} {app['y']}")
            
            # Ensure window is mapped
            run_xdotool(f"windowmap {wid}")

            # 5. Restore States
            run_eesh(f"win_op {hex_wid} stick {'on' if app.get('sticky') else 'off'}")
            
            if app.get("shaded"):
                run_eesh(f"win_op {hex_wid} shade on")
                
            if app.get("iconified"):
                run_eesh(f"win_op {hex_wid} iconify on")
            
            log(f"  [✓] {name} restored.", args.log)
        else:
            log(f"  [!] {name} failed.", args.log)

if __name__ == "__main__":
    main()
