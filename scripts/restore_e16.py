#!/usr/bin/env python3
"""
restore_e16.py — Restores an Enlightenment e16 desktop layout from a config.

This script reads a JSON configuration file, launches any missing applications,
and then uses xdotool and Enlightenment's eesh to position windows and 
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

def run_cmd(cmd):
    """Executes a shell command and returns the stripped stdout."""
    return subprocess.run(cmd, shell=True, text=True, capture_output=True).stdout.strip()

def find_window(search_term):
    """Finds a window ID by name or class using xdotool."""
    # Try searching by name first
    wid = run_cmd(f"xdotool search --name '{search_term}' | head -n 1")
    # Fallback to searching by class
    if not wid:
        wid = run_cmd(f"xdotool search --class '{search_term}' | head -n 1")
    return wid

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
        cmd = app.get("command")
        
        # Filter if specific apps were requested via command line
        if args.apps and not any(a.lower() in name.lower() or a.lower() in search.lower() for a in args.apps):
            continue

        # Check if the window is already open
        wid = find_window(search)
        
        # Launch the application if it's missing and a command is provided
        if not wid and cmd:
            log(f"Launching {name}...", args.log)
            subprocess.Popen(cmd, shell=True)
            # Wait up to 120 seconds for the window to appear
            for _ in range(240): 
                time.sleep(0.5)
                wid = find_window(search)
                if wid: break
        
        if wid:
            # Convert decimal ID to hex for eesh compatibility
            hex_wid = hex(int(wid))
            
            # Ensure the window is active and mapped
            run_cmd(f"xdotool windowactivate {wid}")
            
            # Restore Virtual Desktop assignment
            desk = app.get("desktop")
            if desk is not None and desk != -1:
                run_cmd(f"xdotool set_desktop_for_window {wid} {desk}")

            # Restore Geometry (x, y, width, height)
            run_cmd(f"xdotool windowmove {wid} {app['x']} {app['y']}")
            run_cmd(f"xdotool windowsize {wid} {app['width']} {app['height']}")
            run_cmd(f"xdotool windowmap {wid}")

            # Sync e16-specific states using eesh
            run_cmd(f"eesh win_op {hex_wid} border {app.get('border', 'DEFAULT')}")
            run_cmd(f"eesh win_op {hex_wid} stick {'on' if app.get('sticky') else 'off'}")
            run_cmd(f"eesh win_op {hex_wid} shade {'on' if app.get('shaded') else 'off'}")
            if app.get("iconified"):
                run_cmd(f"eesh win_op {hex_wid} iconify on")
            
            log(f"  [✓] {name} positioned.", args.log)
        else:
            log(f"  [!] {name} failed.", args.log)

if __name__ == "__main__":
    main()
