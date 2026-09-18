"""任务栏指示器与图形用户界面层 (Indicator & UI Frontend).

设计背景与架构实现：
1. 界面呈现策略：
   在银河麒麟 (UKUI)、统信 (UOS/DDE) 等 Linux 信创桌面上，传统的 libappindicator 托盘
   往往存在文字过长被截断、多列对齐混乱、刷新闪烁以及依赖库版本断层等问题。
   本项目采用独立的 X11 Dock 悬浮挂件窗口 (LinuxDockIndicator) 方案：
   - 具备置顶 (keep-above)、避开任务栏/分页器 (skip-taskbar / skip-pager) 特性；
   - 采用纯实色渲染 (Solid 2D RGB)，完全规避了老旧集成显卡或 ARM/兆芯 CPU
     计算 Alpha 半透明混合时的 Compositor 性能负担；
   - 支持鼠标左键自由拖拽，松手自动记忆坐标并写入配置文件；
   - 支持右键呼出原生 GTK3 性能详情菜单，具备按需 3 秒局部动态刷新与 30 秒熔断保护机制。
2. 开发测试友好：
   提供 MockIndicator 实现，支持在 macOS 或纯终端无桌面环境下以单行实时刷新的形式进行预览。
"""

import os
import signal
import sys
import time
from abc import ABC, abstractmethod
from typing import Optional, List, Any
from .config import MonitorConfig, DEFAULT_CONFIG_PATH
from .collector import MetricsCollector

class BaseIndicator(ABC):
    """指示器基类（抽象接口定义）."""

    def __init__(self, config: MonitorConfig, collector: MetricsCollector):
        """初始化指示器基类.
        
        Args:
            config: 监视器配置对象。
            collector: 性能指标采集器实例。
        """
        self.config = config
        self.collector = collector
        self._is_running = False

    @abstractmethod
    def start(self) -> None:
        """启动指示器并进入主运行循环."""
        pass

    @abstractmethod
    def update_label(self, label: str) -> None:
        """更新展示的性能文本标签内容.
        
        Args:
            label: 格式化后的监控文本字符串。
        """
        pass

    @abstractmethod
    def stop(self) -> None:
        """停止指示器并释放所有关联资源."""
        pass

    def run(self) -> None:
        """指示器阻塞运行入口."""
        self.start()

class MockIndicator(BaseIndicator):
    """终端模拟预览指示器（专供 macOS 开发调试及无桌面环境预览）."""

    def __init__(self, config: MonitorConfig, collector: MetricsCollector):
        super().__init__(config, collector)

    def format_metrics(self) -> str:
        """采集当前性能指标并应用用户定义的模板进行格式化.
        
        Returns:
            str: 格式化后的监控文本。
        """
        metrics = self.collector.collect()
        try:
            return self.config.format.format(**metrics)
        except Exception as e:
            return f"格式化错误: {e}"

    def update_label(self, label: str) -> None:
        """利用 ANSI 转义符在终端单行原地覆盖刷新文本.
        
        \\r 返回行首，\\033[K 清除当前行从光标到末尾的内容。
        """
        sys.stdout.write(f"\r\033[K[任务栏模拟] 👉  {label}")
        sys.stdout.flush()

    def start(self) -> None:
        """启动终端文本刷新循环."""
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
        """退出终端模拟预览."""
        self._is_running = False
        print("\n👋 已退出 Mock 预览。")

