"""Autostart installer for Linux desktop environments (UKUI/GNOME/KDE)."""

import os
import shutil
import sys
from pathlib import Path
from typing import Optional

AUTOSTART_DIR = Path.home() / ".config" / "autostart"
DESKTOP_FILE = AUTOSTART_DIR / "kylin-taskbar-monitor.desktop"

def get_exec_command() -> str:
    """Resolve the optimal executable command for autostart."""
    # Check if kylin-monitor is in PATH
    bin_path = shutil.which("kylin-monitor")
    if bin_path:
        return bin_path
    
    # Check ~/.local/bin/kylin-monitor
    local_bin = Path.home() / ".local" / "bin" / "kylin-monitor"
    if local_bin.exists():
        return str(local_bin)

    # Fallback to current python module entrypoint
    return f"{sys.executable} -m kylin_taskbar_monitor.cli"

def install_autostart(desktop_path: Optional[Path] = None, exec_cmd: Optional[str] = None) -> Path:
    target_path = desktop_path or DESKTOP_FILE
    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    cmd = exec_cmd or get_exec_command()
    
    content = f"""[Desktop Entry]
Type=Application
Exec={cmd}
Hidden=false
NoDisplay=false
Terminal=false
StartupNotify=false
X-GNOME-Autostart-enabled=true
Name=Kylin Taskbar Monitor
Comment=Ultra-lightweight taskbar performance monitor for Kylin OS
Icon=utilities-system-monitor
Categories=System;Monitor;
"""
    with open(target_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ 已成功安装开机自启项至: {target_path}")
    return target_path

def uninstall_autostart(desktop_path: Optional[Path] = None) -> bool:
    target_path = desktop_path or DESKTOP_FILE
    if target_path.exists():
        target_path.unlink()
        print(f"🗑️ 已成功移除开机自启项: {target_path}")
        return True
    else:
        print("ℹ️ 未发现已安装的开机自启文件。")
        return False

def status_autostart(desktop_path: Optional[Path] = None) -> bool:
    target_path = desktop_path or DESKTOP_FILE
    return target_path.exists()
