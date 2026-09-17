# Kylin Taskbar Monitor (信创银河麒麟极轻量性能监视器)

专为国产信创系统（银河麒麟 V10 SP1 / 统信 UOS / Linux）打造的**极轻量级、零负担、极低功耗**桌面性能监视器。针对兆芯、海光、飞腾等单核性能偏弱或集成无硬解加速显卡的硬件环境进行了极端工程优化。

---

## 🌟 核心特色 (v0.2.5 高能效架构)

- **零混成器负担 (Zero-Composite Overhead)**：采用 Solid 2D RGB 直写渲染，杜绝 Alpha 半透明图层混合，完全不占用 CPU 软算力计算阴影与透明度。
- **内存脏检查 (Dirty Check)**：平时仅在数值变动时重绘 GTK 标签，稳态 CPU 占用常驻 **0.00%**，内存控制在 **50 MB** 以内。
- **右键按需动态探针**：
  - **CPU 各核心 (Per-Core) 负载**：单核过载瓶颈一览无余；
  - **高负载进程 Top 5**：大字号（16px）、极深高对比度墨黑排版，清楚标明进程名称、PID 与瞬时占用；
  - **信创显卡状态**：识别兆芯 C-960 等国产显存与运行主频；
  - **3秒平滑原地刷新**：槽位原地更新（In-place Label Update），界面丝滑、绝无闪烁、不丢失焦点；
  - **多重退出与 30 秒硬熔断机制**：关闭菜单瞬间销毁定时器并完全释放资源；若菜单长开超过 30 秒自动硬熔断定格，绝不长期空耗算力。
- **智能吸附与拖拽记忆**：默认精确停靠在任务栏上方，按住鼠标左键可随意拖动至屏幕任意位置，松开即刻记忆坐标。
- **1080P 125% 缩放适配**：全字段定宽防抖对齐，杜绝数字变动造成的界面跳动与高分屏字体截断。

---

## 🚀 快速下载与一键部署

### 1. 准备基础系统依赖 (信创/Ubuntu 系统通常已自带)
```bash
sudo apt update && sudo apt install gir1.2-gtk-3.0 python3-psutil -y
```

### 2. 通过命令一键下载安装 / 升级
通过官方 GitHub 仓库直接安装最新发布版：
```bash
pip install --upgrade git+https://github.com/RichardHuang0001/kylin-taskbar-monitor.git
```
*(如果是网络受限环境，也可克隆源码后在目录中执行 `pip install .`)*

### 3. 一键配置开机自启与立即启动
```bash
# 1. 注册开机自启 (自动写入标准 XDG Autostart 规范)
kylin-monitor --install

# 2. 立即在后台静默启动
nohup kylin-monitor >/dev/null 2>&1 &
```
> 启动后，您将在桌面右下角任务栏正上方看到小巧精致的监控条！

---

## 🛡️ 长期稳定运行指南

- **开机自启动机制**：
  `kylin-monitor --install` 会在用户的 `~/.config/autostart/kylin-taskbar-monitor.desktop` 生成自启动桌面项，用户每次登录系统时由桌面环境无感知拉起，**无需 root 提权，安全稳定**。
- **查看运行状态**：
  ```bash
  kylin-monitor --status
  # 或者通过系统进程命令检查
  ps aux | grep kylin-monitor | grep -v grep
  ```
- **配置文件管理**：
  配置文件位于 `~/.config/kylin-monitor/config.json`，可随时通过右键菜单直接打开，或执行：
  ```bash
  kylin-monitor --init-config
  ```

---

## 🧹 干净退出与彻底卸载

如果您因故不需要使用该小工具，请按照以下方式操作。本工具遵循“绿色纯净”原则，所有退出和卸载操作均保证**零僵尸进程、零残留垃圾文件**：

### 1. 临时退出当前监控
- **方式一（图形化）**：直接在监控条上点击鼠标右键，在菜单最底部点击 **「退出监控」** 即可干净退出；
- **方式二（命令行）**：
  ```bash
  killall kylin-monitor
  # 或
  pkill -f kylin-monitor
  ```

### 2. 仅关闭开机自启（保留程序）
```bash
kylin-monitor --uninstall
```

### 3. 完全卸载并抹除所有配置（彻底清空）
```bash
# 步骤 1：终止正在运行的监控进程
killall kylin-monitor 2>/dev/null

# 步骤 2：彻底移除开机自启动配置
kylin-monitor --uninstall 2>/dev/null

# 步骤 3：使用 pip 卸载本体
pip uninstall kylin-taskbar-monitor -y

# 步骤 4：清理本地配置文件与缓存（可选）
rm -rf ~/.config/kylin-monitor
```

---

## ⚙️ 交互说明与快捷手势

| 交互操作 | 效果说明 |
| :--- | :--- |
| **鼠标左键按住拖动** | 可拖拽至屏幕任意位置（如副屏或右上角），松开自动持久化记忆坐标 |
| **鼠标右键点击** | 唤出高性能探针菜单（查看各核心负载、Top 5 高占用进程、显卡信息） |
| **右键菜单展示时** | 每 3 秒平滑动态更新一次当前负载，关闭菜单立即回归 0.00% 极低功耗；长开达 30 秒自动硬熔断保护 |
| **鼠标点击空白处 / Esc** | 立即关闭右键探针菜单并销毁全部临时对象 |
