"""常驻周期采样与历史曲线缓存。"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Awaitable
from typing import TypeVar

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

T = TypeVar("T")

#: 建立基准后等这么久再采第一次，让首采就有真实的时间窗口
PRIME_INTERVAL = 0.6


class SamplerDataUnavailable(RuntimeError):
    """采样数据还没准备好（采集超时或仍在进行中）。"""


#: 保持在跑的采集任务强引用：asyncio 对任务只持弱引用，不留引用的话
#: 超时后继续在跑的任务可能被 GC 掉（表现为「迟到的采样永远不落地」）
_pending_tasks: set[asyncio.Task] = set()


async def _bounded(
    coro: Awaitable[T],
    timeout: float,
    what: str,
) -> tuple[bool, T | None]:
    """等一个协程最多 ``timeout`` 秒，超时就不管它继续跑。

    刻意**不取消**：psutil 的阻塞调用跑在线程里，取消 await 并不会让线程
    停下，硬取消反而会让差分基准被半途改写。超时后我们只是不等它，任务继续
    在后台跑完（走完会自己更新状态），期间后续采样会被 ``_collecting`` 挡掉。
    """
    task = asyncio.ensure_future(coro)
    _pending_tasks.add(task)
    task.add_done_callback(_pending_tasks.discard)

    done, _pending = await asyncio.wait({task}, timeout=timeout)
    if task in done:
        return True, task.result()

    logger.warning(
        "ZMD {} 超过 {}s 仍未完成，先继续，数据由后续周期采样补上", what, timeout
    )
    task.add_done_callback(_log_late_result)
    return False, None


def _log_late_result(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    if exc := task.exception():
        logger.warning("ZMD 迟到的采样失败：{}: {}", exc.__class__.__name__, exc)
    else:
        logger.debug("ZMD 迟到的采样已完成")


class Sampler:
    """常驻采样器：持有差分状态、最近一次快照与各设备的历史曲线。

    历史里存的是原始值：CPU/内存/磁盘容量占用为百分比，网络为
    ``max(下行, 上行)`` 的 Mbps，归一化留给渲染层做（网络需要链路速率才知
    道百分比是否可算）。
    """

    def __init__(self) -> None:
        self._collector = SnapshotCollector()
        # 用普通 bool 而不是锁：asyncio 单线程，检查与置位之间没有 await，
        # 后来的调用可以立刻返回而不是排队等一个可能卡住的采样
        self._collecting = False
        size = config.stzmd_history_size

        self.static: StaticInfo | None = None
        self.latest: Snapshot | None = None
        self.last_error: str | None = None
        self.started_at: float = time.time()
        self.startup_degraded = False
        #: 启动期等待采集的总预算截止点（只在 start() 期间设置）
        self._deadline: float | None = None

        self.cpu_hist: deque[float] = deque(maxlen=size)
        self.mem_hist: deque[float] = deque(maxlen=size)
        self.disk_hist: dict[str, deque[float]] = {}
        self.net_hist: dict[str, deque[float]] = {}

    def _budget(self, default: float | None = None) -> float:
        """剩余预算；不在启动期时用 ``default``（默认取配置值）。"""
        fallback = default if default is not None else config.stzmd_collect_timeout
        if self._deadline is None:
            return fallback
        return max(0.1, self._deadline - time.monotonic())

    async def ensure_static(self, timeout: float | None = None) -> StaticInfo | None:
        """取静态信息；已有缓存直接返回，采集失败/超时返回 None。"""
        if self.static is not None:
            return self.static
        ok, value = await _bounded(
            collect_static(),
            self._budget(timeout),
            "采集静态信息",
        )
        if ok:
            self.static = value
        return self.static

    async def prime(self, timeout: float | None = None) -> bool:
        """建立 CPU / 磁盘 / 网络 / 进程的采样基准。

        不踩基准的话首采必然偏空：CPU 差值算不出来（psutil 的规定是首值无
        意义），磁盘与网络速率没有参照，进程 CPU 全是 0.0——也就是「刚启动
        那张图 CPU 显示 0」。
        """
        ok, _ = await _bounded(
            prime_snapshot(self._collector),
            self._budget(timeout),
            "建立采样基准",
        )
        if ok:
            await asyncio.sleep(PRIME_INTERVAL)
        return ok

    async def collect_once(self) -> Snapshot | None:
        """采一次快照。

        已有采样在进行中（可能正卡在慢 I/O 上）时直接返回 None，绝不排队——
        排队会把卡顿传染给调用方。
        """
        if self._collecting:
            logger.debug("ZMD 上一次采样尚未结束，跳过本次")
            return None

        self._collecting = True
        try:
            snapshot = await collect_snapshot(self._collector)
        except Exception as e:
            self.last_error = f"{e.__class__.__name__}: {e}"
            raise
        finally:
            self._collecting = False

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
        """取最近一次快照；没有就现采一次（受 ``stzmd_collect_timeout`` 约束）。"""
        if self.latest is not None:
            return self.latest

        ok, _ = await _bounded(
            self.collect_once(),
            config.stzmd_collect_timeout,
            "首次出图前采样",
        )
        if not ok:
            self.last_error = f"采集超时（>{config.stzmd_collect_timeout}s）"
        if self.latest is None:
            raise SamplerDataUnavailable(
                "状态数据还没准备好（采集超时或仍在进行中），稍后再试",
            )
        return self.latest

    async def _job(self) -> None:
        try:
            await self.collect_once()
        except Exception as e:  # noqa: BLE001
            logger.opt(exception=e).warning("ZMD 状态采样失败，错误已记录")

    async def start(self) -> None:
        """启动期采样。

        静态信息 + 基准 + 首采共用一份总预算 ``stzmd_collect_timeout``（不是
        每个阶段各算一遍）：宿主机上有失联的网络盘时 ``psutil.disk_usage()``
        这类调用可能阻塞很久，不能让它拖住 NoneBot 的启动。超时只是暂时没
        数据，周期采样会补上。
        """
        self._deadline = time.monotonic() + config.stzmd_collect_timeout
        try:
            static = await self.ensure_static()
            primed = await self.prime()
            if static is not None and primed:
                ok, _ = await _bounded(
                    self.collect_once(),
                    self._budget(),
                    "首次采样",
                )
                self.startup_degraded = not ok
            else:
                self.startup_degraded = True
        finally:
            self._deadline = None

        if self.startup_degraded:
            self.last_error = self.last_error or "启动期采集超时"
            logger.warning(
                "ZMD 启动期采集未在 {}s 内完成，已先继续启动；"
                "状态数据会在下个采样周期补齐",
                config.stzmd_collect_timeout,
            )

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
