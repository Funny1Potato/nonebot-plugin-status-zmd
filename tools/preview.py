"""终末状态图预览工具：不启动机器人也能出图调样式。

用法：
    python tools/preview.py --demo                   # 假数据 → preview.html
    python tools/preview.py --demo --shot            # 顺便出 preview.png
    python tools/preview.py --live --shot --open     # 真实采集并出图
    python tools/preview.py --all --shot             # 三种版式各出一份

--demo 走的是与线上完全相同的组装/渲染代码路径，只是把采集结果替换成
固定种子的假数据，所以样式调好后线上表现一致。
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import nonebot  # noqa: E402

# htmlrender >= 0.8 需要显式选择 Provider（等价于 .env 里的 RENDER=...）
nonebot.init(render={"provider": "playwright", "startup": "warmup"})

from nonebot_plugin_status_zmd import bot_info  # noqa: E402
from nonebot_plugin_status_zmd.collectors import (  # noqa: E402
    CpuStat,
    DiskStat,
    MemStat,
    NetStat,
    ProcStat,
    Snapshot,
    StaticInfo,
)
from nonebot_plugin_status_zmd.config import config  # noqa: E402
from nonebot_plugin_status_zmd.render import (  # noqa: E402
    build_html,
    build_model,
    render_model,
)
from nonebot_plugin_status_zmd.sampler import sampler  # noqa: E402

HISTORY = 180
GIB = 1024**3
MIB = 1024**2

DEMO_PROCS = (
    ("msedge.exe", 16.4, 2840 * MIB),
    ("Code.exe", 6.2, 1120 * MIB),
    ("python.exe", 4.8, 460 * MIB),
    ("mysqld.exe", 2.1, 380 * MIB),
    ("nginx.exe", 1.4, 96 * MIB),
    ("node.exe", 1.1, 210 * MIB),
    ("explorer.exe", 0.6, 84 * MIB),
    ("dwm.exe", 0.4, 62 * MIB),
)


class FakeAdapter:
    def get_name(self) -> str:
        return "OneBot V11"


class FakeBot:
    """只为预览提供 collect_bot_status 需要的两个属性。"""

    def __init__(self, self_id: str) -> None:
        self.self_id = self_id
        self.adapter = FakeAdapter()


def walk(rng: random.Random, start: float, size: int, spread: float) -> list[float]:
    value = start
    values: list[float] = []
    for _ in range(size):
        value = max(0.0, min(100.0, value + rng.uniform(-spread, spread)))
        values.append(value)
    return values


def load_demo_data() -> list[FakeBot]:
    rng = random.Random(20260921)
    cpu_percent = 34.2
    mem_percent = 61.3

    sampler.static = StaticInfo(
        system="Windows 11 Pro AMD64",
        hostname="ENDFIELD-01",
        kernel="Windows 10.0.26100",
        machine="AMD64",
        python=f"CPython {sys.version_info.major}.{sys.version_info.minor}.11",
        nonebot=nonebot.__version__ or "unknown",
        cpu_brand="AMD Ryzen 9 7945HX",
        cpu_physical=16,
        cpu_logical=32,
        cpu_max_freq=4200.0,
        mem_total=16 * GIB,
        disk_models=["Samsung SSD 980 PRO 1TB"],
        addrs=["以太网 192.168.1.24"],
        boot_time=datetime.now().timestamp() - 3 * 86400 - 7200,
    )
    sampler.latest = Snapshot(
        ts=datetime.now().timestamp(),
        cpu=CpuStat(percent=cpu_percent, freq_current=3620.0, freq_max=4200.0),
        mem=MemStat(
            used=int(9.8 * GIB),
            total=16 * GIB,
            percent=mem_percent,
            swap_used=2 * GIB,
            swap_total=8 * GIB,
            swap_percent=25.0,
        ),
        disks=[
            DiskStat(
                device="C:\\",
                mountpoint="C:\\",
                fstype="NTFS",
                used=int(486.2 * GIB),
                total=1024 * GIB,
                percent=47.5,
                read_bps=96 * MIB,
                write_bps=30 * MIB,
            ),
            DiskStat(
                device="D:\\",
                mountpoint="D:\\",
                fstype="NTFS",
                used=int(700.0 * GIB),
                total=2048 * GIB,
                percent=34.2,
                read_bps=18 * MIB,
                write_bps=4 * MIB,
            ),
        ],
        nets=[
            NetStat(
                name="以太网",
                up_bps=3.11e6 / 8,
                down_bps=12.42e6 / 8,
                up_total=int(120 * GIB),
                down_total=int(860 * GIB),
                speed_mbps=1000,
            ),
        ],
        procs=[
            ProcStat(pid=1000 + index, name=name, cpu=cpu, mem=mem)
            for index, (name, cpu, mem) in enumerate(DEMO_PROCS)
        ],
    )

    sampler.cpu_hist.clear()
    sampler.cpu_hist.extend(walk(rng, cpu_percent, HISTORY, 7))
    sampler.mem_hist.clear()
    sampler.mem_hist.extend(walk(rng, mem_percent, HISTORY, 2.4))
    sampler.disk_hist["C:\\"] = deque(walk(rng, 47.5, HISTORY, 0.6), maxlen=HISTORY)
    sampler.disk_hist["D:\\"] = deque(walk(rng, 34.2, HISTORY, 0.4), maxlen=HISTORY)
    sampler.net_hist["以太网"] = deque(walk(rng, 60.0, HISTORY, 25), maxlen=HISTORY)

    now = datetime.now().astimezone()
    bot_info.nonebot_run_time = now - timedelta(days=3, hours=2)
    bot_info.bot_connect_time["10001"] = now - timedelta(hours=3, minutes=12)
    bot_info.recv_num["10001"] = 8421
    bot_info.send_num["10001"] = 8302
    bot_info.prime_bot_meta("10001", "终末地终端")
    return [FakeBot("10001")]


async def load_live_data() -> list[FakeBot]:
    await sampler.ensure_static()
    # 必须先建立基准，否则首采的 CPU / 磁盘 / 网络都是空的（CPU 会显示 0）
    await sampler.prime()
    await sampler.collect_once()
    return []


async def build_one(
    bots: list,
    layout: str,
    out: Path,
    *,
    shot: bool,
    open_it: bool,
) -> None:
    config.zmd_layout = layout  # type: ignore[assignment]
    model = await build_model(bots, want_gauge="gauge" in config.enabled_blocks())
    html = await build_html(model)
    out.write_text(html, encoding="u8")
    print(f"[{layout}] HTML 已写入 {out}（{len(html) // 1024} KB）")

    if shot:
        image = await render_model(model)
        image_path = out.with_suffix(".png")
        image_path.write_bytes(image)
        print(f"[{layout}] 图片已写入 {image_path}（{len(image) // 1024} KB）")

    if open_it:
        import webbrowser

        webbrowser.open(out.resolve().as_uri())


async def main() -> None:
    parser = argparse.ArgumentParser(description="终末状态图预览")
    parser.add_argument("--demo", action="store_true", help="使用固定假数据")
    parser.add_argument("--live", action="store_true", help="使用真实采集数据")
    parser.add_argument("--shot", action="store_true", help="用 Playwright 出 PNG")
    parser.add_argument("--open", action="store_true", help="出完 HTML 后打开浏览器")
    parser.add_argument(
        "--layout",
        default="full",
        choices=["full", "gauge", "perf"],
        help="版式（--all 时忽略）",
    )
    parser.add_argument("--all", action="store_true", help="三种版式各出一份")
    parser.add_argument("--out", default=None, help="输出文件名前缀")
    args = parser.parse_args()

    bots = load_demo_data() if args.demo else await load_live_data()
    layouts = ["full", "gauge", "perf"] if args.all else [args.layout]

    for layout in layouts:
        name = args.out or ("preview" if len(layouts) == 1 else f"preview-{layout}")
        await build_one(
            bots,
            layout,
            ROOT / f"{name}.html",
            shot=args.shot,
            open_it=args.open,
        )


if __name__ == "__main__":
    asyncio.run(main())
