"""常驻周期采样与历史曲线缓存。"""

from __future__ import annotations

import asyncio
import time
from collections import deque

from nonebot import logger
from nonebot_plugin_apscheduler import scheduler

from .collectors import (
    Snapshot,
    SnapshotCollector,
    StaticInfo,
    collect_snapshot,
    collect_static,
    prime_snapshot,
)
from .config import config

#: 建立基准后等这么久再采第一次，让首采就有真实的时间窗口
PRIME_INTERVAL = 0.6


class Sampler:
    """常驻采样器：持有差分状态、最近一次快照与各设备的历史曲线。

    历史里存的是原始值：CPU/内存/磁盘容量占用为百分比，网络为
    ``max(下行, 上行)`` 的 Mbps，归一化留给渲染层做（网络需要链路速率才知
    道百分比是否可算）。
    """

    def __init__(self) -> None:
        self._collector = SnapshotCollector()
        self._lock = asyncio.Lock()
        size = config.stzmd_history_size

        self.static: StaticInfo | None = None
        self.latest: Snapshot | None = None
        self.last_error: str | None = None
        self.started_at: float = time.time()

        self.cpu_hist: deque[float] = deque(maxlen=size)
        self.mem_hist: deque[float] = deque(maxlen=size)
        self.disk_hist: dict[str, deque[float]] = {}
        self.net_hist: dict[str, deque[float]] = {}

    async def ensure_static(self) -> StaticInfo:
        if self.static is None:
            self.static = await collect_static()
        return self.static

    async def prime(self) -> None:
        """建立 CPU / 磁盘 / 网络 / 进程的采样基准。

        不踩基准的话首采必然偏空：CPU 差值算不出来（psutil 的规定是首值无
        意义），磁盘与网络速率没有参照，进程 CPU 全是 0.0——也就是「刚启动
        的那张图 CPU 显示 0」。
        """
        await prime_snapshot(self._collector)
        await asyncio.sleep(PRIME_INTERVAL)

    async def collect_once(self) -> Snapshot:
        async with self._lock:
            snapshot = await collect_snapshot(self._collector)

            self.latest = snapshot
            self.last_error = None
            # CPU 无基准时为 None，历史按 0 记以保持与内存序列等长
            self.cpu_hist.append(snapshot.cpu.percent or 0.0)
            self.mem_hist.append(snapshot.mem.percent)

            for disk in snapshot.disks:
                series = self.disk_hist.setdefault(
                    disk.mountpoint,
                    deque(maxlen=config.stzmd_history_size),
                )
                series.append(disk.percent)

            for net in snapshot.nets:
                series = self.net_hist.setdefault(
                    net.name,
                    deque(maxlen=config.stzmd_history_size),
                )
                series.append(max(net.down_bps, net.up_bps) * 8 / 1e6)

            return snapshot

    async def ensure_latest(self) -> Snapshot:
        """取最近一次采样；一次都没有时立刻采一次。"""
        if self.latest is None:
            return await self.collect_once()
        return self.latest

    async def _job(self) -> None:
        try:
            await self.collect_once()
        except Exception as e:  # noqa: BLE001
            self.last_error = f"{e.__class__.__name__}: {e}"
            logger.opt(exception=e).warning("ZMD 状态采样失败")

    async def start(self) -> None:
        await self.ensure_static()
        await self.prime()
        try:
            await self.collect_once()
        except Exception as e:  # noqa: BLE001
            self.last_error = f"{e.__class__.__name__}: {e}"
            logger.opt(exception=e).warning("ZMD 首次采样失败，将在下个周期重试")

        scheduler.add_job(
            self._job,
            "interval",
            seconds=config.stzmd_collect_interval,
            id="nonebot_plugin_status_zmd_sampler",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        logger.debug(
            "ZMD 采样任务已启动，间隔 {}s，历史窗口 {} 点",
            config.stzmd_collect_interval,
            config.stzmd_history_size,
        )


sampler = Sampler()
