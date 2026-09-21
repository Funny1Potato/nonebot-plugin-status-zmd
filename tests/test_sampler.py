"""采样器：历史窗口长度、缓存复用与历史键。"""

from __future__ import annotations

from nonebot_plugin_status_zmd.sampler import Sampler


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
    assert first is second
    assert first.hostname
