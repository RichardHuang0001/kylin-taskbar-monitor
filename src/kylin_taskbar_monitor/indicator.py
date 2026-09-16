"""AppIndicator interface with Linux native backend and macOS mock backend."""

import os
import signal
import sys
import time
from abc import ABC, abstractmethod
from typing import Optional
from .config import MonitorConfig, DEFAULT_CONFIG_PATH
from .collector import MetricsCollector

class BaseIndicator(ABC):
    def __init__(self, config: MonitorConfig, collector: MetricsCollector):
        self.config = config
        self.collector = collector
        self._is_running = False

    @abstractmethod
    def start(self) -> None:
        """Start the indicator update loop."""
        pass

    @abstractmethod
    def update_label(self, label: str) -> None:
        """Update the indicator text or label."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stop the indicator loop."""
        pass

    def run(self) -> None:
        """Blocking entry point."""
        self.start()

class MockIndicator(BaseIndicator):
    """Terminal-based preview indicator for development on macOS."""
    def __init__(self, config: MonitorConfig, collector: MetricsCollector):
        super().__init__(config, collector)

    def format_metrics(self) -> str:
        metrics = self.collector.collect()
        try:
            return self.config.format.format(**metrics)
        except Exception as e:
            return f"格式化错误: {e}"

    def update_label(self, label: str) -> None:
        sys.stdout.write(f"\r\033[K[任务栏模拟] 👉  {label}")
        sys.stdout.flush()

    def start(self) -> None:
        self._is_running = True
        print("\n🚀 [Mock 模式启动 - 终端实时预览 (Mac 环境友好)]")
        print(f"• 采样间隔: {self.config.interval}s")
        print(f"• 模板格式: {self.config.format}")
        print("• 按 Ctrl+C 退出测试\n")
        try:
            while self._is_running:
                text = self.format_metrics()
                self.update_label(text)
                time.sleep(self.config.interval)
        except KeyboardInterrupt:
            self.stop()

    def stop(self) -> None:
        self._is_running = False
        print("\n👋 已退出 Mock 预览。")

