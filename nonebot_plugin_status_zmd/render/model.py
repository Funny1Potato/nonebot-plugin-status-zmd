"""把采集结果整理成模板上下文。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime

from nonebot.adapters import Bot as BaseBot

from .. import bot_info
from ..bot_info import BotStatus
from ..collectors import Snapshot, StaticInfo
from ..config import cache_dir, config
from ..sampler import sampler
from ..utils import (
    clamp,
    first_str,
    format_bitrate,
    format_byterate,
    format_duration,
    format_freq,
    format_percent,
    human_bytes,
    human_bytes_pair,
)
from .backend import backend_label
from .icons import icon_svg, proc_icon_key

VIEWPORT_WIDTH = 1176


@dataclass
class AppRow:
    name: str
    sub: str
    cpu: float
    mem: int
    cpu_pct: float
    mem_pct: float
    icon: str


@dataclass
class PerfRow:
    name: str
    sub: str
    icon: str
    hist: list[float]
    cur1_label: str
    cur1_value: str
    cur2_label: str
    cur2_value: str
    spec_label: str
    spec_value: str


@dataclass
class BotRow:
    self_id: str
    adapter: str
    nickname: str | None
    avatar: str | None
    online: bool
    uptime: str
    recv: str
    send: str
    icon: str


@dataclass
class GaugeView:
    percent: float
    value: int
    value_peak: int
    value_max: int
    cpu: float
    mem: float
    uptime: str
    svg: str = ""


@dataclass
class RenderModel:
    generated_at: str
    layout: str
    blocks: set[str]
    host_name: str
    system: str
    backend: str
    sample_desc: str
    slots: int
    proc_sort_by: str
    gauge: GaugeView | None = None
    apps: list[AppRow] = field(default_factory=list)
    perf: list[PerfRow] = field(default_factory=list)
    bots: list[BotRow] = field(default_factory=list)
    specs: list[tuple[str, str]] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    source_ok: bool = True
    source_text: str = "实时"


def _normalize(series: list[float], *, limit: float | None) -> list[float]:
    if not series:
        return []
    if limit and limit > 0:
        return [clamp(v / limit * 100, 0, 100) for v in series]
    top = max(series) or 1.0
    return [clamp(v / top * 100, 0, 100) for v in series]


def _build_apps(snapshot: Snapshot) -> list[AppRow]:
    top_cpu = max((p.cpu for p in snapshot.procs), default=0.0)
    top_mem = max((p.mem for p in snapshot.procs), default=0)
    cpu_base = max(10.0, top_cpu)
    mem_base = max(500 * 1024 * 1024, top_mem)

    rows: list[AppRow] = []
    for proc in snapshot.procs:
        display = proc.name
        if display.lower().endswith(".exe"):
            display = display[:-4]
        rows.append(
            AppRow(
                name=display,
                sub=f"PID {proc.pid}",
                cpu=proc.cpu,
                mem=proc.mem,
                cpu_pct=clamp(proc.cpu / cpu_base * 100, 2, 100),
                mem_pct=clamp(proc.mem / mem_base * 100, 2, 100),
                icon=icon_svg(proc_icon_key(proc.name), 20),
            ),
        )
    return rows


def _cpu_row(snapshot: Snapshot, static: StaticInfo) -> PerfRow:
    cpu = snapshot.cpu
    freq = cpu.freq_current or static.cpu_max_freq
    return PerfRow(
        name="处理器",
        sub=f"{static.cpu_logical or '?'} 线程 · {cpu.percent:.0f}% 负载",
        icon=icon_svg("cpu"),
        hist=_normalize(list(sampler.cpu_hist), limit=100),
        cur1_label="占用",
        cur1_value=format_percent(cpu.percent),
        cur2_label="速度",
        cur2_value=format_freq(freq),
        spec_label="规格",
        spec_value=f"最高 {format_freq(static.cpu_max_freq)}",
    )


def _mem_row(snapshot: Snapshot, static: StaticInfo) -> PerfRow:
    mem = snapshot.mem
    swap = (
        f"{human_bytes_pair(mem.swap_used, mem.swap_total)}"
        if mem.swap_total
        else "未部署"
    )
    return PerfRow(
        name="内存",
        sub=f"已用 {human_bytes_pair(mem.used, mem.total)}",
        icon=icon_svg("memory"),
        hist=_normalize(list(sampler.mem_hist), limit=100),
        cur1_label="占用",
        cur1_value=format_percent(mem.percent),
        cur2_label="Swap",
        cur2_value=swap,
        spec_label="规格",
        spec_value=f"总容量 {human_bytes(static.mem_total or mem.total)}",
    )


def _disk_rows(snapshot: Snapshot) -> list[PerfRow]:
    rows: list[PerfRow] = []
    for index, disk in enumerate(snapshot.disks):
        rw = disk.rw_bps
        rows.append(
            PerfRow(
                name=f"磁盘 {index} ({disk.mountpoint})",
                sub=f"已用 {human_bytes_pair(disk.used, disk.total)}",
                icon=icon_svg("disk"),
                hist=_normalize(
                    list(sampler.disk_hist.get(disk.mountpoint, [])),
                    limit=100,
                ),
                cur1_label="占用",
                cur1_value=format_percent(disk.percent),
                cur2_label="读写",
                cur2_value=format_byterate(rw) if rw is not None else "—",
                spec_label="规格",
                spec_value=f"{disk.fstype} · {disk.device}",
            ),
        )
    return rows


def _net_rows(snapshot: Snapshot) -> list[PerfRow]:
    rows: list[PerfRow] = []
    for net in snapshot.nets:
        rows.append(
            PerfRow(
                name=net.name,
                sub=(
                    f"链路 {net.speed_mbps} Mbps" if net.speed_mbps else "链路速率未知"
                ),
                icon=icon_svg("network"),
                hist=_normalize(
                    list(sampler.net_hist.get(net.name, [])),
                    limit=net.speed_mbps,
                ),
                cur1_label="下行",
                cur1_value=format_bitrate(net.down_bps),
                cur2_label="上行",
                cur2_value=format_bitrate(net.up_bps),
                spec_label="规格",
                spec_value=(
                    f"累计 ↓{human_bytes(net.down_total)} ↑{human_bytes(net.up_total)}"
                ),
            ),
        )
    return rows


def _bot_rows(bots: list[BaseBot]) -> list[BotRow]:
    now = datetime.now().astimezone()
    statuses: list[BotStatus] = [
        *bot_info.collect_bot_status(bots),
        *bot_info.collect_offline_bots(bots),
    ]

    rows: list[BotRow] = []
    for status in statuses:
        if status.connect_time:
            uptime = format_duration((now - status.connect_time).total_seconds())
        else:
            uptime = "离线"
        rows.append(
            BotRow(
                self_id=status.self_id,
                adapter=status.adapter,
                nickname=status.nickname,
                avatar=status.avatar,
                online=status.online,
                uptime=uptime,
                recv="未知" if status.recv is None else str(status.recv),
                send="未知" if status.send is None else str(status.send),
                icon=icon_svg("bot"),
            ),
        )
    return rows


def _spec_rows(
    snapshot: Snapshot,
    static: StaticInfo,
    bot_count: int,
) -> list[tuple[str, str]]:
    adapters, plugins = bot_info.nonebot_env()
    cores = "—"
    if static.cpu_physical or static.cpu_logical:
        cores = f"{static.cpu_physical or '?'} 核 / {static.cpu_logical or '?'} 线程"

    return [
        ("主机名", static.hostname),
        ("操作系统", static.system),
        ("内核", f"{static.kernel} · {static.machine}"),
        ("网络", ", ".join(static.addrs) or "—"),
        ("处理器", static.cpu_brand),
        ("核心", cores),
        ("内存", human_bytes(static.mem_total or snapshot.mem.total)),
        ("磁盘型号", ", ".join(static.disk_models) or "—"),
        ("运行时长", format_duration(effective_uptime())),
        ("NoneBot", f"{static.nonebot} · 运行 {format_duration(nonebot_uptime())}"),
        ("运行环境", f"{static.python} · 插件 {plugins} · 适配器 {adapters}"),
        ("连接 Bot", f"{bot_count} 个"),
        (
            "采样",
            f"每 {config.zmd_collect_interval}s · 最近 {config.zmd_history_size} 点",
        ),
        ("渲染后端", backend_label()),
        ("缓存目录", str(cache_dir())),
    ]


def nonebot_uptime() -> float:
    """NoneBot 启动至今的秒数（读模块属性，方便测试与预览注入）。"""
    return (datetime.now().astimezone() - bot_info.nonebot_run_time).total_seconds()


def effective_uptime() -> float:
    """系统 uptime（拿不到时退回采样器自身运行时长）。"""
    static = sampler.static
    if static and static.boot_time:
        return max(0.0, time.time() - static.boot_time)
    return time.time() - sampler.started_at


async def build_model(bots: list[BaseBot], *, want_gauge: bool) -> RenderModel:
    static = await sampler.ensure_static()
    snapshot = await sampler.ensure_latest()
    blocks = config.enabled_blocks()
    layout = config.zmd_layout

    model = RenderModel(
        generated_at=datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        layout=layout,
        blocks=blocks,
        host_name=first_str(config.zmd_host_name, static.hostname),
        system=static.system,
        backend=backend_label(),
        sample_desc=(
            f"每 {config.zmd_collect_interval}s 采样"
            f" · 窗口 {config.zmd_history_size} 点"
        ),
        slots=config.zmd_history_size,
        proc_sort_by=config.zmd_proc_sort_by,
        source_ok=sampler.last_error is None,
        source_text="实时" if sampler.last_error is None else "采样异常",
    )

    if want_gauge:
        from .svg import gauge_svg

        def compose(cpu: float, mem: float) -> float:
            return clamp(
                cpu * config.zmd_gauge_cpu_weight + mem * config.zmd_gauge_mem_weight,
                0.0,
                100.0,
            )

        percent = compose(snapshot.cpu.percent, snapshot.mem.percent)
        window = [
            compose(cpu, mem)
            for cpu, mem in zip(sampler.cpu_hist, sampler.mem_hist, strict=False)
        ] or [percent]
        scale = config.zmd_gauge_value_max / 100

        model.gauge = GaugeView(
            percent=percent,
            value=round(percent * scale),
            value_peak=round(max(window) * scale),
            value_max=int(config.zmd_gauge_value_max),
            cpu=snapshot.cpu.percent,
            mem=snapshot.mem.percent,
            uptime=format_duration(nonebot_uptime()),
            svg=gauge_svg(percent),
        )

    if layout == "full" and "apps" in blocks:
        model.apps = _build_apps(snapshot)

    if "perf" in blocks:
        model.perf = [
            _cpu_row(snapshot, static),
            _mem_row(snapshot, static),
            *_disk_rows(snapshot),
            *_net_rows(snapshot),
        ]

    if "bots" in blocks:
        model.bots = _bot_rows(bots)

    if "specs" in blocks:
        model.specs = _spec_rows(snapshot, static, len(bots))

    if model.gauge is not None:
        model.tags = [
            f"CPU {snapshot.cpu.percent:.0f}%",
            f"MEM {snapshot.mem.percent:.0f}%",
            f"综合 {model.gauge.percent:.1f}%",
        ]
    else:
        model.tags = [
            f"CPU {snapshot.cpu.percent:.0f}%",
            f"MEM {snapshot.mem.percent:.0f}%",
        ]

    return model
