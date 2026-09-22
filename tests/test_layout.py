"""布局回归：长图不能横向溢出，关键元素的几何与配色要对得上设计稿。

只有 Playwright 会真正排版，所以这里的断言都放在浏览器里跑。
"""

from __future__ import annotations

import pytest

from nonebot_plugin_status_zmd.render.backend import new_page
from nonebot_plugin_status_zmd.render.model import VIEWPORT_WIDTH, AppRow

from .test_render_html import make_gauge, make_model, make_perf

AUDIT_JS = """() => {
  const box = (sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const b = el.getBoundingClientRect();
    return [Math.round(b.x), Math.round(b.y), Math.round(b.width), Math.round(b.height)];
  };
  const overflow = [...document.querySelectorAll('.page *')]
    .filter((el) => el.getBoundingClientRect().right > 1177)
    .map((el) => (el.className || el.tagName) + '@' + Math.round(el.getBoundingClientRect().right));
  const scroll = [...document.querySelectorAll('.page *')]
    .filter((el) => el.scrollWidth > el.clientWidth + 2 && el.tagName !== 'BODY')
    .map((el) => String(el.className) + ' sw=' + el.scrollWidth);
  return {
    docW: document.documentElement.scrollWidth,
    docH: document.documentElement.scrollHeight,
    bodyBg: getComputedStyle(document.body).backgroundColor,
    dots: getComputedStyle(document.querySelector('.page')).backgroundSize,
    gauge: box('.gauge-stage'),
    boxActual: box('.box-actual'),
    boxMax: box('.box-max'),
    apps: box('.apps-panel'),
    bots: box('.bots-panel'),
    chart: box('.chart-cell'),
    bars: document.querySelectorAll('.perf-row .bars').length,
    firstRowBars: document.querySelectorAll('.perf-row .bar').length,
    barMinH: (() => {
      const el = document.querySelector('.bar');
      return el ? getComputedStyle(el).minHeight : null;
    })(),
    ringStroke: getComputedStyle(document.querySelector('path[stroke="#ffe23d"]')).stroke,
    discFill: getComputedStyle(document.querySelector('circle[fill="#ededea"]')).fill,
    centerText: ['of', 'uptime', 'uptime-sub'].reduce((acc, cls) => {
      const el = document.querySelector('.gauge-center .' + cls);
      acc[cls] = el ? getComputedStyle(el).color : null;
      return acc;
    }, {}),
    iconClass: document.querySelector('.svg-ic') ? 'svg-ic' : null,
    oldIconClass: document.querySelector('svg.ic') ? 'svg.ic' : null,
    overflow,
    scroll,
  };
}"""


def _channel(value: float) -> float:
    c = value / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def contrast_ratio(foreground: str, background: str) -> float:
    """WCAG 对比度，入参形如 ``rgb(99, 99, 93)`` 或 ``#63635d``。"""

    def luminance(color: str) -> float:
        if color.startswith("#"):
            rgb = [int(color[i : i + 2], 16) for i in (1, 3, 5)]
        else:
            inner = color[color.index("(") + 1 : color.index(")")]
            rgb = [float(p) for p in inner.split(",")[:3]]
        return (
            0.2126 * _channel(rgb[0])
            + 0.7152 * _channel(rgb[1])
            + 0.0722 * _channel(rgb[2])
        )

    first, second = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (first + 0.05) / (second + 0.05)


async def audit(model, render_guard) -> dict:
    pytest.importorskip("playwright.async_api")
    from nonebot_plugin_status_zmd.render.env import build_html

    html = await build_html(model)
    try:
        async with new_page(
            viewport={"width": VIEWPORT_WIDTH, "height": 900},
            device_scale_factor=1,
            locale="zh-CN",
        ) as page:
            await page.set_content(html, wait_until="load")
            await page.wait_for_function("document.body.classList.contains('done')")
            return await page.evaluate(AUDIT_JS)
    except Exception as e:
        render_guard(e)
        raise


def full_model():
    return make_model(
        gauge=make_gauge(),
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
        perf=[make_perf()],
        blocks={"header", "gauge", "apps", "bots", "perf", "specs", "footer"},
    )


@pytest.mark.render
async def test_no_horizontal_overflow(render_guard):
    report = await audit(full_model(), render_guard)
    assert report["docW"] == VIEWPORT_WIDTH
    assert report["overflow"] == []
    assert report["scroll"] == []


@pytest.mark.render
async def test_design_tokens_are_applied(render_guard):
    report = await audit(full_model(), render_guard)
    assert report["bodyBg"] == "rgb(236, 236, 235)"  # --bg
    assert report["dots"] == "18px 18px"  # 点阵底纹
    assert report["ringStroke"] == "rgb(255, 226, 61)"  # --yellow 进度弧
    assert report["barMinH"] == "2px"  # 极小值也留可见的柱子


@pytest.mark.render
async def test_gauge_geometry(render_guard):
    report = await audit(full_model(), render_guard)
    # 电量环 470×470，数据块分别贴右上与左下
    assert report["gauge"][2:] == [470, 470]
    assert report["boxActual"][0] > report["gauge"][0] + 200
    assert report["boxActual"][1] < report["gauge"][1] + 60
    assert report["boxMax"][0] < report["gauge"][0] + 60
    assert report["boxMax"][1] > report["gauge"][1] + 300
    # 右栏在环的右边
    assert report["apps"][0] >= report["gauge"][0] + 470


@pytest.mark.render
async def test_perf_chart_geometry(render_guard):
    report = await audit(full_model(), render_guard)
    assert report["bars"] == 1
    assert report["firstRowBars"] == 3  # make_perf 只给了 3 个历史点
    assert report["chart"][3] == 66  # .chart-cell 固定 66px
    assert report["chart"][2] > 400


@pytest.mark.render
async def test_gauge_center_text_contrast(render_guard):
    """中心文字压在粒子点云上，颜色要够深：对圆盘底色的 WCAG 对比度不低于 4.5。

    点云本身比圆盘略深，所以这里对圆盘测出来的余量就是点云上的余量。
    """
    report = await audit(full_model(), render_guard)
    for cls, color in report["centerText"].items():
        assert color, cls
        ratio = contrast_ratio(color, report["discFill"])
        assert ratio >= 4.5, (
            f"{cls} 对比度 {ratio:.2f} 偏低（{color} on {report['discFill']}）"
        )


@pytest.mark.render
async def test_icon_classes_do_not_collide(render_guard):
    report = await audit(full_model(), render_guard)
    # 图标 SVG 用 svg-ic，避免和承载图标的深色圆圈 .ic 撞样式
    assert report["iconClass"] == "svg-ic"
    assert report["oldIconClass"] is None
