"""Unit tests for MonitorConfig."""

import json
from pathlib import Path
from kylin_taskbar_monitor.config import MonitorConfig, DEFAULT_FORMAT

def test_default_config():
    cfg = MonitorConfig()
    assert cfg.interval == 2.0
    assert cfg.format == DEFAULT_FORMAT
    assert cfg.net_interface == "auto"
    assert cfg.icon == "utilities-system-monitor"

def test_config_save_and_load(tmp_path: Path):
    cfg_file = tmp_path / "test_config.json"
    cfg = MonitorConfig(interval=3.5, format="CPU: {cpu}%", net_interface="eth0")
    cfg.save(cfg_file)

    assert cfg_file.exists()
    loaded = MonitorConfig.load(cfg_file)
    assert loaded.interval == 3.5
    assert loaded.format == "CPU: {cpu}%"
    assert loaded.net_interface == "eth0"

def test_config_auto_create(tmp_path: Path):
    cfg_file = tmp_path / "sub" / "auto_created.json"
    assert not cfg_file.exists()
    loaded = MonitorConfig.load(cfg_file, auto_create=True)
    assert cfg_file.exists()
    assert loaded.interval == 2.0

def test_config_with_comments_and_corrupt(tmp_path: Path):
    cfg_file = tmp_path / "corrupt.json"
    # Write invalid JSON
    cfg_file.write_text("{not a valid json}", encoding="utf-8")
    loaded = MonitorConfig.load(cfg_file)
    assert loaded.interval == 2.0  # Fallback to default

    # Write JSON with comment keys
    cfg_file.write_text(json.dumps({
        "_comment": "test comment",
        "interval": 0.1,  # Should be clamped to >= 0.5
        "format": "Hello {cpu}"
    }), encoding="utf-8")
    loaded = MonitorConfig.load(cfg_file)
    assert loaded.interval == 0.5
    assert loaded.format == "Hello {cpu}"
