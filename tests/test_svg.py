"""SVG 部件：几何、可复现性与边界。"""

from __future__ import annotations

from nonebot_plugin_status_zmd.render.svg import (
    BLOB_DOT_COLOR,
    BLOB_POINTS,
    CX,
    CY,
    arc_path,
    blob_svg,
    gauge_svg,
    polar,
    stripes,
)


def test_polar_origin_is_twelve_oclock():
    assert polar(CX, CY, 100, 0) == (CX, CY - 100)
    x, y = polar(CX, CY, 100, 90)
    assert round(x) == round(CX + 100)
    assert round(y) == round(CY)
    x, y = polar(CX, CY, 100, 180)
    assert round(x) == round(CX)
    assert round(y) == round(CY + 100)


def test_arc_path_flags():
    # 小于 180° 时 large-arc-flag 为 0
    assert "A 150 150 0 0 1" in arc_path(CX, CY, 150, 0, 90)
    # 大于 180° 时为 1
    assert "A 150 150 0 1 1" in arc_path(CX, CY, 150, 0, 270)
    # 跨越 0° 时自动补 360°
    assert arc_path(CX, CY, 150, 350, 10)


def test_stripes_are_reproducible():
    first = stripes("#ecb063", 270, 360, seed=31)
    second = stripes("#ecb063", 270, 360, seed=31)
    assert first == second
    assert first != stripes("#ecb063", 270, 360, seed=97)


def test_stripes_density_and_color():
    markup = stripes("#7fb2cc", 90, 180, seed=97)
    count = markup.count("<path")
    # 90° 扇区里应该有几十条楔形，不能空也不能爆炸
    assert 20 < count < 400
    assert "hsl(" in markup
    assert "nan" not in markup.lower()


def test_blob_is_reproducible_and_bounded():
    import math
    import re

    markup = blob_svg()
    assert markup == blob_svg()

    dots = re.findall(r'<circle cx="([-\d.]+)" cy="([-\d.]+)" r="([\d.]+)"', markup)
    assert len(dots) == BLOB_POINTS
    assert "nan" not in markup.lower()

    center = 290 / 2
    for raw_x, raw_y, raw_r in dots:
        x, y, radius = float(raw_x), float(raw_y), float(raw_r)
        # 点必须在画布内，且整体收在内盘半径 126 之内，否则会压到黄环上
        assert 0 <= x <= 290
        assert 0 <= y <= 290
        assert 0.7 <= radius <= 1.9
        assert math.hypot(x - center, y - center) <= 130


def test_blob_dots_stay_light():
    """点云铺在中心文字底下，颜色必须留在浅色区间（太深会糊住数字与运行时间）。"""
    r, g, b = (int(BLOB_DOT_COLOR[i : i + 2], 16) for i in (1, 3, 5))
    assert (r + g + b) / 3 >= 160
    assert f'fill="{BLOB_DOT_COLOR}"' in blob_svg()


def test_gauge_svg_contents():
    markup = gauge_svg(50.0)
    for color in ("#cfcfc9", "#ecb063", "#7fb2cc", "#ededea", "#ffe23d"):
        assert color in markup
    # 进度弧只有一条，且带圆头
    assert markup.count('stroke="#ffe23d"') == 1
    assert 'stroke-linecap="round"' in markup
    assert "nan" not in markup.lower()


def test_gauge_svg_maps_percent_to_sweep():
    assert gauge_svg(0) != gauge_svg(100)
    # 0% 也要留 0.5° 让圆头端点可见，100% 不超过 359.5°
    assert arc_path(CX, CY, 150, 0, 0.5) in gauge_svg(0)
    assert arc_path(CX, CY, 150, 0, 359.5) in gauge_svg(100)
    # 超出范围的值被夹住
    assert arc_path(CX, CY, 150, 0, 359.5) in gauge_svg(300)
    assert arc_path(CX, CY, 150, 0, 0.5) in gauge_svg(-10)
