"""AppIndicator interface with Linux native backend and macOS mock backend."""

import os
import signal
import sys
import time
from abc import ABC, abstractmethod
from typing import Optional, List, Any
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
        self._menu_timer_id: Optional[int] = None
        self._menu_open_time: float = 0.0
        self._menu_core_items: List[Any] = []
        self._menu_proc_items: List[Any] = []
        self._current_menu: Optional[Any] = None

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

    def _setup_css(self, Gtk, Gdk):
        css_data = b"""
        #kylin-dock-window {
            background-color: #1a1d24;
            border: 1px solid #333948;
            border-radius: 4px;
        }
        #kylin-dock-label {
            color: #dce4ec;
            font-family: monospace, "DejaVu Sans Mono", "Liberation Mono";
            font-size: 15px;
            font-weight: 600;
            padding: 4px 10px;
        }
        menuitem.monitor-title:disabled label,
        menuitem.monitor-title:disabled {
            color: #1d4ed8;
            font-weight: 700;
            font-size: 14px;
            opacity: 1.0;
        }
        menuitem.monitor-section:disabled label,
        menuitem.monitor-section:disabled {
            color: #0369a1;
            font-weight: 600;
            font-size: 13px;
            opacity: 1.0;
        }
        menuitem.monitor-mono:disabled label,
        menuitem.monitor-mono:disabled {
            color: #0f172a;
            font-family: monospace, "DejaVu Sans Mono", "Liberation Mono";
            font-size: 14px;
            font-weight: 500;
            opacity: 1.0;
        }
        menuitem.monitor-proc:disabled label,
        menuitem.monitor-proc:disabled {
            color: #0f172a;
            font-family: monospace, "DejaVu Sans Mono", "Liberation Mono";
            font-size: 16px;
            font-weight: 600;
            opacity: 1.0;
        }
        menuitem.monitor-item:disabled label,
        menuitem.monitor-item:disabled {
            color: #1e293b;
            opacity: 1.0;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css_data)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
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
        about.set_version("0.2.5")
        about.set_copyright("Copyright © 2026 Huang Wei")
        about.set_comments("信创极轻量任务栏性能监视器 (银河麒麟/统信UOS 高能效极速版)")
        about.connect("response", lambda d, r: d.destroy())
        about.show_all()

    def _stop_menu_timer(self) -> None:
        """Immediately stop dynamic menu refresh and release widget references."""
        if self._menu_timer_id is not None and self._glib:
            try:
                self._glib.source_remove(self._menu_timer_id)
            except Exception:
                pass
            self._menu_timer_id = None
        self._current_menu = None
        self._menu_core_items.clear()
        self._menu_proc_items.clear()

    def _update_menu_content(self) -> None:
        """In-place update of MenuItem text with zero flicker and negligible overhead."""
        try:
            # 1. Update Per-Core stats in-place
            cores = self.collector.get_per_cpu_percent()
            if cores and self._menu_core_items:
                chunks = [cores[i:i + 4] for i in range(0, len(cores), 4)]
                for row_idx, chunk in enumerate(chunks):
                    if row_idx < len(self._menu_core_items):
                        parts = [f"C{row_idx * 4 + idx}:{val:>2.0f}%" for idx, val in enumerate(chunk)]
                        self._menu_core_items[row_idx].set_label("  " + "  ".join(parts))

            # 2. Update Top 5 processes in-place
            top_procs = self.collector.get_top_processes(limit=5)
            for idx in range(len(self._menu_proc_items)):
                item = self._menu_proc_items[idx]
                if top_procs and idx < len(top_procs):
                    p = top_procs[idx]
                    p_name = p['name']
                    if len(p_name) > 18:
                        p_name = p_name[:17] + "…"
                    item.set_label(f"  • {p['cpu']:>5.1f}%  {p_name:<18} (PID {p['pid']})")
                    item.show()
                elif idx == 0 and not top_procs:
                    item.set_label("  • 所有进程 CPU < 1% (系统空闲)")
                    item.show()
                else:
                    item.hide()
        except Exception:
            pass

    def _menu_refresh_tick(self) -> bool:
        """3-second dynamic refresh callback with 30-second circuit breaker."""
        # 1. Check if menu is still active and visible
        if not self._current_menu or not self._current_menu.get_visible():
            self._stop_menu_timer()
            return False

        # 2. Circuit breaker: maximum 30 seconds of dynamic refresh
        now = time.time()
        if now - self._menu_open_time >= 30.0:
            self._stop_menu_timer()
            return False

        # 3. In-place content update
        self._update_menu_content()
        return True

    def _on_menu_closed(self, menu):
        """Teardown when menu is dismissed or closed by user."""
        self._stop_menu_timer()
        try:
            menu.destroy()
        except Exception:
            pass

    def _show_context_menu(self, event):
        Gtk = self._gtk
        # Terminate any previously dangling timer
        self._stop_menu_timer()

        menu = Gtk.Menu()
        self._current_menu = menu

        # Connect exit events for complete zero-leak teardown
        menu.connect("selection-done", self._on_menu_closed)
        menu.connect("deactivate", self._on_menu_closed)
        menu.connect("destroy", self._on_menu_closed)

        item_title = Gtk.MenuItem(label="信创性能监控 v0.2.5")
        item_title.set_sensitive(False)
        item_title.get_style_context().add_class("monitor-title")
        menu.append(item_title)

        menu.append(Gtk.SeparatorMenuItem())

        # 1. Per-Core CPU (slots)
        cores = self.collector.get_per_cpu_percent()
        if cores:
            item_core_header = Gtk.MenuItem(label="【CPU 各核心负载】")
            item_core_header.set_sensitive(False)
            item_core_header.get_style_context().add_class("monitor-section")
            menu.append(item_core_header)

            chunks = [cores[i:i + 4] for i in range(0, len(cores), 4)]
            self._menu_core_items = []
            for row_idx, chunk in enumerate(chunks):
                parts = [f"C{row_idx * 4 + idx}:{val:>2.0f}%" for idx, val in enumerate(chunk)]
                line_str = "  " + "  ".join(parts)
                item_core = Gtk.MenuItem(label=line_str)
                item_core.set_sensitive(False)
                item_core.get_style_context().add_class("monitor-mono")
                menu.append(item_core)
                self._menu_core_items.append(item_core)

            menu.append(Gtk.SeparatorMenuItem())

        # 2. Top CPU-consuming processes (5 fixed slots)
        item_proc_header = Gtk.MenuItem(label="【高负载进程 Top 5 (3秒动态刷新)】")
        item_proc_header.set_sensitive(False)
        item_proc_header.get_style_context().add_class("monitor-section")
        menu.append(item_proc_header)

        self._menu_proc_items = []
        for _ in range(5):
            item_p = Gtk.MenuItem(label="")
            item_p.set_sensitive(False)
            item_p.get_style_context().add_class("monitor-proc")
            menu.append(item_p)
            self._menu_proc_items.append(item_p)

        # Initial populate
        self._update_menu_content()

        menu.append(Gtk.SeparatorMenuItem())

        # 3. GPU Info (on-demand / cached)
        gpu = self.collector.get_gpu_info()
        if gpu and gpu.get("available"):
            gpu_text = f"【显卡】{gpu['name']} (显存: {gpu['vram']} | {gpu['clock']})"
            item_gpu = Gtk.MenuItem(label=gpu_text)
            item_gpu.set_sensitive(False)
            item_gpu.get_style_context().add_class("monitor-section")
            menu.append(item_gpu)
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

        # Start dynamic 3-second refresh timer with timestamp
        self._menu_open_time = time.time()
        self._menu_timer_id = self._glib.timeout_add_seconds(3, self._menu_refresh_tick)

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
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() if display else None
        if monitor:
            geom = monitor.get_geometry()
        else:
            screen = Gdk.Screen.get_default()
            p = screen.get_primary_monitor() if screen else 0
            geom = screen.get_monitor_geometry(p if p >= 0 else 0) if screen else type("Geom", (), {"x": 0, "y": 0, "width": 1920, "height": 1080})()
        
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

        self._setup_css(Gtk, Gdk)

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
        self._stop_menu_timer()
        if self._gtk:
            self._gtk.main_quit()

# Backwards compatibility alias
LinuxAppIndicator = LinuxDockIndicator

def create_indicator(config: MonitorConfig, collector: MetricsCollector, force_mock: bool = False) -> BaseIndicator:
    if force_mock or sys.platform == "darwin" or getattr(config, "mode", "dock") == "mock":
        return MockIndicator(config, collector)
    return LinuxDockIndicator(config, collector)

