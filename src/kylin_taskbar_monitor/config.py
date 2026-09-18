"""配置管理模块 (Configuration Management).

负责监视器配置参数的加载、验证、类型转换以及持久化存储。
支持从 ~/.config/kylin-monitor/config.json 读取和写入配置，
具备字段过滤、异常容错降级及刷新间隔安全下限保护机制。
"""

import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Union

# 默认配置目录：遵循 XDG 规范，存储于用户主目录下的 .config/kylin-monitor/
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "kylin-monitor"

# 默认配置文件路径
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.json"

# 默认状态栏展示模板：包含 CPU 占用率、内存使用量、下行/上行网络速率
# 采用定宽格式化语法（如 {cpu:>2}%），防止数值位数变动导致界面文字横向抖动
DEFAULT_FORMAT = "CPU {cpu:>2}% | 内存 {mem_used_g:4.1f}G | ↓{down_speed} | ↑{up_speed}"


@dataclass
class MonitorConfig:
    """性能监视器核心配置数据类.
    
    Attributes:
        interval: 采样与界面刷新时间间隔（单位：秒，最小安全值为 0.5s，默认 2.0s）。
        format: 任务栏显示格式模板字符串，支持多种指标占位符。
        net_interface: 监听的网络接口名称，"auto" 为自动合并所有物理网卡流量。
        icon: 桌面系统托盘图标名称。
        show_icon: 是否显示托盘图标。
        dock_x: 悬浮挂件在屏幕上的横坐标（-1 表示自动吸附在屏幕右下角）。
        dock_y: 悬浮挂件在屏幕上的纵坐标（-1 表示自动吸附在任务栏上方）。
        mode: 运行模式，可选 "dock"（Linux 原生桌面挂件）或 "mock"（终端文本预览）。
    """
    interval: float = 2.0
    format: str = DEFAULT_FORMAT
    net_interface: str = "auto"
    icon: str = "utilities-system-monitor"
    show_icon: bool = True
    dock_x: int = -1
    dock_y: int = -1
    mode: str = "dock"

    @classmethod
    def load(cls, path: Union[str, Path] = DEFAULT_CONFIG_PATH, auto_create: bool = False) -> "MonitorConfig":
        """从指定 JSON 文件加载配置.
        
        若文件存在，则解析并清洗字段，自动忽略未知键和注释键；
        若文件不存在或读取损坏，则优雅降级返回默认配置对象。
        
        Args:
            path: 配置文件路径，支持字符串或 Path 对象，默认使用 DEFAULT_CONFIG_PATH。
            auto_create: 当配置文件不存在时，是否自动创建并写入一份默认配置文件。
            
        Returns:
            MonitorConfig: 实例化后的配置对象。
        """
        # 展开 ~ 用户路径并获取绝对规范路径
        config_path = Path(path).expanduser().resolve()
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # 仅保留数据类已声明的字段，过滤以下划线开头的注释字段或未知参数
                valid_data = {
                    k: v for k, v in data.items() 
                    if k in cls.__annotations__ and not k.startswith("_")
                }
                # 刷新间隔下限安全保护：避免采样间隔设置过低导致信创低算力 CPU 负载过高
                if "interval" in valid_data:
                    valid_data["interval"] = max(0.5, float(valid_data["interval"]))
                return cls(**valid_data)
            except Exception as e:
                # 发生 JSON 解析异常或读取错误时打印警告并回退至默认配置
                print(f"[Warn] 加载配置文件失败，将使用默认配置: {e}")
                return cls()
        
        # 配置文件不存在时创建默认配置
        cfg = cls()
        if auto_create:
            try:
                cfg.save(config_path)
            except Exception as e:
                print(f"[Warn] 自动生成配置文件失败: {e}")
        return cfg

    def save(self, path: Union[str, Path] = DEFAULT_CONFIG_PATH) -> None:
        """将当前配置序列化保存为 JSON 文件.
        
        写入时会自动包含注释说明字段，方便用户直接在文本编辑器中查阅占位符使用方法。
        
        Args:
            path: 目标保存路径，若父级目录不存在将自动级联创建。
        """
        config_path = Path(path).expanduser().resolve()
        # 确保父级目录已存在
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 构建带注释与占位符帮助信息的 JSON 载荷
        payload = {
            "_comment": "信创极轻量任务栏性能监视器配置文件",
            "_fields_help": "可用占位符: {cpu}, {cpu_float}, {mem_used_g}, {mem_total_g}, {mem_percent}, {down_speed}, {up_speed}",
            "interval": self.interval,
            "format": self.format,
            "net_interface": self.net_interface,
            "icon": self.icon,
            "show_icon": self.show_icon,
            "dock_x": self.dock_x,
            "dock_y": self.dock_y,
            "mode": self.mode
        }
        # 以 UTF-8 编码美化输出 JSON 文件
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

