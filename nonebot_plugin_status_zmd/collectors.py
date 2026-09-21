"""psutil 采集层。所有阻塞调用都通过线程池执行。"""

from __future__ import annotations

import os
import platform
import re
import socket
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psutil

from .config import config
from .utils import match_any, run_sync

# region 数据结构


@dataclass
class CpuStat:
    #: 距上次采样窗口的平均占用率；首次采样（无基准）为 None
    percent: float | None = None
    freq_current: float | None = None  # MHz
    freq_max: float | None = None  # MHz


@dataclass
class MemStat:
    used: int = 0
    total: int = 0
    percent: float = 0.0
    swap_used: int = 0
    swap_total: int = 0
    swap_percent: float = 0.0


@dataclass
class DiskStat:
    device: str
    mountpoint: str
    fstype: str
    used: int
    total: int
    percent: float
    read_bps: float | None = None
    write_bps: float | None = None

    @property
    def rw_bps(self) -> float | None:
        if self.read_bps is None and self.write_bps is None:
            return None
        return (self.read_bps or 0.0) + (self.write_bps or 0.0)


@dataclass
class NetStat:
    name: str
    up_bps: float
    down_bps: float
    up_total: int
    down_total: int
    speed_mbps: int | None = None


@dataclass
class ProcStat:
    pid: int
    name: str
    cpu: float
    mem: int


@dataclass
class StaticInfo:
    system: str = "未知系统"
    hostname: str = "—"
    kernel: str = "—"
    machine: str = "—"
    python: str = "—"
    nonebot: str = "—"
    cpu_brand: str = "未知型号"
    cpu_physical: int | None = None
    cpu_logical: int | None = None
    cpu_max_freq: float | None = None  # MHz
    mem_total: int = 0
    disk_models: list[str] = field(default_factory=list)
    addrs: list[str] = field(default_factory=list)
    boot_time: float = 0.0


@dataclass
class Snapshot:
    ts: float
    cpu: CpuStat
    mem: MemStat
    disks: list[DiskStat]
    nets: list[NetStat]
    procs: list[ProcStat]


# endregion

# region 静态信息


def _linux_name_version() -> tuple[str, str] | None:
    for path, name_key, ver_key in (
        (Path("/etc/os-release"), "NAME", "VERSION_ID"),
        (Path("/etc/lsb-release"), "DISTRIB_ID", "DISTRIB_RELEASE"),
    ):
        try:
            content = path.read_text(encoding="u8")
        except OSError:
            continue
        env: dict[str, str] = {}
        for line in content.splitlines():
            key, _, value = line.partition("=")
            env[key.strip().upper()] = value.strip().strip("\"'")
        if (name := env.get(name_key)) and (ver := env.get(ver_key)):
            return name, ver
    return None


def _system_name() -> str:
    system, _, release, _version, machine, _ = platform.uname()
    system, release, _version = platform.system_alias(system, release, _version)

    if system == "Windows":
        return f"Windows {release} {platform.win32_edition()} {machine}"
    if system == "Darwin":
        return f"macOS {platform.mac_ver()[0]} {machine}"
    if system == "Linux":
        if (prefix := os.getenv("PREFIX")) and "termux" in prefix:
            return f"Termux (Android) {release} {machine}"
        if os.getenv("ANDROID_ROOT") == "/system":
            return f"Linux (Android) {release} {machine}"
        if ver := _linux_name_version():
            name, version_id = ver
            version = release if version_id.lower() == "rolling" else version_id
            return f"{name} {version} {machine}"
        return f"未知 Linux {release} {machine}"
    return f"{system} {release}"


def _cpu_brand() -> str:
    try:
        from cpuinfo import get_cpu_info

        brand = str(get_cpu_info().get("brand_raw", ""))
    except Exception:
        return platform.processor() or "未知型号"
    brand = brand.split("@", maxsplit=1)[0].strip()
    if brand.lower().endswith(("cpu", "processor")):
        brand = brand.rsplit(maxsplit=1)[0].strip()
    return brand or "未知型号"


