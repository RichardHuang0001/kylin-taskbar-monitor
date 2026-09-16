# Kylin Taskbar Monitor (信创银河麒麟极轻量性能监视器)

专为国产信创（银河麒麟 V10 SP1 / 统信 UOS / Linux）打造的**极轻量级、零负担、极低功耗**桌面性能监视器。针对十几年前弱单核与集成无硬解显卡（兆芯/海光老款芯片）进行极端性能优化。

---

## 🌟 核心特色 (v0.2.0 高能效架构)
- **零混成器负担 (Zero-Composite Overhead)**：采用 Solid 2D RGB 哑光深色直写渲染，杜绝 Alpha 半透明软件混合，完全不占用 CPU 进行图层计算。
- **内存脏检查 (Dirty Check)**：仅在指标数值变动时才刷新 GTK 标签，空闲时 CPU 唤醒耗时低于 **0.01 毫秒**。
- **智能吸附与拖拽记忆**：默认自动精确定位在银河麒麟右下角任务栏托盘正上方，鼠标左键按住可任意拖拽，松开自动保存位置。
- **1080P 125% 缩放适配**：全字段定宽防抖对齐，杜绝数字跳动造成的晃动与高 DPI 字体省略号截断。
- **免遮挡、不占焦点**：`WindowTypeHint.DOCK` 声明，`keep_above=True` 始终置顶，窗口管理器零事件轮询负担。
- **极小资源开销**：单进程内存仅约 **9.8 MB**，CPU 活跃时间 **< 0.01%**。

---

## 🛠️ 本地开发与调试 (在 Mac 上)

```bash
# 1. 安装依赖
pip install psutil pytest build

# 2. 运行自动化单元测试
pytest tests/

# 3. 运行本地 Mock 预览 (在 Mac 终端直接看定宽防抖效果)
PYTHONPATH=src python3 -m kylin_taskbar_monitor.cli --mock
```

---

## 🚀 部署到信创系统 (银河麒麟 / 统信 UOS)

### 1. 准备基础库 (信创系统通常已自带)
```bash
sudo apt update && sudo apt install gir1.2-gtk-3.0 python3-psutil -y
```

### 2. 通过 GitHub 一键安装 / 升级
```bash
pip install --upgrade git+https://github.com/RichardHuang0001/kylin-taskbar-monitor.git
```

### 3. 立即启动与开机自启
```bash
# 一键注册开机自启 (自动写入 ~/.config/autostart/)
kylin-monitor --install

# 立即启动常驻后台 (屏幕右下角即可看到效果)
nohup kylin-monitor >/dev/null 2>&1 &
```

---

## ⚙️ 交互与快捷管理

- **鼠标拖拽**：鼠标左键按住监控条即可随意拖动到桌面任意位置（如右上角或任务栏上方），松开自动记录坐标。
- **右键菜单**：右键点击监控条唤出原生菜单（打开配置文件、关于、退出监控）。
- **命令行配置**：
  ```bash
  # 生成/检查配置文件 (位于 ~/.config/kylin-monitor/config.json)
  kylin-monitor --init-config
  kylin-monitor --status
  ```

