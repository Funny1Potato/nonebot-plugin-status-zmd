"""HTML 组装：板块开关、自包含性与完整渲染烟测。"""

from __future__ import annotations

import pytest

from nonebot_plugin_status_zmd.render.env import build_html
from nonebot_plugin_status_zmd.render.model import (
    AppRow,
    BotRow,
    GaugeView,
    PerfRow,
    RenderModel,
)
from nonebot_plugin_status_zmd.render.svg import gauge_svg


def make_model(**overrides) -> RenderModel:
    defaults = {
        "generated_at": "2026-09-21 20:00:00",
        "layout": "full",
        "blocks": set(),
        "host_name": "ENDFIELD-01",
        "system": "Windows 11 Pro AMD64",
        "backend": "HTMLRENDER 0.8.1 / 0.8+",
        "sample_desc": "每 5s 采样 · 窗口 180 点",
        "slots": 180,
        "proc_sort_by": "cpu",
    }
    defaults.update(overrides)
    return RenderModel(**defaults)


def make_gauge() -> GaugeView:
    return GaugeView(
        percent=50.46,
        value=164398,
        value_peak=289313,
        value_max=325799,
        cpu=34.2,
        mem=61.3,
        uptime="3天 02:00:00",
        svg=gauge_svg(50.46),
    )


def make_perf() -> PerfRow:
    return PerfRow(
        name="处理器",
        sub="32 线程 · 34% 负载",
        icon="<svg></svg>",
        hist=[10.0, 50.0, 100.0],
        cur1_label="占用",
        cur1_value="34.2%",
        cur2_label="速度",
        cur2_value="3.62 GHz",
        spec_label="规格",
        spec_value="最高 4.20 GHz",
    )


async def test_html_is_self_contained():
    html = await build_html(make_model(gauge=make_gauge()))
    assert "--yellow-bar: #ded24e" in html  # CSS 已内联
    assert "<link" not in html
    assert "@import" not in html
    # 除了 SVG 命名空间，不应有任何外部资源引用
    assert 'src="http' not in html
    assert "http://www.w3.org/2000/svg" in html
    assert "document.body.classList.contains" not in html  # 打标脚本只应写类名
    assert "classList.add('done')" in html


async def test_topbar_and_footer_always_render():
    html = await build_html(make_model())
    assert "END" in html
    assert "//" in html
    assert "ENDFIELD-01" in html
    assert "HTMLRENDER 0.8.1" in html
    assert "2026-09-21 20:00:00" in html


async def test_gauge_block():
    html = await build_html(make_model(gauge=make_gauge()))
    assert "占用报告" in html
    assert "164,398" in html
    assert "/ 325,799" in html
    assert "289,313" in html
    assert "实际占用" in html
    assert "最大占用" in html
    assert "已运行" in html


async def test_apps_block():
    model = make_model(
        apps=[
            AppRow(
                name="msedge",
                sub="PID 1000",
                cpu=16.4,
                mem=2840 * 1024 * 1024,
                cpu_pct=100.0,
                mem_pct=100.0,
                icon="<svg></svg>",
            ),
        ],
    )
    html = await build_html(model)
    assert "应用概况" in html
    assert 'class="app-row"' in html
    assert "msedge" in html
    assert "2840" in html
    assert "16.4" in html


async def test_bots_block():
    model = make_model(
        bots=[
            BotRow(
                self_id="10001",
                adapter="OneBot V11",
                nickname="终末地终端",
                avatar=None,
                online=True,
                uptime="03:12:00",
                recv="8421",
                send="8302",
                icon="<svg></svg>",
            ),
        ],
    )
    html = await build_html(model)
    assert "终端链路" in html
    assert "终末地终端" in html
    assert "在线" in html
    assert "03:12:00" in html


async def test_perf_block_bars():
    model = make_model(perf=[make_perf()])
    html = await build_html(model)
    assert "设备性能" in html
    assert html.count('class="bar"') == 3
    assert "--slots: 180" in html
    assert "--h: 100.0%" in html


async def test_blocks_are_optional():
    html = await build_html(make_model())
    # 按标记断言：CSS 注释里也含这些中文词
    assert 'class="app-row"' not in html
    assert 'class="bot-row"' not in html
    assert 'class="perf-row"' not in html
    assert 'class="spec-item"' not in html
    assert 'class="gauge-svg"' not in html
    assert 'class="gauge-center"' not in html


async def test_two_column_layout_needs_both_sides():
    # 只有电量环时走单栏居中
    html = await build_html(make_model(gauge=make_gauge()))
    assert 'class="gauge-solo"' in html
    assert 'class="overview-grid"' not in html


async def test_apps_and_bots_render_without_gauge():
    """关掉电量环但保留应用表/终端链路时，这两个板块不能凭空消失。"""
    model = make_model(
        apps=[
            AppRow(
                name="msedge",
                sub="PID 1000",
                cpu=1.0,
                mem=1024,
                cpu_pct=10.0,
                mem_pct=10.0,
                icon="<svg></svg>",
            ),
        ],
        bots=[
            BotRow(
                self_id="1",
                adapter="OneBot V11",
                nickname=None,
                avatar=None,
                online=True,
                uptime="00:00:01",
                recv="0",
                send="0",
                icon="<svg></svg>",
            ),
        ],
    )
    html = await build_html(model)
    assert 'class="app-row"' in html
    assert 'class="bot-row"' in html
    assert 'class="overview-grid"' not in html
    assert 'class="gauge-solo"' not in html


@pytest.mark.render
async def test_full_render_produces_image(render_guard):
    pytest.importorskip("playwright.async_api")

    from nonebot_plugin_status_zmd.render import render_model
    from nonebot_plugin_status_zmd.render.backend import probe

    available, detail = probe()
    if not available:
        pytest.skip(detail)

    model = make_model(
        gauge=make_gauge(),
        perf=[make_perf()],
        blocks={"header", "gauge", "perf", "footer"},
    )
    try:
        image = await render_model(model)
    except Exception as e:
        render_guard(e)
        raise
    assert image[:3] == b"\xff\xd8\xff"  # JPEG 魔数
    assert len(image) > 20_000
