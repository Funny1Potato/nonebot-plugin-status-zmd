"""格式化函数的边界与口径。"""

from __future__ import annotations

import pytest

from nonebot_plugin_status_zmd.utils import (
    clamp,
    first_str,
    format_bitrate,
    format_byterate,
    format_duration,
    format_freq,
    format_percent,
    human_bytes,
    human_bytes_pair,
    match_any,
)

GIB = 1024**3
MIB = 1024**2


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "0 B"),
        (512, "512 B"),
        (2048, "2.0 KB"),
        (MIB, "1.0 MB"),
        (int(9.8 * GIB), "9.8 GB"),
        (1024 * GIB, "1.0 TB"),
    ],
)
def test_human_bytes(value, expected):
    assert human_bytes(value) == expected


@pytest.mark.parametrize(
    ("used", "total", "expected"),
    [
        (int(9.8 * GIB), 16 * GIB, "9.8 / 16.0 GB"),
        (2 * GIB, 8 * GIB, "2.0 / 8.0 GB"),
        # 1TB 盘不能写成 0.5 / 1.0 TB，精度太低
        (int(486.2 * GIB), 1024 * GIB, "486.2 / 1024.0 GB"),
        (700 * GIB, 2048 * GIB, "700.0 / 2048.0 GB"),
        # 4TB 盘上用了 2TB，已用量不是 0.x，保留 TB
        (2 * 1024 * GIB, 4 * 1024 * GIB, "2.0 / 4.0 TB"),
        (int(120.5 * MIB), 512 * MIB, "120.5 / 512.0 MB"),
        (0, 0, "0 B / —"),
    ],
)
def test_human_bytes_pair(used, total, expected):
    assert human_bytes_pair(used, total) == expected


def test_human_bytes_pair_keeps_large_units():
    # 100TB 的池子不该退档成 GB
    used = 2 * 1024 * GIB
    total = 100 * 1024 * GIB
    assert human_bytes_pair(used, total) == "2.0 / 100.0 TB"


@pytest.mark.parametrize(
    ("bps", "expected"),
    [
        # 12.42 Mbps 换算成字节/秒再转回来
        (12.42e6 / 8, "12.4 Mbps"),
        (1000, "8.0 Kbps"),
        (125_000_000, "1.0 Gbps"),
        (0, "0 bps"),
    ],
)
def test_format_bitrate(bps, expected):
    assert format_bitrate(bps) == expected


def test_format_byterate():
    assert format_byterate(126 * MIB) == "126 MB/s"
    assert format_byterate(0) == "0 B/s"


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "00:00:00"),
        (61, "00:01:01"),
        (3661, "01:01:01"),
        (86400 + 3661, "1天 01:01:01"),
        (-5, "00:00:00"),
    ],
)
def test_format_duration(seconds, expected):
    assert format_duration(seconds) == expected


@pytest.mark.parametrize(
    ("mhz", "expected"),
    [(3620.0, "3.62 GHz"), (800.0, "800 MHz"), (None, "—"), (0, "—")],
)
def test_format_freq(mhz, expected):
    assert format_freq(mhz) == expected


def test_format_percent():
    assert format_percent(61.34) == "61.3%"
    assert format_percent(5.0, precision=0) == "5%"


def test_clamp():
    assert clamp(120, 0, 100) == 100
    assert clamp(-1, 0, 100) == 0
    assert clamp(50, 0, 100) == 50


def test_match_any_handles_invalid_regex():
    assert match_any([r"^lo(op)?\d*$"], "lo")
    assert match_any([r"^lo(op)?\d*$"], "eth0") is False
    # 非法正则按字面量兜底
    assert match_any(["(unclosed"], "x(unclosed")
    assert match_any([], "anything") is False


def test_first_str():
    assert first_str(None, "", "值") == "值"
    assert first_str(None, None) == "—"
