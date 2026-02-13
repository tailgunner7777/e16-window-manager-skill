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
