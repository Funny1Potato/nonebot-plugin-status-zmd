"""采样器：历史窗口、缓存复用、首采基准、超时闸与逐设备开关。"""

from __future__ import annotations

import asyncio
import time
from importlib import import_module

import pytest

from nonebot_plugin_status_zmd.collectors import CpuStat, MemStat, Snapshot, StaticInfo
from nonebot_plugin_status_zmd.render.model import build_model
from nonebot_plugin_status_zmd.sampler import Sampler, SamplerDataUnavailable

# 包内 ``sampler`` 这个名字被 Sampler 实例占用了，取模块要用 import_module
sampler_module = import_module("nonebot_plugin_status_zmd.sampler")
live_sampler = sampler_module.sampler


class FakeScheduler:
    """记录 add_job 调用，避免测试真的去动 apscheduler。"""

    def __init__(self) -> None:
        self.jobs: list[tuple] = []

    def add_job(self, func, *args, **kwargs) -> None:
        self.jobs.append((func, args, kwargs))


@pytest.fixture()
def fast_startup(monkeypatch):
    """把启动基准等待与调度器换掉：测试跑得快且不碰 apscheduler。"""
    monkeypatch.setattr(sampler_module, "PRIME_INTERVAL", 0.0)
    fake_scheduler = FakeScheduler()
    monkeypatch.setattr(sampler_module, "scheduler", fake_scheduler)
    return fake_scheduler


async def test_collect_once_fills_history(restore_config):
    restore_config.stzmd_history_size = 3
    sampler = Sampler()

    await sampler.collect_once()
    assert sampler.latest is not None
    assert sampler.last_error is None
    assert len(sampler.cpu_hist) == 1
    assert len(sampler.mem_hist) == 1

    for _ in range(4):
        await sampler.collect_once()

    # deque 的 maxlen 生效，不会无限增长
    assert len(sampler.cpu_hist) == 3
    assert len(sampler.mem_hist) == 3
    assert all(0 <= v <= 100 for v in sampler.cpu_hist)


async def test_ensure_latest_reuses_snapshot(restore_config):
    restore_config.stzmd_history_size = 5
    sampler = Sampler()

    first = await sampler.ensure_latest()
    assert sampler.latest is first
    # 已有数据时不应重复采样
    second = await sampler.ensure_latest()
    assert second is first
    assert len(sampler.cpu_hist) == 1


async def test_history_keys_follow_devices(restore_config):
    restore_config.stzmd_history_size = 4
    sampler = Sampler()
    snapshot = await sampler.collect_once()
    assert snapshot is not None

    for disk in snapshot.disks:
        assert disk.mountpoint in sampler.disk_hist
        assert len(sampler.disk_hist[disk.mountpoint]) == 1
    for net in snapshot.nets:
        assert net.name in sampler.net_hist
        # 历史里存的是 Mbps 原始值，不是百分比
        assert sampler.net_hist[net.name][0] >= 0


async def test_ensure_static_is_cached(restore_config):
    sampler = Sampler()
    first = await sampler.ensure_static()
    second = await sampler.ensure_static()
    assert first is not None
    assert first is second
    assert first.hostname


async def test_first_sample_without_prime_has_no_cpu(restore_config):
    """不踩基准时 CPU 算不出来（None），渲染层会显示「待首次采样」而不是 0。"""
    restore_config.stzmd_history_size = 4
    sampler = Sampler()
    first = await sampler.collect_once()
    assert first is not None
    assert first.cpu.percent is None
    assert sampler.cpu_hist[0] == 0.0  # 历史按 0 记，保持与内存序列等长


async def test_prime_makes_first_sample_meaningful(restore_config, monkeypatch):
    """踩过基准后，第一份快照就有真实的 CPU 与磁盘/网络速率。"""
    restore_config.stzmd_history_size = 4
    monkeypatch.setattr(sampler_module, "PRIME_INTERVAL", 0.3)

    sampler = Sampler()
    assert await sampler.prime() is True
    snapshot = await sampler.collect_once()
    assert snapshot is not None

    assert snapshot.cpu.percent is not None
    assert 0 <= snapshot.cpu.percent <= 100
    assert sampler.cpu_hist[-1] == pytest.approx(snapshot.cpu.percent)
    # 首采也要有磁盘/网络速率，不再是「读写 —」
    assert all(d.rw_bps is not None for d in snapshot.disks)


