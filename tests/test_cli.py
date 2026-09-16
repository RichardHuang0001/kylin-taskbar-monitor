"""Unit tests for CLI entrypoint."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from kylin_taskbar_monitor.cli import main
from kylin_taskbar_monitor import __version__

def test_cli_version(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert __version__ in captured.out or __version__ in captured.err

def test_cli_status(capsys):
    with patch("kylin_taskbar_monitor.cli.status_autostart", return_value=True):
        ret = main(["--status"])
        assert ret == 0
        captured = capsys.readouterr()
        assert "已启用" in captured.out

def test_cli_init_config(tmp_path: Path):
    target_config = tmp_path / "custom_config.json"
    assert not target_config.exists()
    ret = main(["-c", str(target_config), "--init-config"])
    assert ret == 0
    assert target_config.exists()

def test_cli_install_uninstall():
    with patch("kylin_taskbar_monitor.cli.install_autostart") as mock_install:
        ret = main(["--install"])
        assert ret == 0
        mock_install.assert_called_once()

    with patch("kylin_taskbar_monitor.cli.uninstall_autostart") as mock_uninstall:
        ret = main(["--uninstall"])
        assert ret == 0
        mock_uninstall.assert_called_once()

def test_cli_overrides_and_run():
    mock_ind = MagicMock()
    with patch("kylin_taskbar_monitor.cli.create_indicator", return_value=mock_ind) as mock_create:
        ret = main([
            "--mock",
            "--interval", "4.0",
            "--format", "CPU: {cpu}%",
            "--net-interface", "eth1",
            "--dock-x", "50",
            "--dock-y", "60",
            "--mode", "dock"
        ])
        assert ret == 0
        mock_ind.run.assert_called_once()
        
        args, kwargs = mock_create.call_args
        config, collector = args
        assert config.interval == 4.0
        assert config.format == "CPU: {cpu}%"
        assert config.net_interface == "eth1"
        assert config.dock_x == 50
        assert config.dock_y == 60
        assert config.mode == "dock"
        assert collector.net_interface == "eth1"
        assert kwargs["force_mock"] is True