class LinuxDockIndicator(BaseIndicator):
    """Linux 原生 X11 Dock 悬浮挂件指示器.
    
    专为银河麒麟 (UKUI) 与信创环境调优，采用 GTK3 原生控件与实色 2D RGB 渲染，
    完全杜绝老旧 x86/ARM/兆芯等信创处理器的 Compositor 透明 Alpha 计算开销。
    """

    def __init__(self, config: MonitorConfig, collector: MetricsCollector):
        super().__init__(config, collector)
        # GTK 核心窗口及文本标签控件
        self.window = None
        self.label = None
        # 上一次渲染的文本缓存，用于脏检查 (Dirty-check) 避免重复重绘
        self._last_text = ""
        # 鼠标拖拽状态记录：(start_x, start_y, win_x, win_y)
        self._drag_data = None
        # 动态延迟导入的 GTK / GLib 模块句柄
        self._gtk = None
        self._glib = None
        
        # 菜单动态刷新定时器管理
        self._menu_timer_id: Optional[int] = None
        self._menu_open_time: float = 0.0
        # 预先分配的菜单项固定槽位（实现原地 set_label 局部更新）
        self._menu_core_items: List[Any] = []
        self._menu_proc_items: List[Any] = []
        # 当前弹出的菜单对象弱引用
        self._current_menu: Optional[Any] = None

    def _init_gtk(self):
        """安全动态导入 PyGObject (GTK 3.0) 运行时.
        
        若系统未安装必要的依赖包，给出明确友好的 apt 安装提示并安全退出。
        """
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
        """配置并应用 GTK3 CSS 样式表.
        
        设计规范：
        - 挂件背景：深色底 (#1a1d24) 搭配柔和边框 (#333948)，保证在各类桌面壁纸下均清晰可读；
        - 等宽字体：使用 monospace / DejaVu Sans Mono / Liberation Mono，保证数字变动时宽度稳定；
        - 右键菜单：使用清晰的分组层级、蓝灰强调色与高对比度字体展示核心负载与 Top 5 进程。
        """
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
        # 将样式注入到当前屏幕全局最高优先级
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _open_config(self, _widget):
        """通过系统的 xdg-open 调用默认文本编辑器打开配置文件."""
        try:
            import subprocess
            subprocess.Popen(["xdg-open", str(DEFAULT_CONFIG_PATH)])
        except Exception as e:
            print(f"[Warn] 无法打开配置文件: {e}")

    def _show_about(self, _widget):
        """弹出 GTK 原生标准“关于”对话框."""
        Gtk = self._gtk
        about = Gtk.AboutDialog()
        about.set_program_name("Kylin Taskbar Monitor")
        about.set_version("0.2.5")
        about.set_copyright("Copyright © 2026 Huang Wei")
        about.set_comments("信创极轻量任务栏性能监视器 (银河麒麟/统信UOS 高能效极速版)")
        # 监听对话框关闭按钮事件，销毁窗口
        about.connect("response", lambda d, r: d.destroy())
        about.show_all()

    def _stop_menu_timer(self) -> None:
        """立即终止右键菜单动态刷新定时器，并释放所有关联控件的缓存引用.
        
        彻底避免在菜单已关闭的情况下后台依然空转刷新，造成内存或定时器泄漏。
        """
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
        """原地更新菜单项文字标签（零闪烁、极小 CPU 开销）.
        
        优化机制：不销毁、不重建任何 MenuItem 控件，直接调用 `set_label` 局部刷新内容。
        """
        try:
            # 1. 原地更新 CPU 各核心负载 (每行展示 4 个核心)
            cores = self.collector.get_per_cpu_percent()
            if cores and self._menu_core_items:
                chunks = [cores[i:i + 4] for i in range(0, len(cores), 4)]
                for row_idx, chunk in enumerate(chunks):
                    if row_idx < len(self._menu_core_items):
                        parts = [f"C{row_idx * 4 + idx}:{val:>2.0f}%" for idx, val in enumerate(chunk)]
                        self._menu_core_items[row_idx].set_label("  " + "  ".join(parts))

            # 2. 原地更新 Top 5 进程槽位
            top_procs = self.collector.get_top_processes(limit=5)
            for idx in range(len(self._menu_proc_items)):
                item = self._menu_proc_items[idx]
                if top_procs and idx < len(top_procs):
                    p = top_procs[idx]
                    p_name = p['name']
                    # 超长进程名称截断处理，保持菜单整洁
                    if len(p_name) > 18:
                        p_name = p_name[:17] + "…"
                    item.set_label(f"  • {p['cpu']:>5.1f}%  {p_name:<18} (PID {p['pid']})")
                    item.show()
                elif idx == 0 and not top_procs:
                    # 所有进程占用均低于 1% 时的提示
                    item.set_label("  • 所有进程 CPU < 1% (系统空闲)")
                    item.show()
                else:
                    item.hide()
        except Exception:
            pass


    def _menu_refresh_tick(self) -> bool:
        """右键菜单 3 秒局部动态刷新回调函数（带 30 秒无操作熔断保护）.
        
        优化机制：
        1. 视口与活跃性检查：若菜单已不可见或被销毁，立即解除定时器，杜绝空转；
        2. 熔断保护：若菜单保持弹出超过 30 秒，自动停止动态刷新，防止用户离开工位造成长时间无效开销；
        3. 增量更新：原地刷新各核心负载与 Top 5 进程列表，维持极低资源消耗。
        
        Returns:
            bool: 返回 True 继续下次调度，返回 False 销毁当前定时器。
        """
        # 1. 检查菜单控件是否仍然存活且处于可见状态
        if not self._current_menu or not self._current_menu.get_visible():
            self._stop_menu_timer()
            return False

        # 2. 熔断机制：单次菜单弹出最长允许 30 秒的动态连续刷新
        now = time.time()
        if now - self._menu_open_time >= 30.0:
            self._stop_menu_timer()
            return False

        # 3. 原地更新文本内容
        self._update_menu_content()
        return True

    def _on_menu_closed(self, menu):
        """当用户在菜单外部点击或点击菜单项时触发的清理回调.
        
        执行完整的资源清理与定时器停止，随后安全销毁菜单对象。
        """
        self._stop_menu_timer()
        try:
            menu.destroy()
        except Exception:
            pass

    def _show_context_menu(self, event):
        """构建并弹出原生 GTK3 上下文菜单 (包含多核详情、Top 进程及系统设置).
        
        菜单层级结构：
        - 标题：信创性能监控版本号
        - 分割线
        - 【CPU 各核心负载】：按核心编号展示负载率 (C0: xx%  C1: xx% ...)
        - 分割线
        - 【高负载进程 Top 5】：固定 5 个槽位，原地 3 秒动态更新
        - 分割线
        - 【显卡信息】：检测到的显卡型号、显存及频率（若有）
        - 打开配置文件
        - 关于
        - 分割线
        - 退出监控
        
        Args:
            event: Gdk 鼠标点击事件对象，用于定位菜单弹出坐标。
        """
        Gtk = self._gtk
        # 弹出新菜单前先终止可能存在的旧定时器
        self._stop_menu_timer()

        menu = Gtk.Menu()
        self._current_menu = menu

        # 绑定菜单关闭与注销事件，实现 100% 资源零泄漏释放
        menu.connect("selection-done", self._on_menu_closed)
        menu.connect("deactivate", self._on_menu_closed)
        menu.connect("destroy", self._on_menu_closed)

        # 顶部标题栏（置灰不可点击）
        item_title = Gtk.MenuItem(label="信创性能监控 v0.2.5")
        item_title.set_sensitive(False)
        item_title.get_style_context().add_class("monitor-title")
        menu.append(item_title)

        menu.append(Gtk.SeparatorMenuItem())

        # 1. 动态生成 CPU 各核心负载信息
        cores = self.collector.get_per_cpu_percent()
        if cores:
            item_core_header = Gtk.MenuItem(label="【CPU 各核心负载】")
            item_core_header.set_sensitive(False)
            item_core_header.get_style_context().add_class("monitor-section")
            menu.append(item_core_header)

            # 将核心按 4 个一组切分行，便于整齐排版
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

        # 2. 预先构建 Top 5 高负载进程固定槽位（支持 3 秒无感就地刷新）
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

        # 立即填充一次初始数据
        self._update_menu_content()

        menu.append(Gtk.SeparatorMenuItem())

        # 3. 显卡硬件信息 (按需查询缓存)
        gpu = self.collector.get_gpu_info()
        if gpu and gpu.get("available"):
            gpu_text = f"【显卡】{gpu['name']} (显存: {gpu['vram']} | {gpu['clock']})"
            item_gpu = Gtk.MenuItem(label=gpu_text)
            item_gpu.set_sensitive(False)
            item_gpu.get_style_context().add_class("monitor-section")
            menu.append(item_gpu)
            menu.append(Gtk.SeparatorMenuItem())

        # 打开配置文件条目
        item_config = Gtk.MenuItem(label="打开配置文件")
        item_config.connect("activate", self._open_config)
        menu.append(item_config)

        # 关于条目
        item_about = Gtk.MenuItem(label="关于")
        item_about.connect("activate", self._show_about)
        menu.append(item_about)

        menu.append(Gtk.SeparatorMenuItem())

        # 退出应用条目
        item_quit = Gtk.MenuItem(label="退出监控")
        item_quit.connect("activate", lambda _: self.stop())
        menu.append(item_quit)

        menu.show_all()
        # 在鼠标点击的相对位置弹出菜单
        menu.popup_at_pointer(event)

        # 开启 3 秒动态局部刷新定时器，并记录起始时间戳
        self._menu_open_time = time.time()
        self._menu_timer_id = self._glib.timeout_add_seconds(3, self._menu_refresh_tick)

    def _on_button_press(self, widget, event):
        """鼠标按下事件回调: 左键记录拖拽起始点，右键弹出上下文菜单."""
        if event.button == 1:  # 鼠标左键：开启拖拽，记录起点及当前窗口坐标
            self._drag_data = (event.x_root, event.y_root, *self.window.get_position())
        elif event.button == 3:  # 鼠标右键：弹出设置与详情菜单
            self._show_context_menu(event)

    def _on_motion_notify(self, widget, event):
        """鼠标移动事件回调: 计算移动偏移量并平滑移动挂件窗口."""
        if self._drag_data:
            start_x, start_y, win_x, win_y = self._drag_data
            dx = int(event.x_root - start_x)
            dy = int(event.y_root - start_y)
            self.window.move(win_x + dx, win_y + dy)

    def _on_button_release(self, widget, event):
        """鼠标释放事件回调: 结束拖拽，并持久化保存用户移动后的新坐标."""
        if event.button == 1 and self._drag_data:
            self._drag_data = None
            new_x, new_y = self.window.get_position()
            # 保存到配置中，保证下次开机自启或重启应用时恢复该位置
            self.config.dock_x = new_x
            self.config.dock_y = new_y
            try:
                self.config.save()
            except Exception:
                pass

    def update_label(self, label: str) -> None:
        """更新挂件文本标签（含脏检查优化机制）.
        
        脏检查说明：如果格式化生成的文本与上一次完全相同，则跳过 GTK 的 set_text 调用，
        实现 0 次无效重绘，进一步节约 X11 服务端渲染负载。
        
        Args:
            label: 待显示的文本字符串。
        """
        # 脏检查：仅在文本发生实际改变时才触发 GTK 内部文本排版与重绘
        if self.label and label != self._last_text:
            self._last_text = label
            self.label.set_text(label)

    def _tick(self) -> bool:
        """主定时器循环回调函数.
        
        周期性拉取最新性能指标并更新主界面标签。
        
        Returns:
            bool: 返回 True 维持定时器周期触发，返回 False 退出。
        """
        if not self._is_running:
            return False
        # 采集性能指标
        metrics = self.collector.collect()
        try:
            label_text = self.config.format.format(**metrics)
        except Exception as e:
            label_text = f"Err: {e}"
        # 刷新标签
        self.update_label(label_text)
        return True

    def _position_window(self, Gdk):
        """计算并设置悬浮挂件在屏幕上的初始展示位置.
        
        定位逻辑：
        - 若用户曾手动拖拽过并保存了坐标 (dock_x >= 0, dock_y >= 0)，恢复持久化坐标；
        - 否则自动计算屏幕分辨率，吸附在主显示器右下角、任务栏上方 6px 处。
        """
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() if display else None
        if monitor:
            geom = monitor.get_geometry()
        else:
            screen = Gdk.Screen.get_default()
            p = screen.get_primary_monitor() if screen else 0
            geom = screen.get_monitor_geometry(p if p >= 0 else 0) if screen else type("Geom", (), {"x": 0, "y": 0, "width": 1920, "height": 1080})()
        
        # 获取窗口首选尺寸大小
        _, natural_req = self.window.get_preferred_size()
        w = max(260, natural_req.width)
        h = max(24, natural_req.height)

        if self.config.dock_x >= 0 and self.config.dock_y >= 0:
            # 恢复用户拖拽记忆的坐标
            self.window.move(self.config.dock_x, self.config.dock_y)
        else:
            # 智能默认值：停靠在右下角，避开 UKUI 任务栏高度（约 44px）
            x = geom.x + geom.width - w - 16
            y = geom.y + geom.height - 44 - h - 6
            self.window.move(max(0, x), max(0, y))

    def start(self) -> None:
        """初始化 GTK3 窗口组件、绑定系统事件并启动 GTK 主事件循环."""
        Gtk, Gdk, GLib = self._init_gtk()
        self._gtk = Gtk
        self._glib = GLib
        self._is_running = True

        # 加载注入 CSS 主题样式
        self._setup_css(Gtk, Gdk)

        # 1. 创建顶层窗口并配置 Dock 属性（纯实色 2D RGB，零合成器开销）
        self.window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self.window.set_name("kylin-dock-window")
        self.window.set_type_hint(Gdk.WindowTypeHint.DOCK)  # 声明为桌面 Dock 停靠挂件
        self.window.set_decorated(False)                    # 无系统标题栏边框
        self.window.set_keep_above(True)                     # 保持窗口最前端置顶
        self.window.set_skip_taskbar_hint(True)              # 避免在任务栏生成自身图标
        self.window.set_skip_pager_hint(True)                # 避免在桌面工作区切换器中显示
        self.window.set_accept_focus(False)                  # 不抢占键盘输入焦点
        self.window.set_title("KylinTaskbarMonitor")

        # 2. 创建承载监控指标文字的 Label 控件
        self.label = Gtk.Label(label=" 初始化监控中... ")
        self.label.set_name("kylin-dock-label")
        self.window.add(self.label)

        # 3. 注册鼠标交互事件（支持鼠标按下、释放以及光标移动拖拽）
        self.window.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK |
            Gdk.EventMask.BUTTON_RELEASE_MASK |
            Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.window.connect("button-press-event", self._on_button_press)
        self.window.connect("motion-notify-event", self._on_motion_notify)
        self.window.connect("button-release-event", self._on_button_release)

        # 4. 监听 POSIX 系统终止信号 (SIGINT / SIGTERM)，确保进程终止时正常退出
        try:
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self.stop)
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self.stop)
        except Exception:
            pass

        # 显示窗口并计算初次吸附停靠坐标
        self.window.show_all()
        self._position_window(Gdk)

        # 首次立即刷新一次界面
        self._tick()

        # 调度周期性刷新定时器
        # 优化说明：若为整数秒，使用 timeout_add_seconds 可让 GLib 合并对齐唤醒周期，大幅节约 CPU 唤醒能耗
        interval = self.config.interval
        if interval.is_integer() and interval >= 1.0:
            GLib.timeout_add_seconds(int(interval), self._tick)
        else:
            GLib.timeout_add(int(interval * 1000), self._tick)

        # 进入 GTK 主事件循环（阻塞）
        Gtk.main()

    def stop(self) -> None:
        """优雅退出 GTK 主循环并清理所有定时器."""
        self._is_running = False
        self._stop_menu_timer()
        if self._gtk:
            self._gtk.main_quit()

# 向后兼容别名
LinuxAppIndicator = LinuxDockIndicator

def create_indicator(config: MonitorConfig, collector: MetricsCollector, force_mock: bool = False) -> BaseIndicator:
    """根据运行操作系统与用户配置构造适宜的指示器实例（简单工厂方法）.
    
    选择策略：
    - 若传入 force_mock 为 True、或者操作系统为 macOS (darwin)、或者配置的 mode 为 "mock"，
      则实例化 MockIndicator（终端文本单行覆盖预览模式）；
    - 否则在 Linux 桌面环境下实例化原生的 LinuxDockIndicator（X11 Dock 原生悬浮挂件）。
    
    Args:
        config: 配置对象。
        collector: 性能指标采集器。
        force_mock: 是否强制启用终端模拟模式。
        
    Returns:
        BaseIndicator: 实例化的指示器对象。
    """
    if force_mock or sys.platform == "darwin" or getattr(config, "mode", "dock") == "mock":
        return MockIndicator(config, collector)
    return LinuxDockIndicator(config, collector)