class LinuxAppIndicator(BaseIndicator):
    """Native Linux AppIndicator backend using GTK3 & libappindicator."""
    def __init__(self, config: MonitorConfig, collector: MetricsCollector):
        super().__init__(config, collector)
        self.indicator = None
        self._gtk = None
        self._glib = None

    def _init_gtk(self):
        try:
            import gi
            gi.require_version('Gtk', '3.0')
            try:
                gi.require_version('AppIndicator3', '0.1')
                from gi.repository import AppIndicator3 as appindicator
            except (ValueError, ImportError):
                gi.require_version('AyatanaAppIndicator3', '0.1')
                from gi.repository import AyatanaAppIndicator3 as appindicator
            from gi.repository import Gtk, GLib, Gio
            return appindicator, Gtk, GLib, Gio
        except Exception as e:
            print(f"❌ 初始化 Linux 图形托盘失败: {e}")
            print("💡 如果在信创/Ubuntu系统上，请确保已安装依赖:")
            print("   sudo apt install gir1.2-appindicator3-0.1 python3-psutil -y")
            sys.exit(1)

    def _open_config(self, _widget):
        try:
            import subprocess
            subprocess.Popen(["xdg-open", str(DEFAULT_CONFIG_PATH)])
        except Exception as e:
            print(f"[Warn] 无法打开配置文件: {e}")

    def _show_about(self, _widget):
        Gtk = self._gtk
        about = Gtk.AboutDialog()
        about.set_program_name("Kylin Taskbar Monitor")
        about.set_version("0.1.0")
        about.set_copyright("Copyright © 2026 Huang Wei")
        about.set_comments("信创国产系统极轻量任务栏性能监视器 (银河麒麟/统信UOS)")
        about.set_website_label("Project Home")
        about.connect("response", lambda d, r: d.destroy())
        about.show_all()

    def _get_safe_guide(self) -> str:
        """Compute maximum bounding box for guide string with 125% scaling safety margin."""
        sample_metrics = {
            "cpu": 100,
            "cpu_float": 100.0,
            "mem_used_g": 99.9,
            "mem_total_g": 99.9,
            "mem_free_g": 99.9,
            "mem_percent": 100,
            "down_speed": "999.9M/s",
            "up_speed": "999.9M/s",
            "down_bps": 999999999.0,
            "up_bps": 999999999.0,
        }
        try:
            rendered = self.config.format.format(**sample_metrics)
        except Exception:
            rendered = "CPU 100% | 内存 99.9G | ↓999.9M/s | ↑999.9M/s"
        # 12% safety margin accounts for fractional font layout at 125% DPI scale
        margin = " " * max(3, int(len(rendered) * 0.12))
        return f"  {rendered}{margin}  "

    def update_label(self, label: str) -> None:
        if self.indicator:
            # 2 spaces on each side prevent crowding adjacent icons
            self.indicator.set_label(f"  {label}  ", self._guide_string)

    def _tick(self) -> bool:
        if not self._is_running:
            return False
        metrics = self.collector.collect()
        try:
            label_text = self.config.format.format(**metrics)
        except Exception as e:
            label_text = f"Err: {e}"
        self.update_label(label_text)
        return True

    def start(self) -> None:
        appindicator, Gtk, GLib, Gio = self._init_gtk()
        self._gtk = Gtk
        self._glib = GLib
        self._is_running = True
        self._guide_string = self._get_safe_guide()

        # If show_icon is disabled, pass empty or transparent icon to save tray width
        icon_name = self.config.icon if getattr(self.config, "show_icon", False) else ""
        if not icon_name:
            icon_name = "application-x-zerosize"  # Standard GNOME/Kylin empty icon fallback

        self.indicator = appindicator.Indicator.new(
            "kylin-perf-monitor",
            icon_name,
            appindicator.IndicatorCategory.SYSTEM_SERVICES
        )
        self.indicator.set_status(appindicator.IndicatorStatus.ACTIVE)

        # Right-click context menu
        menu = Gtk.Menu()
        
        # 1. Title / Header
        item_title = Gtk.MenuItem(label="信创极轻量性能监控 v0.1.0")
        item_title.set_sensitive(False)
        menu.append(item_title)

        menu.append(Gtk.SeparatorMenuItem())

        # 2. Open Config
        item_config = Gtk.MenuItem(label="打开配置文件")
        item_config.connect("activate", self._open_config)
        menu.append(item_config)

        # 3. About
        item_about = Gtk.MenuItem(label="关于")
        item_about.connect("activate", self._show_about)
        menu.append(item_about)

        menu.append(Gtk.SeparatorMenuItem())

        # 4. Quit
        item_quit = Gtk.MenuItem(label="退出监控")
        item_quit.connect("activate", lambda _: self.stop())
        menu.append(item_quit)

        menu.show_all()
        self.indicator.set_menu(menu)

        # Signal handlers for graceful exit on SIGINT/SIGTERM
        try:
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self.stop)
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self.stop)
        except Exception:
            pass

        # Initial tick
        self._tick()

        # Schedule timer: use timeout_add_seconds for integer seconds to save wakeups
        interval = self.config.interval
        if interval.is_integer() and interval >= 1.0:
            GLib.timeout_add_seconds(int(interval), self._tick)
        else:
            GLib.timeout_add(int(interval * 1000), self._tick)

        Gtk.main()

    def stop(self) -> None:
        self._is_running = False
        if self._gtk:
            self._gtk.main_quit()

def create_indicator(config: MonitorConfig, collector: MetricsCollector, force_mock: bool = False) -> BaseIndicator:
    if force_mock or sys.platform == "darwin":
        return MockIndicator(config, collector)
    return LinuxAppIndicator(config, collector)