class TestCollectTimeout:
    """超时闸：慢 I/O（比如失联的网络盘）不能拖住启动，也不能拖住出图。"""

    async def test_start_does_not_wait_for_stuck_static(
        self,
        restore_config,
        fast_startup,
        monkeypatch,
    ):
        restore_config.stzmd_collect_timeout = 0.2

        async def stuck() -> StaticInfo:
            await asyncio.sleep(1.0)
            return StaticInfo(hostname="stuck")

        monkeypatch.setattr(sampler_module, "collect_static", stuck)

        sampler = Sampler()
        started = time.monotonic()
        await sampler.start()
        elapsed = time.monotonic() - started

        assert elapsed < 0.8  # 没被 1s 的卡顿拖住
        assert sampler.startup_degraded is True
        assert sampler.static is None
        # 超时也要注册周期任务，好让数据后面补上
        assert fast_startup.jobs
        assert fast_startup.jobs[0][2]["id"] == "nonebot_plugin_status_zmd_sampler"

    async def test_startup_budget_is_shared(
        self,
        restore_config,
        fast_startup,
        monkeypatch,
    ):
        """三个阶段的等待共用一份预算，而不是「超时 × 阶段数」。"""
        restore_config.stzmd_collect_timeout = 0.3

        async def stuck_static() -> StaticInfo:
            await asyncio.sleep(1.0)
            return StaticInfo(hostname="stuck")

        async def stuck_prime(_collector) -> None:
            await asyncio.sleep(1.0)

        async def stuck_collect(_collector):
            await asyncio.sleep(1.0)
            return None

        monkeypatch.setattr(sampler_module, "collect_static", stuck_static)
        monkeypatch.setattr(sampler_module, "prime_snapshot", stuck_prime)
        monkeypatch.setattr(sampler_module, "collect_snapshot", stuck_collect)

        sampler = Sampler()
        started = time.monotonic()
        await sampler.start()
        elapsed = time.monotonic() - started

        # 三个各 1s 的卡顿，共享 0.3s 预算 → 总耗时应在预算附近
        assert elapsed < 0.8
        assert sampler.startup_degraded is True
        assert sampler.static is None
        assert sampler.latest is None

    async def test_slow_collect_finishes_late_and_writes_state(
        self,
        restore_config,
        fast_startup,
        monkeypatch,
    ):
        restore_config.stzmd_collect_timeout = 0.2

        async def fast_static() -> StaticInfo:
            return StaticInfo(hostname="fast")

        async def fast_prime(_collector) -> None:
            return None

        async def slow(_collector) -> Snapshot:
            # 模拟卡在慢 I/O 上：超时窗口内肯定完不成
            await asyncio.sleep(0.6)
            return Snapshot(
                ts=time.time(),
                cpu=CpuStat(percent=12.5),
                mem=MemStat(used=1, total=2, percent=50.0),
                disks=[],
                nets=[],
                procs=[],
            )

        monkeypatch.setattr(sampler_module, "collect_static", fast_static)
        monkeypatch.setattr(sampler_module, "prime_snapshot", fast_prime)
        monkeypatch.setattr(sampler_module, "collect_snapshot", slow)

        sampler = Sampler()
        started = time.monotonic()
        await sampler.start()
        assert time.monotonic() - started < 0.8

        # 启动先放行，此刻还没有数据
        assert sampler.startup_degraded is True
        assert sampler.latest is None

        # 迟到的那次没有被取消，跑完后照样写进状态
        for _ in range(20):
            if sampler.latest is not None:
                break
            await asyncio.sleep(0.1)
        assert sampler.latest is not None
        assert sampler.latest.cpu.percent == 12.5
        assert len(sampler.cpu_hist) == 1
        assert sampler.last_error is None  # 成功后清掉降级标记

    async def test_ensure_latest_reports_timeout_instead_of_hanging(
        self,
        restore_config,
        monkeypatch,
    ):
        restore_config.stzmd_collect_timeout = 0.2

        async def stuck(collector):
            await asyncio.sleep(0.4)
            return None

        monkeypatch.setattr(sampler_module, "collect_snapshot", stuck)

        sampler = Sampler()
        started = time.monotonic()
        with pytest.raises(SamplerDataUnavailable):
            await sampler.ensure_latest()
        assert time.monotonic() - started < 0.8
        assert sampler.last_error is not None
        assert "超时" in sampler.last_error

        await asyncio.sleep(0.4)  # 收尾，避免留下未完成任务

    async def test_collect_once_skips_while_busy(self, restore_config, monkeypatch):
        real_collect = sampler_module.collect_snapshot
        started = asyncio.Event()
        release = asyncio.Event()

        async def slow(collector):
            started.set()
            await release.wait()
            return await real_collect(collector)

        monkeypatch.setattr(sampler_module, "collect_snapshot", slow)

        sampler = Sampler()
        task = asyncio.create_task(sampler.collect_once())
        await started.wait()

        # 正在采样时不排队，立刻返回 None
        started_at = time.monotonic()
        assert await sampler.collect_once() is None
        assert time.monotonic() - started_at < 0.2

        release.set()
        assert await task is not None
        assert len(sampler.cpu_hist) == 1  # 只采了一次


@pytest.fixture()
async def prepared_sampler(restore_config, monkeypatch):
    """把全局 sampler 填上真实数据。"""
    monkeypatch.setattr(sampler_module, "PRIME_INTERVAL", 0.1)
    await live_sampler.ensure_static()
    assert await live_sampler.prime()
    await live_sampler.collect_once()
    return live_sampler


class TestDeviceToggles:
    """STZMD_DEVICES：逐设备开关与顺序。"""

    @pytest.fixture(autouse=True)
    async def prepared(self, prepared_sampler):
        yield

    async def test_only_cpu(self, restore_config):
        restore_config.stzmd_devices = ["cpu"]
        model = await build_model([], want_gauge=False)
        assert [row.name for row in model.perf] == ["处理器"]

    async def test_subset_and_config_order(self, restore_config):
        restore_config.stzmd_devices = ["net", "cpu"]
        model = await build_model([], want_gauge=False)
        names = [row.name for row in model.perf]
        assert names[-1] == "处理器"  # 顺序跟随配置
        assert "处理器" not in names[:-1]

    async def test_all_devices_include_disk_and_net(self, restore_config):
        restore_config.stzmd_devices = ["cpu", "mem", "disk", "net"]
        model = await build_model([], want_gauge=False)
        names = [row.name for row in model.perf]
        assert names[0] == "处理器"
        assert names[1] == "内存"

        snapshot = live_sampler.latest
        assert snapshot is not None
        if snapshot.disks:
            assert any(name.startswith("磁盘") for name in names)
        if snapshot.nets:
            assert any(name in live_sampler.net_hist for name in names)