def _cpu_max_freq() -> float | None:
    freq = psutil.cpu_freq()
    return getattr(freq, "max", None) or None


def _disk_models() -> list[str]:
    models: list[str] = []
    sys_block = Path("/sys/block")
    if sys_block.is_dir():
        for entry in sorted(sys_block.iterdir()):
            if entry.name.startswith(("loop", "zram", "dm-", "ram", "sr")):
                continue
            try:
                model = (entry / "device" / "model").read_text(encoding="u8").strip()
            except OSError:
                continue
            if model and model not in models:
                models.append(model)
    return models


#: 只列真实可用的内网地址，链路的 169.254 自动获取失败地址没意义
ADDRESS_PREFIXES = ("10.", "192.", "172.", "100.")
#: 地址最多列几条，避免规格表被网卡列表撑爆
ADDRESS_LIMIT = 3


def _addresses() -> list[str]:
    result: list[str] = []
    try:
        addrs = psutil.net_if_addrs()
    except Exception:
        return result
    for name, entries in sorted(addrs.items()):
        if match_any(config.stzmd_ignore_nets, name):
            continue
        for entry in entries:
            # psutil 里没有 AF_INET 常量，family 就是 socket.AddressFamily
            if entry.family != socket.AF_INET:
                continue
            if not entry.address.startswith(ADDRESS_PREFIXES):
                continue
            result.append(f"{name} {entry.address}")
            if len(result) >= ADDRESS_LIMIT:
                return result
    return result


def collect_static_sync() -> StaticInfo:
    import nonebot

    freq_max = _cpu_max_freq()
    return StaticInfo(
        system=_system_name(),
        hostname=platform.node() or "—",
        kernel=f"{platform.system()} {platform.release()}",
        machine=platform.machine() or "—",
        python=f"{platform.python_implementation()} {platform.python_version()}",
        nonebot=nonebot.__version__ or "unknown",
        cpu_brand=_cpu_brand(),
        cpu_physical=psutil.cpu_count(logical=False),
        cpu_logical=psutil.cpu_count(),
        cpu_max_freq=freq_max,
        mem_total=psutil.virtual_memory().total,
        disk_models=_disk_models(),
        addrs=_addresses(),
        boot_time=psutil.boot_time(),
    )


# endregion

# region 动态采集


class _CpuCounter:
    """自己用 ``cpu_times`` 差值算占用率。

    不用 ``psutil.cpu_percent()`` 的原因：它的基准是进程级全局变量，任何其它
    代码（比如同时装了 picstatus）调用一次就会把基准吃掉，导致窗口变成 ~0ms
    而恒返回 0；而且它的首个返回值按文档就是「无意义的 0.0」。
    """

    def __init__(self) -> None:
        # 必须是 psutil 的 scputimes（namedtuple）：它带 idle/iowait 属性，
        # 一旦退化成普通 tuple，getattr 会静默拿到 0，占用率就恒为 100%
        self._prev: Any = None

    @staticmethod
    def _total(times: Any) -> float:
        total = float(sum(times))
        # Linux 的 guest 时间已计入 user，psutil 自己也会减掉
        total -= getattr(times, "guest", 0)
        total -= getattr(times, "guest_nice", 0)
        return total

    @classmethod
    def _busy(cls, times: Any) -> float:
        return (
            cls._total(times) - getattr(times, "idle", 0) - getattr(times, "iowait", 0)
        )

    def prime(self) -> None:
        """踩一次基准，让下一次 ``percent()`` 立刻有值。"""
        self._prev = psutil.cpu_times()

    @classmethod
    def _percent_between(cls, previous: Any, current: Any) -> float | None:
        all_delta = cls._total(current) - cls._total(previous)
        if all_delta <= 0:
            return None
        busy_delta = cls._busy(current) - cls._busy(previous)
        return round(min(100.0, max(0.0, busy_delta / all_delta * 100)), 1)

    def percent(self) -> float | None:
        """距上次调用的平均占用率；没有基准时返回 None。"""
        current = psutil.cpu_times()
        previous, self._prev = self._prev, current
        if previous is None:
            return None
        return self._percent_between(previous, current)


