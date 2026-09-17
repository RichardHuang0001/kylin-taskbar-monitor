"""System metrics collector using psutil (zero-process-spawn /proc reader)."""

import os
import time
from typing import Dict, Any, Tuple, List, Optional
import psutil

def format_speed(bytes_per_sec: float, fixed_width: bool = False) -> str:
    """Format speed in bytes/sec to human readable string."""
    if bytes_per_sec < 0:
        bytes_per_sec = 0.0
    kb = bytes_per_sec / 1024.0
    if kb >= 1024.0 * 1024.0:
        val = f"{kb / (1024.0 * 1024.0):.1f}G/s"
    elif kb >= 1024.0:
        val = f"{kb / 1024.0:.1f}M/s"
    else:
        val = f"{int(kb)}K/s"
    if fixed_width:
        return f"{val:>6}"
    return val

class MetricsCollector:
    def __init__(self, net_interface: str = "auto"):
        self.net_interface = net_interface
        self._cached_nics: Optional[List[str]] = None
        self._last_nic_scan: float = 0.0
        self.last_bytes_recv, self.last_bytes_sent = self._get_net_bytes()
        self.last_time = time.time()
        
        # Debounce cache for on-demand top processes & per-core stats
        self._cached_top_procs: List[Dict[str, Any]] = []
        self._last_top_proc_scan: float = 0.0
        self._cached_gpu_info: Optional[Dict[str, Any]] = None
        
        # Prime the CPU percentage reader
        try:
            psutil.cpu_percent(interval=None)
        except Exception:
            pass
        
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
        """Fetch current total bytes_recv and bytes_sent with NIC discovery caching."""
        try:
            pernic = psutil.net_io_counters(pernic=True)
            if not pernic:
                return 0, 0

            # Specified interface
            if self.net_interface and self.net_interface != "auto":
                if self.net_interface in pernic:
                    nic = pernic[self.net_interface]
                    return nic.bytes_recv, nic.bytes_sent
                return 0, 0

            # Auto mode with 60s lazy NIC scan caching (reduces allocation & CPU cycles)
            now = time.time()
            if self._cached_nics is None or (now - self._last_nic_scan > 60.0):
                self._cached_nics = [
                    name for name in pernic
                    if not name.startswith("lo")
                ]
                self._last_nic_scan = now

            if self._cached_nics:
                total_recv = 0
                total_sent = 0
                for name in self._cached_nics:
                    if name in pernic:
                        nic = pernic[name]
                        total_recv += nic.bytes_recv
                        total_sent += nic.bytes_sent
                return total_recv, total_sent

            # Fallback if only loopback exists
            global_net = psutil.net_io_counters()
            if global_net:
                return global_net.bytes_recv, global_net.bytes_sent
        except Exception:
            pass
        return 0, 0

    def collect(self) -> Dict[str, Any]:
        try:
            now = time.time()
            dt = now - self.last_time
            if dt <= 0:
                dt = 1.0

            # CPU
            cpu = psutil.cpu_percent(interval=None)
            if cpu is None or cpu < 0:
                cpu = 0.0

            # Memory
            mem = psutil.virtual_memory()
            mem_used_g = mem.used / (1024 ** 3)
            mem_total_g = mem.total / (1024 ** 3)
            mem_free_g = getattr(mem, "available", mem.free) / (1024 ** 3)
            mem_percent = mem.percent

            # Network calculation with counter wrap/reboot protection
            bytes_recv, bytes_sent = self._get_net_bytes()
            if bytes_recv >= self.last_bytes_recv:
                down_bps = (bytes_recv - self.last_bytes_recv) / dt
            else:
                down_bps = 0.0

            if bytes_sent >= self.last_bytes_sent:
                up_bps = (bytes_sent - self.last_bytes_sent) / dt
            else:
                up_bps = 0.0

            self.last_bytes_recv = bytes_recv
            self.last_bytes_sent = bytes_sent
            self.last_time = now

            # Populate metrics cache in-place (reduces GC pressure)
            c = self._metrics_cache
            c["cpu"] = int(cpu)
            c["cpu_float"] = round(cpu, 1)
            c["mem_used_g"] = round(mem_used_g, 2)
            c["mem_total_g"] = round(mem_total_g, 2)
            c["mem_free_g"] = round(mem_free_g, 2)
            c["mem_percent"] = int(mem_percent)
            # Fixed-width 6 chars prevents horizontal jumping under fractional 125% scaling
            c["down_speed"] = format_speed(down_bps, fixed_width=True)
            c["up_speed"] = format_speed(up_bps, fixed_width=True)
            c["down_bps"] = down_bps
            c["up_bps"] = up_bps

            return c
        except Exception:
            return self._metrics_cache

    def get_per_cpu_percent(self) -> List[float]:
        """Fetch per-core CPU utilization (on-demand only, ~0.4ms overhead)."""
        try:
            return psutil.cpu_percent(percpu=True)
        except Exception:
            return []

    def get_top_processes(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Fetch top CPU-consuming processes (on-demand only with 1.5s debounce).
        
        Uses lightweight direct /proc reader on Linux to avoid psutil Process object
        allocation overhead and initial 0% sampling anomalies. Falls back to psutil
        on non-Linux platforms.
        """
        now = time.time()
        if self._cached_top_procs is not None and (now - self._last_top_proc_scan < 1.5):
            return self._cached_top_procs[:limit]

        # Linux direct /proc sampling with 80ms micro-window
        if os.path.exists("/proc"):
            try:
                clk_tck = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
                
                def _scan_proc_ticks() -> Dict[int, Tuple[str, int]]:
                    stats: Dict[int, Tuple[str, int]] = {}
                    for entry in os.scandir("/proc"):
                        if entry.name.isdigit():
                            try:
                                with open(f"/proc/{entry.name}/stat", "r") as f:
                                    content = f.read()
                                rparen = content.rfind(")")
                                if rparen != -1:
                                    parts = content[rparen + 2:].split()
                                    ticks = int(parts[11]) + int(parts[12])
                                    name = content[content.find("(") + 1:rparen]
                                    stats[int(entry.name)] = (name, ticks)
                            except Exception:
                                pass
                    return stats

                t0 = time.perf_counter()
                s1 = _scan_proc_ticks()
                time.sleep(0.08)
                t1 = time.perf_counter()
                s2 = _scan_proc_ticks()

                dt = max(0.01, t1 - t0)
                procs: List[Dict[str, Any]] = []
                for pid, (name, ticks2) in s2.items():
                    if pid in s1:
                        dticks = ticks2 - s1[pid][1]
                        if dticks > 0:
                            cpu_pct = (dticks / clk_tck) / dt * 100.0
                            procs.append({"pid": pid, "name": name, "cpu": round(cpu_pct, 1)})

                procs.sort(key=lambda x: x["cpu"], reverse=True)
                self._cached_top_procs = procs
                self._last_top_proc_scan = now
                return self._cached_top_procs[:limit]
            except Exception:
                pass

        # Fallback to psutil for macOS / BSD / non-proc environments
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
        """Fetch GPU hardware summary (cached on-demand, zero dynamic polling overhead)."""
        if self._cached_gpu_info is not None:
            return self._cached_gpu_info

        info: Dict[str, Any] = {
            "name": "未知显卡",
            "vram": "未知",
            "clock": "未知",
            "available": False
        }
        # Detect Zhaoxin C-960 or generic Linux DRM
        try:
            gpu_info_path = "/sys/class/drm/card0/device/gpu-info"
            if os.path.exists(gpu_info_path):
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
                info["name"] = "Linux DRM Card0"
                info["available"] = True
        except Exception:
            pass

        self._cached_gpu_info = info
        return info
