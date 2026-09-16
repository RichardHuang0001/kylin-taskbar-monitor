"""Configuration management for Kylin Taskbar Monitor."""

import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Union

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "kylin-monitor"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.json"

DEFAULT_FORMAT = "CPU {cpu:>2}% | 内存 {mem_used_g:4.1f}G | ↓{down_speed} | ↑{up_speed}"


@dataclass
class MonitorConfig:
    interval: float = 2.0
    format: str = DEFAULT_FORMAT
    net_interface: str = "auto"
    icon: str = "utilities-system-monitor"
    show_icon: bool = False

    @classmethod
    def load(cls, path: Union[str, Path] = DEFAULT_CONFIG_PATH, auto_create: bool = False) -> "MonitorConfig":
        config_path = Path(path).expanduser().resolve()
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                valid_data = {
                    k: v for k, v in data.items() 
                    if k in cls.__annotations__ and not k.startswith("_")
                }
                if "interval" in valid_data:
                    valid_data["interval"] = max(0.5, float(valid_data["interval"]))
                return cls(**valid_data)
            except Exception as e:
                print(f"[Warn] 加载配置文件失败，将使用默认配置: {e}")
                return cls()
        
        cfg = cls()
        if auto_create:
            try:
                cfg.save(config_path)
            except Exception as e:
                print(f"[Warn] 自动生成配置文件失败: {e}")
        return cfg

    def save(self, path: Union[str, Path] = DEFAULT_CONFIG_PATH) -> None:
        config_path = Path(path).expanduser().resolve()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        payload = {
            "_comment": "信创极轻量任务栏性能监视器配置文件",
            "_fields_help": "可用占位符: {cpu}, {cpu_float}, {mem_used_g}, {mem_total_g}, {mem_percent}, {down_speed}, {up_speed}",
            "interval": self.interval,
            "format": self.format,
            "net_interface": self.net_interface,
            "icon": self.icon,
            "show_icon": self.show_icon
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
