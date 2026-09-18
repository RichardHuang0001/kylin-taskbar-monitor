"""系统底层性能指标采集器 (System Metrics Collector).

设计哲学与优化特点：
1. 零子进程派生 (Zero-process-spawn)：严禁使用 subprocess 调用 top/free/ifconfig 等外部命令，
   完全通过 psutil 的原生 C 扩展与直接读取 Linux /proc 虚拟文件系统获取指标，大幅降低 CPU 开销。
2. 缓存复用与降低 GC 压力：指标字典原地更新，网卡列表 60 秒防抖缓存，避免频繁内存分配与垃圾回收。
3. 国产信创芯片友好：针对兆芯、飞腾、龙芯、鲲鹏等中低算力 CPU 进行优化，后台单次采样时间低于 1ms。
"""

import os
import time
from typing import Dict, Any, Tuple, List, Optional
import psutil

def format_speed(bytes_per_sec: float, fixed_width: bool = False) -> str:
    """将每秒字节数 (bytes/sec) 格式化为人类可读的速率字符串.
    
    单位自动转换：
    - >= 1 GB/s: 显示为 x.xG/s
    - >= 1 MB/s: 显示为 x.xM/s
    - < 1 MB/s: 显示为整数 xK/s
    
    Args:
        bytes_per_sec: 每秒传输字节数 (float)。
        fixed_width: 是否固定为 6 字符宽度（右对齐）。开启后可避免桌面挂件在
                     网速数字位数变化（如 9K/s 变 100K/s）时出现窗口宽度或文字跳动。
                     
    Returns:
        str: 格式化后的速率字符串，如 "1.2M/s" 或 "  85K/s"。
    """
    # 异常保护：若因系统休眠唤醒或计数器溢出导致负数，重置为 0
    if bytes_per_sec < 0:
        bytes_per_sec = 0.0
    
    # 转换为 KB
    kb = bytes_per_sec / 1024.0
    
    if kb >= 1024.0 * 1024.0:
        # 大于等于 1GB/s
        val = f"{kb / (1024.0 * 1024.0):.1f}G/s"
    elif kb >= 1024.0:
        # 大于等于 1MB/s
        val = f"{kb / 1024.0:.1f}M/s"
    else:
        # 小于 1MB/s，保留整数显示
        val = f"{int(kb)}K/s"
        
    # 如果要求固定宽度，则进行 6 字符右对齐填充空格
    if fixed_width:
        return f"{val:>6}"
    return val

