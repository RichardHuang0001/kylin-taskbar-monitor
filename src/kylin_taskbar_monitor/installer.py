"""Linux 桌面开机自启动管理模块 (Autostart Installer).

遵循 FreeDesktop.org (XDG) Autostart 桌面自启动标准规范。
支持银河麒麟 (UKUI)、统信 (DDE)、GNOME、KDE 等 Linux 桌面环境。
通过在用户目录 `~/.config/autostart/` 生成或删除 `.desktop` 文件，
实现免 root 权限的用户级应用开机自动静默随桌面会话启动。
"""

import os
import shutil
import sys
from pathlib import Path
from typing import Optional

# XDG 规范的用户级自启动桌面文件目录
AUTOSTART_DIR = Path.home() / ".config" / "autostart"

# 默认生成的自启动桌面条目文件路径
DESKTOP_FILE = AUTOSTART_DIR / "kylin-taskbar-monitor.desktop"

def get_exec_command() -> str:
    """动态探测并解析最适宜的自启动执行命令.
    
    解析优先级：
    1. 环境变量 PATH 中已安装的全局二进制可执行命令 `kylin-monitor`；
    2. 用户本地主目录 `~/.local/bin/kylin-monitor`（pip install --user 常见安装路径）；
    3. 当前正在运行的 Python 解释器模块执行命令（兜底策略）：`{sys.executable} -m kylin_taskbar_monitor.cli`。
    
    Returns:
        str: 适合写入 .desktop 文件的 Exec 命令行字符串。
    """
    # 1. 优先检查系统 PATH 中是否存在打包好的独立二进制或全局软链接
    bin_path = shutil.which("kylin-monitor")
    if bin_path:
        return bin_path
    
    # 2. 检查用户目录 pip/pipx 默认安装的 CLI 入口
    local_bin = Path.home() / ".local" / "bin" / "kylin-monitor"
    if local_bin.exists():
        return str(local_bin)

    # 3. 兜底回退：使用当前 Python 解释器直接运行模块 CLI
    return f"{sys.executable} -m kylin_taskbar_monitor.cli"

def install_autostart(desktop_path: Optional[Path] = None, exec_cmd: Optional[str] = None) -> Path:
    """安装/生成开机自启动 .desktop 文件.
    
    Args:
        desktop_path: 指定 .desktop 生成目标路径，默认使用 ~/.config/autostart/kylin-taskbar-monitor.desktop。
        exec_cmd: 指定可执行命令，若未传则通过 get_exec_command() 自动嗅探探测。
        
    Returns:
        Path: 实际写入成功的 .desktop 目标文件路径。
    """
    target_path = desktop_path or DESKTOP_FILE
    # 递归创建 autostart 父级目录
    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    cmd = exec_cmd or get_exec_command()
    
    # 符合 FreeDesktop XDG Desktop Entry 标准的配置文件内容
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
    # 写入 UTF-8 编码的 .desktop 文件
    with open(target_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ 已成功安装开机自启项至: {target_path}")
    return target_path

def uninstall_autostart(desktop_path: Optional[Path] = None) -> bool:
    """移除开机自启动配置.
    
    Args:
        desktop_path: 指定要移除的 .desktop 目标路径，默认使用 DESKTOP_FILE。
        
    Returns:
        bool: 若存在且成功删除返回 True，若本来就不存在则返回 False。
    """
    target_path = desktop_path or DESKTOP_FILE
    if target_path.exists():
        target_path.unlink()
        print(f"🗑️ 已成功移除开机自启项: {target_path}")
        return True
    else:
        print("ℹ️ 未发现已安装的开机自启文件。")
        return False

def status_autostart(desktop_path: Optional[Path] = None) -> bool:
    """检查当前是否已启用开机自启动.
    
    Args:
        desktop_path: 检查的 .desktop 目标路径，默认使用 DESKTOP_FILE。
        
    Returns:
        bool: 自启动文件存在返回 True，否则返回 False。
    """
    target_path = desktop_path or DESKTOP_FILE
    return target_path.exists()

