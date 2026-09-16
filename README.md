# Kylin Taskbar Monitor (信创银河麒麟极轻量任务栏监视器)

专为国产信创（银河麒麟 V10 SP1 / 统信 UOS / Linux）打造的**极轻量级、零负担**任务栏系统性能监视器。

---

## 🌟 核心特色
- **极致省能**：内存占用仅约 **9.8 MB**，CPU 活跃时间 **< 0.01%**，单次采样耗时仅 0.08 毫秒，专治兆芯/海光等低功耗信创整机。
- **原生融合**：利用系统原生 `AppIndicator / StatusNotifierItem` 规范，内嵌在下方任务栏右侧，绝不遮挡窗口。
- **1080P 125% 缩放适配**：全字段定宽防抖对齐，杜绝数字跳动造成的面板晃动与高 DPI 字体省略号截断。
- **防图标挤压**：动态计算最大安全 Guide 空间并预留呼吸边距，彻底避免挤压邻近的微信、钉钉或输入法图标。
- **Mac 友好开发**：内置 `--mock` 模拟模式，在 Mac 本机无需 Linux 图形环境即可开发与测试。
- **标准 Wheel 交付**：纯 Python Wheel，`pip` / `uv` 任意 Linux 设备一键安装。

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

## 📦 打包构建 (在 Mac 上)

```bash
python3 -m build --wheel
# 会在 dist/ 目录下生成平台通用的纯 Python Wheel：
# dist/kylin_taskbar_monitor-0.1.0-py3-none-any.whl
```

---

## 🚀 部署到信创系统 (银河麒麟 / 统信 UOS)

### 1. 准备依赖 (系统底层库)
```bash
sudo apt update && sudo apt install gir1.2-appindicator3-0.1 python3-psutil -y
```

### 2. 安装 (支持 GitHub 直装或 Wheel 安装)

**方式 A：直接通过 GitHub 一键安装**
```bash
pip install git+https://github.com/RichardHuang0001/kylin-taskbar-monitor.git
```

**方式 B：从 Mac 拷贝 Wheel 文件离线安装**
```bash
pip install kylin_taskbar_monitor-0.1.0-py3-none-any.whl
```

### 3. 启动与开机自启
```bash
# 一键注册开机自启 (自动写入 ~/.config/autostart/)
kylin-monitor --install

# 立即启动常驻后台 (屏幕右下角即可看到效果)
nohup kylin-monitor >/dev/null 2>&1 &
```

---

## ⚙️ 自定义配置
生成/修改配置文件：
```bash
kylin-monitor --init-config
# 配置文件位置: ~/.config/kylin-monitor/config.json
```
可自由调整刷新间隔、指定监控网卡（如 `eth0`）或自定义文字显示模板。

右键点击任务栏监控文字，亦可随时唤出菜单快速打开配置文件或退出。
