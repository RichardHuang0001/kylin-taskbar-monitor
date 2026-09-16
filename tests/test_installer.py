"""Unit tests for autostart installer."""

from pathlib import Path
from kylin_taskbar_monitor.installer import (
    install_autostart, uninstall_autostart, status_autostart, get_exec_command
)

def test_get_exec_command():
    cmd = get_exec_command()
    assert isinstance(cmd, str)
    assert len(cmd) > 0

def test_installer_lifecycle(tmp_path: Path):
    test_desktop = tmp_path / "autostart" / "test.desktop"
    assert not status_autostart(test_desktop)

    # Install
    installed_path = install_autostart(desktop_path=test_desktop, exec_cmd="/usr/bin/kylin-monitor")
    assert installed_path == test_desktop
    assert test_desktop.exists()
    assert status_autostart(test_desktop)

    content = test_desktop.read_text(encoding="utf-8")
    assert "[Desktop Entry]" in content
    assert "Exec=/usr/bin/kylin-monitor" in content
    assert "Terminal=false" in content
    assert "Type=Application" in content

    # Uninstall
    result = uninstall_autostart(desktop_path=test_desktop)
    assert result is True
    assert not test_desktop.exists()
    assert not status_autostart(test_desktop)

    # Uninstall again should return False
    result_second = uninstall_autostart(desktop_path=test_desktop)
    assert result_second is False
