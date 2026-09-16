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

class LinuxDockIndicator(BaseIndicator):
    """Ultra-lightweight X11 Dock window indicator for Kylin OS (UKUI).
    Uses solid 2D RGB rendering (Zero Compositor / Zero Alpha CPU overhead)
    specifically optimized for low-performance x86/ARM legacy chips.
    """
    def __init__(self, config: MonitorConfig, collector: MetricsCollector):
        super().__init__(config, collector)
        self.window = None
        self.label = None
        self._last_text = ""
        self._drag_data = None
        self._gtk = None
        self._glib = None

    def _init_gtk(self):
        try:
            import gi
            gi.require_version('Gtk', '3.0')
            from gi.repository import Gtk, Gdk, GLib
            return Gtk, Gdk, GLib
        except Exception as e:
            print(f"❌ 初始化 GTK 运行环境失败: {e}")
            print("💡 请在信创/Ubuntu系统上执行:")
            print("   sudo apt install gir1.2-gtk-3.0 python3-psutil -y")
            sys.exit(1)

    def _setup_css(self, Gtk):
        css_data = b"""
        #kylin-dock-window {
            background-color: #1a1d24;
            border: 1px solid #333948;
            border-radius: 4px;
        }
        #kylin-dock-label {
            color: #dce4ec;
            font-family: monospace, "DejaVu Sans Mono", "Liberation Mono";
            font-size: 11px;
            font-weight: 600;
            padding: 3px 8px;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css_data)
        Gtk.StyleContext.add_provider_for_screen(
            Gtk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

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
        about.set_version("0.2.0")
        about.set_copyright("Copyright © 2026 Huang Wei")
        about.set_comments("信创极轻量任务栏性能监视器 (银河麒麟/统信UOS 高能效极速版)")
        about.connect("response", lambda d, r: d.destroy())
        about.show_all()

    def _show_context_menu(self, event):
        Gtk = self._gtk
        menu = Gtk.Menu()

        item_title = Gtk.MenuItem(label="信创性能监控 v0.2.0 (极低功耗)")
        item_title.set_sensitive(False)
        menu.append(item_title)

        menu.append(Gtk.SeparatorMenuItem())

        item_config = Gtk.MenuItem(label="打开配置文件")
        item_config.connect("activate", self._open_config)
        menu.append(item_config)

        item_about = Gtk.MenuItem(label="关于")
        item_about.connect("activate", self._show_about)
        menu.append(item_about)

        menu.append(Gtk.SeparatorMenuItem())

        item_quit = Gtk.MenuItem(label="退出监控")
        item_quit.connect("activate", lambda _: self.stop())
        menu.append(item_quit)

        menu.show_all()
        menu.popup_at_pointer(event)

    def _on_button_press(self, widget, event):
        if event.button == 1:  # Left click: start drag
            self._drag_data = (event.x_root, event.y_root, *self.window.get_position())
        elif event.button == 3:  # Right click: popup menu
            self._show_context_menu(event)

    def _on_motion_notify(self, widget, event):
        if self._drag_data:
            start_x, start_y, win_x, win_y = self._drag_data
            dx = int(event.x_root - start_x)
            dy = int(event.y_root - start_y)
            self.window.move(win_x + dx, win_y + dy)

    def _on_button_release(self, widget, event):
        if event.button == 1 and self._drag_data:
            self._drag_data = None
            new_x, new_y = self.window.get_position()
            # Save docked position for persistence across boots
            self.config.dock_x = new_x
            self.config.dock_y = new_y
            try:
                self.config.save()
            except Exception:
                pass

    def update_label(self, label: str) -> None:
        # Dirty check: Zero CPU cycles & zero GTK redraw if text has not changed
        if self.label and label != self._last_text:
            self._last_text = label
            self.label.set_text(label)

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

    def _position_window(self, Gdk):
        screen = Gdk.Screen.get_default()
        monitor = screen.get_primary_monitor()
        if not monitor:
            monitor = screen.get_monitor_at_point(0, 0)
        geom = monitor.get_geometry()
        
        # Calculate preferred size
        _, natural_req = self.window.get_preferred_size()
        w = max(260, natural_req.width)
        h = max(24, natural_req.height)

        if self.config.dock_x >= 0 and self.config.dock_y >= 0:
            self.window.move(self.config.dock_x, self.config.dock_y)
        else:
            # Smart default: docked right above UKUI taskbar (bottom-right)
            x = geom.x + geom.width - w - 16
            y = geom.y + geom.height - 44 - h - 6
            self.window.move(max(0, x), max(0, y))

    def start(self) -> None:
        Gtk, Gdk, GLib = self._init_gtk()
        self._gtk = Gtk
        self._glib = GLib
        self._is_running = True

        self._setup_css(Gtk)

        # 1. Native Solid Dock Window (Zero composite overhead)
        self.window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self.window.set_name("kylin-dock-window")
        self.window.set_type_hint(Gdk.WindowTypeHint.DOCK)
        self.window.set_decorated(False)
        self.window.set_keep_above(True)
        self.window.set_skip_taskbar_hint(True)
        self.window.set_skip_pager_hint(True)
        self.window.set_accept_focus(False)
        self.window.set_title("KylinTaskbarMonitor")

        # 2. Label
        self.label = Gtk.Label(label=" 初始化监控中... ")
        self.label.set_name("kylin-dock-label")
        self.window.add(self.label)

        # 3. Mouse events for dragging & right-click
        self.window.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK |
            Gdk.EventMask.BUTTON_RELEASE_MASK |
            Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.window.connect("button-press-event", self._on_button_press)
        self.window.connect("motion-notify-event", self._on_motion_notify)
        self.window.connect("button-release-event", self._on_button_release)

        # 4. Signal handlers
        try:
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self.stop)
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self.stop)
        except Exception:
            pass

        self.window.show_all()
        self._position_window(Gdk)

        # Initial tick
        self._tick()

        # Schedule timer: timeout_add_seconds saves CPU wakeups
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

# Backwards compatibility alias
LinuxAppIndicator = LinuxDockIndicator

def create_indicator(config: MonitorConfig, collector: MetricsCollector, force_mock: bool = False) -> BaseIndicator:
    if force_mock or sys.platform == "darwin" or getattr(config, "mode", "dock") == "mock":
        return MockIndicator(config, collector)
    return LinuxDockIndicator(config, collector)

