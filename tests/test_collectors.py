"""采集层：分区名归一、差分数学与真实 psutil 烟测。"""

from __future__ import annotations

import os
import time
from collections import namedtuple

import pytest

from nonebot_plugin_status_zmd.collectors import (
    SnapshotCollector,
    _collect_procs,
    _CpuCounter,
    _IoCounter,
    _strip_partition_suffix,
    collect_static_sync,
)

# 字段名对齐 psutil.cpu_times()
scputimes = namedtuple("scputimes", ["user", "system", "idle", "interrupt", "dpc"])


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


def test_io_rates_need_prime():
    counter = _IoCounter()
    # 没有基准时算不出速率
    assert counter.rates() == ({}, {})

    counter.prime()
    time.sleep(0.05)
    disk_rates, net_rates = counter.rates()
    assert disk_rates or net_rates  # 有基准后就能算出来
    assert all(r >= 0 for pair in disk_rates.values() for r in pair)
    assert all(r >= 0 for pair in net_rates.values() for r in pair)


class TestCpuCounter:
    def test_percent_needs_baseline(self):
        counter = _CpuCounter()
        # 没有基准时是「未知」，而不是 psutil 那种无意义的 0.0
        assert counter.percent() is None

        counter.prime()
        time.sleep(0.2)
        first = counter.percent()
        assert first is not None
        assert 0 <= first <= 100

        # 之后每次调用都有真值
        time.sleep(0.2)
        second = counter.percent()
        assert second is not None
        assert 0 <= second <= 100

    def test_busy_time_uses_idle_attribute(self):
        times = scputimes(user=10, system=10, idle=80, interrupt=0, dpc=0)
        assert _CpuCounter._busy(times) == 20.0  # 总 100 - idle 80
        # 丢了属性的普通 tuple 会把 idle 当 0，这正是「恒 100%」的来源
        assert _CpuCounter._busy((10, 10, 80, 0, 0)) == 100.0

    def test_prime_keeps_namedtuple_baseline(self):
        counter = _CpuCounter()
        counter.prime()
        # idle 各平台都有；iowait 只有 POSIX 有，靠 getattr 兜底
        assert hasattr(counter._prev, "idle")

    def test_percent_math(self):
        # busy = total - idle - iowait；这里 total +20、busy +10 → 50%
        previous = scputimes(user=10, system=10, idle=80, interrupt=0, dpc=0)
        current = scputimes(user=15, system=15, idle=90, interrupt=0, dpc=0)
        assert _CpuCounter._percent_between(previous, current) == 50.0

    def test_percent_is_clamped(self):
        previous = scputimes(user=0, system=0, idle=0, interrupt=0, dpc=0)
        current = scputimes(user=10, system=0, idle=0, interrupt=0, dpc=0)
        assert _CpuCounter._percent_between(previous, current) == 100.0

    def test_percent_without_elapsed_time(self):
        times = scputimes(user=1, system=1, idle=1, interrupt=0, dpc=0)
        assert _CpuCounter._percent_between(times, times) is None


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
    # 无基准时 CPU 算不出来（不是 0）
    assert collector.collect_sync().cpu.percent is None

    # 踩过基准后，第一份快照就该有真实值
    collector.prime_sync()
    time.sleep(0.3)

    first = collector.collect_sync()
    assert first.cpu.percent is not None
    assert 0 <= first.cpu.percent <= 100
    assert first.mem.total > 0
    assert 0 <= first.mem.percent <= 100
    assert first.ts > 0
    # 首采也要有磁盘/网络速率，不再是「读写 —」
    assert all(disk.rw_bps is not None for disk in first.disks)

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
