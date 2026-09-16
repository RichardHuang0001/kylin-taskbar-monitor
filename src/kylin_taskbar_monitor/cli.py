"""Command line interface entrypoint."""

import argparse
import sys
from typing import List, Optional
from . import __version__
from .config import MonitorConfig, DEFAULT_CONFIG_PATH
from .collector import MetricsCollector
from .indicator import create_indicator
from .installer import install_autostart, uninstall_autostart, status_autostart

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="kylin-monitor",
        description="信创银河麒麟极轻量任务栏性能监视器"
    )
    parser.add_argument(
        "-v", "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "-c", "--config", type=str, default=None,
        help=f"指定配置文件路径 (默认: {DEFAULT_CONFIG_PATH})"
    )
    parser.add_argument(
        "--mock", action="store_true",
        help="强制在终端中以 Mock 模式运行预览 (Mac本地调试用)"
    )
    parser.add_argument(
        "--interval", type=float, default=None,
        help="刷新间隔秒数 (默认: 2.0)"
    )
    parser.add_argument(
        "--format", type=str, default=None,
        help="自定义显示模板格式"
    )
    parser.add_argument(
        "--net-interface", type=str, default=None,
        help="指定监控网卡 (默认: auto)"
    )
    parser.add_argument(
        "--install", action="store_true",
        help="注册为开机自启动应用"
    )
    parser.add_argument(
        "--uninstall", action="store_true",
        help="移除开机自启动配置"
    )
    parser.add_argument(
        "--status", action="store_true",
        help="查看开机自启状态与配置路径"
    )
    parser.add_argument(
        "--dock-x", type=int, default=None,
        help="悬浮挂件 X 坐标 (-1 表示自动吸附右下角)"
    )
    parser.add_argument(
        "--dock-y", type=int, default=None,
        help="悬浮挂件 Y 坐标 (-1 表示自动吸附任务栏上方)"
    )
    parser.add_argument(
        "--mode", type=str, choices=["dock", "mock"], default=None,
        help="运行模式: dock (原生任务栏挂件), mock (终端文字预览)"
    )
    parser.add_argument(
        "--init-config", action="store_true",
        help="生成默认带注释配置文件"
    )

    args = parser.parse_args(argv)

    if args.install:
        install_autostart()
        return 0

    if args.uninstall:
        uninstall_autostart()
        return 0

    if args.status:
        is_installed = status_autostart()
        print(f"📊 开机自启状态: {'已启用' if is_installed else '未启用'}")
        config_file = args.config or DEFAULT_CONFIG_PATH
        print(f"📁 配置文件位置: {config_file}")
        return 0

    config_path = args.config or DEFAULT_CONFIG_PATH
    config = MonitorConfig.load(config_path)

    if args.init_config:
        config.save(config_path)
        print(f"✅ 默认配置文件已生成于: {config_path}")
        return 0

    if args.interval is not None:
        config.interval = max(0.5, args.interval)
    if args.format is not None:
        config.format = args.format
    if args.net_interface is not None:
        config.net_interface = args.net_interface
    if args.dock_x is not None:
        config.dock_x = args.dock_x
    if args.dock_y is not None:
        config.dock_y = args.dock_y
    if args.mode is not None:
        config.mode = args.mode

    collector = MetricsCollector(net_interface=config.net_interface)
    indicator = create_indicator(config, collector, force_mock=args.mock)
    try:
        indicator.run()
    except KeyboardInterrupt:
        pass
    return 0

if __name__ == "__main__":
    sys.exit(main())