def _collect_cpu(counter: _CpuCounter) -> CpuStat:
    freq = psutil.cpu_freq()
    return CpuStat(
        percent=counter.percent(),
        freq_current=getattr(freq, "current", None) or None,
        freq_max=getattr(freq, "max", None) or None,
    )


def _collect_mem() -> MemStat:
    vm = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return MemStat(
        used=vm.used,
        total=vm.total,
        percent=vm.percent,
        swap_used=swap.used,
        swap_total=swap.total,
        swap_percent=swap.percent,
    )


_DEVICE_PATTERNS = (
    re.compile(r"^(disk\d+)s\d+$"),  # macOS: disk1s1
    re.compile(r"^(nvme\d+n\d+)p?\d+$"),  # nvme0n1p2
    re.compile(r"^(mmcblk\d+)p?\d+$"),  # mmcblk0p1
    re.compile(r"^([a-z]+)\d+$", re.IGNORECASE),  # sda1 / vda2
)


def _strip_partition_suffix(device: str) -> str:
    """``/dev/sda1`` / ``/dev/nvme0n1p2`` / ``disk1s1`` -> 物理设备名"""
    name = device.removeprefix("/dev/")
    for pattern in _DEVICE_PATTERNS:
        if match := pattern.match(name):
            return match.group(1)
    return name


class _IoCounter:
    """把 psutil 的累计计数器差分成功率。"""

    def __init__(self) -> None:
        self._ts: float = 0.0
        self._disk: dict[str, tuple[int, int]] = {}
        self._net: dict[str, tuple[int, int]] = {}

    @staticmethod
    def _rates(
        prev: dict[str, tuple[int, int]],
        curr: dict[str, tuple[int, int]],
        elapsed: float,
    ) -> dict[str, tuple[float, float]]:
        result: dict[str, tuple[float, float]] = {}
        for key, (in_bytes, out_bytes) in curr.items():
            if key not in prev or elapsed <= 0:
                continue
            prev_in, prev_out = prev[key]
            result[key] = (
                max(0.0, (in_bytes - prev_in) / elapsed),
                max(0.0, (out_bytes - prev_out) / elapsed),
            )
        return result

    @staticmethod
    def _snapshot() -> tuple[dict[str, tuple[int, int]], dict[str, tuple[int, int]]]:
        try:
            disk_counters = psutil.disk_io_counters(perdisk=True) or {}
        except Exception:
            disk_counters = {}
        try:
            net_counters = psutil.net_io_counters(pernic=True) or {}
        except Exception:
            net_counters = {}
        return (
            {k: (v.read_bytes, v.write_bytes) for k, v in disk_counters.items()},
            {k: (v.bytes_recv, v.bytes_sent) for k, v in net_counters.items()},
        )

    def prime(self) -> None:
        """踩一次基准，让下一次 ``rates()`` 立刻有值。"""
        self._disk, self._net = self._snapshot()
        self._ts = time.time()

    def rates(
        self,
    ) -> tuple[dict[str, tuple[float, float]], dict[str, tuple[float, float]]]:
        """返回（磁盘速率, 网卡速率），两者共用同一个时间窗口。"""
        disk, net = self._snapshot()
        now = time.time()
        elapsed = now - self._ts
        self._ts = now

        disk_rates = self._rates(self._disk, disk, elapsed)
        net_rates = self._rates(self._net, net, elapsed)
        self._disk, self._net = disk, net
        return disk_rates, net_rates


