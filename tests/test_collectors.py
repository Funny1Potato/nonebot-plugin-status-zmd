"""采集层：分区名归一、差分数学与真实 psutil 烟测。"""

from __future__ import annotations

import os

import pytest

from nonebot_plugin_status_zmd.collectors import (
    SnapshotCollector,
    _collect_procs,
    _IoCounter,
    _strip_partition_suffix,
    collect_static_sync,
)


@pytest.mark.parametrize(
    ("device", "expected"),
    [
        ("/dev/sda1", "sda"),
        ("/dev/sda", "sda"),
        ("/dev/nvme0n1p2", "nvme0n1"),
        ("/dev/mmcblk0p1", "mmcblk0"),
        ("/dev/vda2", "vda"),
        ("disk1s1", "disk1"),
        ("sda", "sda"),
        ("C:\\", "C:\\"),
    ],
)
def test_strip_partition_suffix(device, expected):
    assert _strip_partition_suffix(device) == expected


def test_rates_need_two_samples():
    assert _IoCounter._rates({}, {"sda": (100, 200)}, 1.0) == {}


def test_rates_math():
    rates = _IoCounter._rates({"sda": (100, 200)}, {"sda": (1100, 1200)}, 2.0)
    assert rates["sda"] == (500.0, 500.0)


def test_rates_never_negative_and_ignore_zero_elapsed():
    assert _IoCounter._rates({"sda": (100, 100)}, {"sda": (50, 50)}, 1.0) == {
        "sda": (0.0, 0.0),
    }
    assert _IoCounter._rates({"sda": (1, 1)}, {"sda": (9, 9)}, 0.0) == {}


def test_collect_static_real_machine():
    info = collect_static_sync()
    assert info.system
    assert info.hostname
    assert info.cpu_logical and info.cpu_logical >= 1
    assert info.cpu_brand
    assert info.mem_total > 0
    assert info.boot_time > 0
    assert info.python.startswith("CPython")


def test_snapshot_collector_smoke():
    collector = SnapshotCollector()
    first = collector.collect_sync()
    assert 0 <= first.cpu.percent <= 100
    assert first.mem.total > 0
    assert 0 <= first.mem.percent <= 100
    assert first.ts > 0

    second = collector.collect_sync()
    assert isinstance(second.disks, list)
    assert isinstance(second.nets, list)
    for disk in second.disks:
        assert 0 <= disk.percent <= 100
        assert disk.total > 0
        if disk.read_bps is not None:
            assert disk.read_bps >= 0
    for net in second.nets:
        assert net.down_bps >= 0
        assert net.up_bps >= 0


def test_procs_respect_limits_and_order(restore_config):
    restore_config.zmd_proc_len = 3
    restore_config.zmd_proc_sort_by = "mem"
    procs = _collect_procs(os.cpu_count() or 1)
    assert len(procs) <= 3
    assert procs == sorted(procs, key=lambda p: p.mem, reverse=True)
    assert all(p.mem >= 0 for p in procs)


def test_procs_ignore_pattern(restore_config):
    restore_config.zmd_proc_len = 64
    restore_config.zmd_proc_sort_by = "cpu"
    # 进程名不可能以这个前缀开头，结果应该和不过滤相比只是少一些
    restore_config.zmd_ignore_procs = [r"^zmd-definitely-not-a-real-process$"]
    procs = _collect_procs(os.cpu_count() or 1)
    assert all(
        not p.name.startswith("zmd-definitely-not-a-real-process") for p in procs
    )

    restore_config.zmd_ignore_procs = [r"."]
    assert _collect_procs(os.cpu_count() or 1) == []
