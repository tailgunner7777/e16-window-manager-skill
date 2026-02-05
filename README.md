# e16-window-manager Skill for Gemini CLI

An advanced automation skill for the **Enlightenment e16** window manager. This skill allows you to capture, restore, and precisely manage complex window layouts ("Workstation Dashboards") using Python automation and e16's IPC interface.

## 🚀 Features

- **Frame-Accurate Positioning**: Uses Enlightenment's `eesh` Frame geometry to ensure windows include borders and title bars (no more offsets).
- **Enlightenment Style Sync**: Automatically restores Border styles, Sticky states, Shaded (rolled-up) states, and Iconified (minimized) states.
- **Deterministic Automation**: Includes bundled Python scripts for 100% reliable execution.
- **Targeted Restoration**: Restore your entire workspace at boot, or just a single application (e.g., `./restore_e16.py MyApp`).
- **High-Timeout Support**: Designed to handle heavy browser applications with a 120-second launch window.

## 📦 Contents

- `SKILL.md`: The procedural knowledge for the AI agent.
- `scripts/capture_e16.py`: Snapshot utility for recording your layout.
- `scripts/restore_e16.py`: Engine for launching and snapping apps.
- `e16-window-manager.skill`: The pre-packaged skill file for easy import.

## 🛠 Installation

1. **Download** the `.skill` file from this repository.
2. **Install** it into your Gemini CLI workspace:
   ```bash
   gemini skills install e16-window-manager.skill --scope workspace
   ```
3. **Reload** your session:
   ```bash
   /skills reload
   ```

## 📖 How to Use

### 1. Capture your Layout
Arrange your windows exactly how you want them on your Enlightenment desktops, then run:
```bash
python3 scripts/capture_e16.py my_layout.json
```

### 2. Restore your Layout
To launch missing apps and snap everything back to the grid:
```bash
python3 scripts/restore_e16.py --config my_layout.json
```

### 3. Desktop Integration
Add the restore command to your `~/.e16/Start` script to have your workbench ready the moment you log in.

## Requirements
- Python 3.x
- `xdotool`
- `eesh` (Standard with Enlightenment e16)
- Gemini CLI

---
*Created with Tailguner and an AI Engineer.*