def _collect_disks(
    disk_rates: dict[str, tuple[float, float]],
) -> list[DiskStat]:
    single_physical = next(iter(disk_rates)) if len(disk_rates) == 1 else None
    result: list[DiskStat] = []
    try:
        partitions = psutil.disk_partitions(all=False)
    except Exception:
        return result

    for part in partitions:
        if match_any(config.stzmd_ignore_parts, part.mountpoint) or match_any(
            config.stzmd_ignore_parts,
            part.device,
        ):
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except OSError:
            continue

        rate = disk_rates.get(_strip_partition_suffix(part.device))
        if rate is None and single_physical is not None:
            rate = disk_rates[single_physical]

        result.append(
            DiskStat(
                device=part.device,
                mountpoint=part.mountpoint,
                fstype=part.fstype or "—",
                used=usage.used,
                total=usage.total,
                percent=usage.percent,
                read_bps=rate[0] if rate else None,
                write_bps=rate[1] if rate else None,
            ),
        )

    result.sort(key=lambda d: d.mountpoint)
    return result


def _collect_nets(
    net_rates: dict[str, tuple[float, float]],
) -> list[NetStat]:
    result: list[NetStat] = []
    try:
        counters = psutil.net_io_counters(pernic=True) or {}
    except Exception:
        return result
    try:
        stats = psutil.net_if_stats() or {}
    except Exception:
        stats = {}

    for name, counter in sorted(counters.items()):
        if match_any(config.stzmd_ignore_nets, name):
            continue
        down, up = net_rates.get(name, (0.0, 0.0))
        speed = getattr(stats.get(name), "speed", 0) or None
        result.append(
            NetStat(
                name=name,
                up_bps=up,
                down_bps=down,
                up_total=counter.bytes_sent,
                down_total=counter.bytes_recv,
                speed_mbps=speed,
            ),
        )
    return result


def _collect_procs(logical_cpu: int | None) -> list[ProcStat]:
    divisor = logical_cpu if logical_cpu and not config.stzmd_proc_cpu_max_100p else 1
    procs: list[ProcStat] = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
        try:
            info = proc.info
            pid = int(info.get("pid") or 0)
            name = str(info.get("name") or "")
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        if not pid or match_any(config.stzmd_ignore_procs, name):
            continue
        mem_info = info.get("memory_info")
        rss = getattr(mem_info, "rss", 0) or 0
        procs.append(
            ProcStat(
                pid=pid,
                name=name,
                cpu=(info.get("cpu_percent") or 0.0) / divisor,
                mem=rss,
            ),
        )

    key = (lambda p: p.mem) if config.stzmd_proc_sort_by == "mem" else (lambda p: p.cpu)
    procs.sort(key=key, reverse=True)
    return procs[: config.stzmd_proc_len]


class SnapshotCollector:
    """持有各计数器的基准，保证能算出速率且第一次采样就有意义的值。"""

    def __init__(self) -> None:
        self._cpu = _CpuCounter()
        self._io = _IoCounter()

    def prime_sync(self) -> None:
        """建立 CPU / 磁盘 / 网络 / 进程的基准（启动时调用一次）。

        没有基准时：CPU 差值算不出来、磁盘与网络速率是空的、进程 CPU 全是
        0.0——也就是「刚启动的那张图 CPU 显示 0」。
        """
        self._cpu.prime()
        self._io.prime()
        # 进程的 cpu_percent 也依赖上一次调用，先踩一次
        _collect_procs(psutil.cpu_count())

    def collect_sync(self) -> Snapshot:
        cpu = _collect_cpu(self._cpu)
        mem = _collect_mem()
        disk_rates, net_rates = self._io.rates()
        disks = _collect_disks(disk_rates)
        nets = _collect_nets(net_rates)
        procs = _collect_procs(psutil.cpu_count())
        return Snapshot(
            ts=time.time(),
            cpu=cpu,
            mem=mem,
            disks=disks,
            nets=nets,
            procs=procs,
        )


async def collect_static() -> StaticInfo:
    return await run_sync(collect_static_sync)


async def collect_snapshot(collector: SnapshotCollector) -> Snapshot:
    return await run_sync(collector.collect_sync)


async def prime_snapshot(collector: SnapshotCollector) -> None:
    return await run_sync(collector.prime_sync)


# endregion
