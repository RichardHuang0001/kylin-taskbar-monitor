"""Unit tests for indicator classes."""

import io
import sys
from kylin_taskbar_monitor.config import MonitorConfig
from kylin_taskbar_monitor.collector import MetricsCollector
from kylin_taskbar_monitor.indicator import (
    create_indicator, MockIndicator, BaseIndicator
)

def test_create_mock_indicator():
    cfg = MonitorConfig()
    collector = MetricsCollector()
    ind = create_indicator(cfg, collector, force_mock=True)
    assert isinstance(ind, MockIndicator)
    assert isinstance(ind, BaseIndicator)

def test_mock_indicator_formatting():
    cfg = MonitorConfig(format="TEST CPU:{cpu}%")
    collector = MetricsCollector()
    ind = MockIndicator(cfg, collector)
    formatted = ind.format_metrics()
    assert "TEST CPU:" in formatted

def test_mock_indicator_update_label():
    cfg = MonitorConfig()
    collector = MetricsCollector()
    ind = MockIndicator(cfg, collector)
    
    buf = io.StringIO()
    orig_stdout = sys.stdout
    try:
        sys.stdout = buf
        ind.update_label("test-status")
        output = buf.getvalue()
        assert "[任务栏模拟]" in output
        assert "test-status" in output
    finally:
        sys.stdout = orig_stdout

def test_mock_indicator_stop():
    cfg = MonitorConfig()
    collector = MetricsCollector()
    ind = MockIndicator(cfg, collector)
    ind._is_running = True
    ind.stop()
    assert ind._is_running is False
