"""Unit tests for MetricsCollector."""

import time
from unittest.mock import patch
from kylin_taskbar_monitor.collector import MetricsCollector, format_speed
from kylin_taskbar_monitor.config import MonitorConfig

def test_format_speed():
    assert format_speed(-100) == "0K/s"
    assert format_speed(0) == "0K/s"
    assert format_speed(500) == "0K/s"
    assert format_speed(1024 * 50) == "50K/s"
    assert format_speed(1024 * 1024 * 2.5) == "2.5M/s"
    assert format_speed(1024 * 1024 * 1024 * 1.5) == "1.5G/s"
    # Fixed width 6 chars for 125% fractional scaling jitter prevention
    assert format_speed(500, fixed_width=True) == "  0K/s"
    assert len(format_speed(500, fixed_width=True)) == 6
    assert len(format_speed(1024 * 1024 * 2.5, fixed_width=True)) == 6

def test_collector_metrics():
    collector = MetricsCollector()
    time.sleep(0.05)
    metrics = collector.collect()
    
    expected_keys = {
        "cpu", "cpu_float", "mem_used_g", "mem_total_g", 
        "mem_free_g", "mem_percent", "down_speed", "up_speed", 
        "down_bps", "up_bps"
    }
    assert expected_keys.issubset(metrics.keys())
    assert metrics["mem_total_g"] > 0
    assert 0 <= metrics["cpu"] <= 100
    assert metrics["down_bps"] >= 0
    assert metrics["up_bps"] >= 0
    assert len(metrics["down_speed"]) == 6
    assert len(metrics["up_speed"]) == 6

def test_config_template():
    config = MonitorConfig()
    collector = MetricsCollector()
    metrics = collector.collect()
    text = config.format.format(**metrics)
    assert "CPU" in text
    assert "内存" in text
    assert "↓" in text
    assert "↑" in text

def test_collector_counter_reset():
    collector = MetricsCollector()
    collector.last_bytes_recv = 100000
    collector.last_bytes_sent = 100000
    
    # Simulate network interface reset (bytes_recv dropped to 100)
    with patch.object(collector, "_get_net_bytes", return_value=(100, 100)):
        metrics = collector.collect()
        assert metrics["down_speed"].strip() == "0K/s"
        assert metrics["up_speed"].strip() == "0K/s"

def test_collector_specific_interface():
    collector = MetricsCollector(net_interface="non_existent_interface_xyz")
    metrics = collector.collect()
    assert "down_speed" in metrics