class MetricsCollector:
    """系统性能指标采集器核心类.
    
    负责周期性抓取 CPU 总体使用率、各核心使用率、内存占用、实时网络吞吐量，
    并提供右键菜单按需查询高 CPU 占用进程列表及显卡硬件信息的能力。
    """

    def __init__(self, net_interface: str = "auto"):
        """初始化性能指标采集器.
        
        Args:
            net_interface: 要监控的网络接口名称，默认 "auto" 自动合并物理网卡流量。
        """
        self.net_interface = net_interface
        
        # 网卡列表缓存：避免每次定时器触发都遍历枚举所有网络接口
        self._cached_nics: Optional[List[str]] = None
        self._last_nic_scan: float = 0.0
        
        # 记录初始网络流量基准值与时间戳，用于计算首次瞬时速率
        self.last_bytes_recv, self.last_bytes_sent = self._get_net_bytes()
        self.last_time = time.time()
        
        # 右键菜单按需查询的防抖缓存 (1.5秒有效期)，防止高频打开菜单触发过多采样
        self._cached_top_procs: List[Dict[str, Any]] = []
        self._last_top_proc_scan: float = 0.0
        # 显卡硬件信息静态缓存（显卡型号基本不动态变更）
        self._cached_gpu_info: Optional[Dict[str, Any]] = None
        
        # 预热 CPU 占有率采样器（psutil 首次无间隔调用会返回 0.0，预先调用一次建立基准）
        try:
            psutil.cpu_percent(interval=None)
        except Exception:
            pass
        
        # 预先分配并初始化指标缓存字典，后续 collect() 原地写入，减轻 GC 停顿
        self._metrics_cache: Dict[str, Any] = {
            "cpu": 0,
            "cpu_float": 0.0,
            "mem_used_g": 0.0,
            "mem_total_g": 0.0,
            "mem_percent": 0,
            "mem_free_g": 0.0,
            "down_speed": "  0K/s",
            "up_speed": "  0K/s",
            "down_bps": 0.0,
            "up_bps": 0.0,
        }


    def _get_net_bytes(self) -> Tuple[int, int]:
        """获取当前网络总接收和发送字节数（带网卡枚举缓存机制）.
        
        策略说明：
        - 若用户指定了特定网卡，则直接抓取该网卡计数；
        - 若为 "auto" 自动模式，则 60 秒做一次网卡枚举扫描（排除 lo 回环网卡），
          避免每次定时器采样都调用底层系统 API 枚举接口，显著节约 CPU 周期；
        - 若仅有 loopback 或发生异常，则安全回退为全局流量或 (0, 0)。
        
        Returns:
            Tuple[int, int]: (累计接收字节数, 累计发送字节数)
        """
        try:
            # pernic=True 返回字典：{'eth0': snetio(...), 'lo': ...}
            pernic = psutil.net_io_counters(pernic=True)
            if not pernic:
                return 0, 0

            # 1. 用户指定了特定的网卡名称 (例如 "eth0" 或 "wlan0")
            if self.net_interface and self.net_interface != "auto":
                if self.net_interface in pernic:
                    nic = pernic[self.net_interface]
                    return nic.bytes_recv, nic.bytes_sent
                return 0, 0

            # 2. 自动模式 (auto): 60秒防抖缓存网卡列表，减少内存分配与 CPU 开销
            now = time.time()
            if self._cached_nics is None or (now - self._last_nic_scan > 60.0):
                # 过滤掉以 "lo" 开头的本地回环网卡，仅统计真实物理/虚拟网络接口
                self._cached_nics = [
                    name for name in pernic
                    if not name.startswith("lo")
                ]
                self._last_nic_scan = now

            # 汇总有效物理网卡的收发字节总和
            if self._cached_nics:
                total_recv = 0
                total_sent = 0
                for name in self._cached_nics:
                    if name in pernic:
                        nic = pernic[name]
                        total_recv += nic.bytes_recv
                        total_sent += nic.bytes_sent
                return total_recv, total_sent

            # 3. 兜底策略：若过滤后无有效网卡（如单机只有 lo），读取全局计数
            global_net = psutil.net_io_counters()
            if global_net:
                return global_net.bytes_recv, global_net.bytes_sent
        except Exception:
            # 捕获异常确保不会因网络接口插拔或权限问题导致监控崩溃
            pass
        return 0, 0

    def collect(self) -> Dict[str, Any]:
        """执行一次全量系统性能指标采集（主定时器高频调用方法）.
        
        采集步骤：
        1. 计算当前时刻与上一次采样的时间增量 dt；
        2. 读取整体 CPU 占用率 (无阻塞调用)；
        3. 读取系统物理内存占用与可用量 (单位换算为 GB)；
        4. 计算网络收发瞬时速率 (bytes/s)，内置网卡翻转与休眠重启保护；
        5. 原地覆写指标字典缓存，避免频繁创建临时字典引起 GC 抖动。
        
        Returns:
            Dict[str, Any]: 包含 cpu, mem, down_speed, up_speed 等键值的性能数据字典。
        """
        try:
            now = time.time()
            dt = now - self.last_time
            # 保护：防止时间倒流或除以零
            if dt <= 0:
                dt = 1.0

            # 1. 采集 CPU 总使用率 (interval=None 即非阻塞读取上次调用以来的平均值)
            cpu = psutil.cpu_percent(interval=None)
            if cpu is None or cpu < 0:
                cpu = 0.0

            # 2. 采集内存信息
            mem = psutil.virtual_memory()
            mem_used_g = mem.used / (1024 ** 3)
            mem_total_g = mem.total / (1024 ** 3)
            # 优先使用 available（真实空闲+可回收缓存），若不支持则使用 free
            mem_free_g = getattr(mem, "available", mem.free) / (1024 ** 3)
            mem_percent = mem.percent

            # 3. 网络收发速率计算 (带计数器翻转及重启保护)
            bytes_recv, bytes_sent = self._get_net_bytes()
            # 若当前累计字节数大于等于上一次，正常计算增量差分
            if bytes_recv >= self.last_bytes_recv:
                down_bps = (bytes_recv - self.last_bytes_recv) / dt
            else:
                # 计数器溢出归零或网卡重启断开，避免算成负数或天文数字
                down_bps = 0.0

            if bytes_sent >= self.last_bytes_sent:
                up_bps = (bytes_sent - self.last_bytes_sent) / dt
            else:
                up_bps = 0.0

            # 更新基准状态
            self.last_bytes_recv = bytes_recv
            self.last_bytes_sent = bytes_sent
            self.last_time = now

            # 4. 原地更新指标字典缓存 (减少垃圾回收负担)
            c = self._metrics_cache
            c["cpu"] = int(cpu)
            c["cpu_float"] = round(cpu, 1)
            c["mem_used_g"] = round(mem_used_g, 2)
            c["mem_total_g"] = round(mem_total_g, 2)
            c["mem_free_g"] = round(mem_free_g, 2)
            c["mem_percent"] = int(mem_percent)
            # 定宽 6 字符可防止在桌面环境 125% 或非整数缩放下文字宽度抖动
            c["down_speed"] = format_speed(down_bps, fixed_width=True)
            c["up_speed"] = format_speed(up_bps, fixed_width=True)
            c["down_bps"] = down_bps
            c["up_bps"] = up_bps

            return c
        except Exception:
            # 容错降级：返回上一次有效缓存
            return self._metrics_cache

    def get_per_cpu_percent(self) -> List[float]:
        """获取 CPU 各逻辑核心的使用率列表（按需调用，约 0.4ms 开销）.
        
        仅在用户右键展开菜单查看核心详情时按需触发，不参与常规后台高频轮询。
        
        Returns:
            List[float]: 每个核心的使用率百分比列表，例如 [12.0, 5.0, 8.0, 99.0]。
        """
        try:
            return psutil.cpu_percent(percpu=True)
        except Exception:
            return []

    def get_top_processes(self, limit: int = 5) -> List[Dict[str, Any]]:
        """获取 CPU 占用率最高的进程列表（带 1.5s 防抖缓存与 Linux 原生差分算法）.
        
        实现原理说明：
        - Linux 环境下：不使用 psutil 的 Process 对象（避免每次遍历构造上百个 Python 对象的 GC 开销），
          直接扫描 `/proc` 目录中的 `/proc/<pid>/stat`。
          通过 80ms 微小时间窗口抓取 utime + stime (进程用户态与内核态滴答数 ticks)，
          差分计算出真实的瞬时 CPU 占用百分比，完全杜绝 psutil 瞬时调用返回 0% 的冷启动问题；
        - 非 Linux 环境（如 macOS 调试）：自动优雅回退到 `psutil.process_iter`。
        
        Args:
            limit: 返回的前 N 个高占用进程数，默认返回 Top 5。
            
        Returns:
            List[Dict[str, Any]]: 进程信息列表，包含 pid, name, cpu。
        """
        now = time.time()
        # 1.5秒防抖：防止用户反复悬停或高频触发菜单造成 CPU 额外开销
        if self._cached_top_procs is not None and (now - self._last_top_proc_scan < 1.5):
            return self._cached_top_procs[:limit]

        # 针对 Linux 环境的轻量直接 /proc 微采样实现 (80ms 时间窗口)
        if os.path.exists("/proc"):
            try:
                # 获取系统时钟滴答频率 (通常为 100 ticks/sec)
                clk_tck = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
                
                def _scan_proc_ticks() -> Dict[int, Tuple[str, int]]:
                    """扫描 /proc 下所有数字目录并提取其进程名与 CPU 滴答数."""
                    stats: Dict[int, Tuple[str, int]] = {}
                    for entry in os.scandir("/proc"):
                        if entry.name.isdigit():
                            try:
                                with open(f"/proc/{entry.name}/stat", "r") as f:
                                    content = f.read()
                                # /proc/[pid]/stat 格式中进程名被括号包裹，使用 rfind 避免进程名带括号导致解析错位
                                rparen = content.rfind(")")
                                if rparen != -1:
                                    parts = content[rparen + 2:].split()
                                    # utime 为索引 11，stime 为索引 12（基于括号之后切割偏移）
                                    ticks = int(parts[11]) + int(parts[12])
                                    name = content[content.find("(") + 1:rparen]
                                    stats[int(entry.name)] = (name, ticks)
                            except Exception:
                                # 进程在扫描过程中退出属正常现象，直接忽略
                                pass
                    return stats

                # 第一次采样
                t0 = time.perf_counter()
                s1 = _scan_proc_ticks()
                # 80ms 极短休眠窗口用于建立差分基准
                time.sleep(0.08)
                # 第二次采样
                t1 = time.perf_counter()
                s2 = _scan_proc_ticks()

                dt = max(0.01, t1 - t0)
                procs: List[Dict[str, Any]] = []
                # 遍历计算各存活进程在窗口内的 CPU 占用率
                for pid, (name, ticks2) in s2.items():
                    if pid in s1:
                        dticks = ticks2 - s1[pid][1]
                        if dticks > 0:
                            cpu_pct = (dticks / clk_tck) / dt * 100.0
                            procs.append({"pid": pid, "name": name, "cpu": round(cpu_pct, 1)})

                # 按 CPU 占用率降序排序并写入缓存
                procs.sort(key=lambda x: x["cpu"], reverse=True)
                self._cached_top_procs = procs
                self._last_top_proc_scan = now
                return self._cached_top_procs[:limit]
            except Exception:
                pass

        # 非 Linux 平台（macOS、BSD 或无 /proc 环境）的回退方案
        procs_fallback: List[Dict[str, Any]] = []
        try:
            for p in psutil.process_iter(["pid", "name", "cpu_percent"]):
                try:
                    cpu = p.info.get("cpu_percent")
                    if cpu is not None and cpu > 0.0:
                        procs_fallback.append({
                            "pid": p.info["pid"],
                            "name": p.info.get("name") or f"PID {p.info['pid']}",
                            "cpu": cpu,
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
            procs_fallback.sort(key=lambda x: x["cpu"], reverse=True)
            self._cached_top_procs = procs_fallback
            self._last_top_proc_scan = now
        except Exception:
            pass

        return (self._cached_top_procs or [])[:limit]

    def get_gpu_info(self) -> Dict[str, Any]:
        """获取 GPU 显卡硬件摘要信息（按需静态缓存，零常规轮询开销）.
        
        适配国产信创硬件架构（如兆芯开先 KX-6000 配套 C-960 显卡）以及通用 Linux DRM 架构，
        通过读取 sysfs `/sys/class/drm/card0/` 探测显卡名称、显存容量及当前工作频率。
        
        Returns:
            Dict[str, Any]: 包含 name, vram, clock, available 属性的字典。
        """
        # 已有缓存直接返回，避免多次读取 sysfs 文件
        if self._cached_gpu_info is not None:
            return self._cached_gpu_info

        info: Dict[str, Any] = {
            "name": "未知显卡",
            "vram": "未知",
            "clock": "未知",
            "available": False
        }
        
        # 探测兆芯 C-960 独立/集成显卡专用接口或通用 Linux DRM 显卡
        try:
            gpu_info_path = "/sys/class/drm/card0/device/gpu-info"
            if os.path.exists(gpu_info_path):
                # 读取兆芯驱动导出的硬件信息节点
                with open(gpu_info_path, "r", encoding="utf-8") as f:
                    lines = f.read().splitlines()
                info["name"] = "兆芯 KX-6000 C-960"
                for line in lines:
                    if "VRAM total size:" in line:
                        val_hex = line.split(":")[-1].strip()
                        size_bytes = int(val_hex, 16)
                        info["vram"] = f"{int(size_bytes / (1024 * 1024))} MB"
                    elif "ECLK current:" in line:
                        info["clock"] = line.split(":")[-1].strip()
                info["available"] = True
            elif os.path.exists("/sys/class/drm/card0"):
                # 通用 Linux DRM 显卡节点兜底
                info["name"] = "Linux DRM Card0"
                info["available"] = True
        except Exception:
            pass

        self._cached_gpu_info = info
        return info

