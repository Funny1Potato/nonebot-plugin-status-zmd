"""服务端确定性生成的 SVG 部件：电量环、径向条纹、粒子点云。

原版终末地 UI 里这些是 canvas + JS 每帧重绘的，静态出图必须换成一次性生成、
可复现的 SVG。所有随机量都走固定种子的线性同余发生器，同一份输入永远得到
同一份输出。
"""

from __future__ import annotations

import math

#: 电量环画布尺寸与圆心（与 zmd-manager 的 470×470 / 圆心 235 对齐）
GAUGE_SIZE = 470
CX = CY = 235.0

OG_ARC = "#ecb063"  # 左上装饰弧：琥珀
BLUE_ARC = "#7fb2cc"  # 右下装饰弧：青蓝
RAIL_COLOR = "#cfcfc9"
DISC_COLOR = "#ededea"
RING_BACK_COLOR = "#d3d3ce"
RING_TRACK_COLOR = "#f2edc4"
RING_PROGRESS_COLOR = "#ffe23d"

#: 装饰弧角度区间（0° 指 12 点方向，顺时针为正）
ARC_LEFT = (270.0, 360.0)
ARC_RIGHT = (90.0, 180.0)

STRIPE_RI = 189.0
STRIPE_RO = 215.0

BLOB_SIZE = 290
BLOB_POINTS = 650


class _Lcg:
    """固定种子的线性同余发生器，替代 Math.random 保证可复现。"""

    def __init__(self, seed: int) -> None:
        self._state = seed

    def next(self) -> float:
        self._state = (self._state * 9301 + 49297) % 233280
        return self._state / 233280


def polar(cx: float, cy: float, radius: float, deg: float) -> tuple[float, float]:
    angle = math.radians(deg - 90)
    return cx + radius * math.cos(angle), cy + radius * math.sin(angle)


def arc_path(
    cx: float,
    cy: float,
    radius: float,
    start: float,
    end: float,
) -> str:
    if end < start:
        end += 360
    large = 1 if (end - start) > 180 else 0
    x1, y1 = polar(cx, cy, radius, start)
    x2, y2 = polar(cx, cy, radius, end)
    return f"M {x1:.2f} {y1:.2f} A {radius} {radius} 0 {large} 1 {x2:.2f} {y2:.2f}"


def _hex_to_hsl(hex_color: str) -> tuple[float, float, float]:
    r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    high, low = max(r, g, b), min(r, g, b)
    lightness = (high + low) / 2
    if high == low:
        return 0.0, 0.0, lightness * 100
    delta = high - low
    saturation = delta / (2 - high - low) if lightness > 0.5 else delta / (high + low)
    if high == r:
        hue = ((g - b) / delta + (6 if g < b else 0)) * 60
    elif high == g:
        hue = ((b - r) / delta + 2) * 60
    else:
        hue = ((r - g) / delta + 4) * 60
    return hue, saturation * 100, lightness * 100


def _wedge(cx: float, cy: float, ri: float, ro: float, start: float, end: float) -> str:
    x1, y1 = polar(cx, cy, ri, start)
    x2, y2 = polar(cx, cy, ro, start)
    x3, y3 = polar(cx, cy, ro, end)
    x4, y4 = polar(cx, cy, ri, end)
    return (
        f"M {x1:.2f} {y1:.2f} L {x2:.2f} {y2:.2f} "
        f"L {x3:.2f} {y3:.2f} L {x4:.2f} {y4:.2f} Z"
    )


def stripes(
    base_color: str,
    start: float,
    end: float,
    *,
    seed: int,
    ri: float = STRIPE_RI,
    ro: float = STRIPE_RO,
) -> str:
    """在角度区间内铺一层 HSL 微抖动的径向楔形条纹。"""
    rng = _Lcg(seed)
    hue, saturation, lightness = _hex_to_hsl(base_color)
    paths: list[str] = []

    angle = start + 1.0
    while angle < end - 1.0:
        width = 0.2 + rng.next() * 0.7
        gap = 0.25 + rng.next() * 1.4
        angle_end = angle + width
        if angle_end > end - 0.5:
            break
        light = min(88.0, max(30.0, lightness + (rng.next() - 0.5) * 14))
        sat = min(96.0, max(24.0, saturation + (rng.next() - 0.5) * 10))
        color = f"hsl({hue:.0f},{sat:.0f}%,{light:.0f}%)"
        paths.append(
            f'<path d="{_wedge(CX, CY, ri, ro, angle, angle_end)}" fill="{color}"/>',
        )
        angle = angle_end + gap

    return "".join(paths)


def blob_svg(*, seed: int = 7, phase_t: float = 0.0, rotation: float = 0.35) -> str:
    """粒子点云：斐波那契球面撒点 + 固定相位噪声，取动画的某一帧。

    对应原版的 650 点 canvas，点大小与透明度按景深 z 插值。
    """
    rng = _Lcg(seed)
    breath = 0.5 + 0.5 * math.sin(phase_t * 0.9)
    center = BLOB_SIZE / 2
    cos_rot, sin_rot = math.cos(rotation), math.sin(rotation)
    dots: list[str] = []

    for index in range(BLOB_POINTS):
        y = 1 - (index / (BLOB_POINTS - 1)) * 2
        ring = math.sqrt(max(0.0, 1 - y * y))
        theta = index * 2.39996
        phase = rng.next() * math.tau

        noise = (
            math.sin(theta * 1.7 + phase)
            * math.sin(y * 4.1 + phase * 1.3)
            * math.sin((theta + y) * 2.3 + phase * 0.7)
        )
        radius = 126 * (0.79 + 0.12 * breath + 0.09 * noise)

        x = math.cos(theta) * ring
        z = math.sin(theta) * ring
        rot_x = x * cos_rot - z * sin_rot
        rot_z = x * sin_rot + z * cos_rot

        depth = (rot_z + 1) / 2
        dots.append(
            f'<circle cx="{center + rot_x * radius:.1f}" '
            f'cy="{center + y * radius:.1f}" '
            f'r="{0.7 + depth * 1.2:.2f}" '
            f'fill="#60605c" fill-opacity="{0.10 + depth * 0.40:.2f}"/>',
        )

    return (
        f'<svg x="{(GAUGE_SIZE - BLOB_SIZE) / 2:.0f}" '
        f'y="{(GAUGE_SIZE - BLOB_SIZE) / 2:.0f}" '
        f'width="{BLOB_SIZE}" height="{BLOB_SIZE}" '
        f'viewBox="0 0 {BLOB_SIZE} {BLOB_SIZE}">{"".join(dots)}</svg>'
    )


#: 静态弧线只算一次：四条导轨（外/内 × 左/右）与两条装饰底弧
RAIL_ARCS: tuple[tuple[float, tuple[float, float]], ...] = (
    (221, ARC_LEFT),
    (183, ARC_LEFT),
    (221, ARC_RIGHT),
    (183, ARC_RIGHT),
)
BASE_ARCS: tuple[tuple[float, tuple[float, float], str], ...] = (
    (202, ARC_LEFT, OG_ARC),
    (202, ARC_RIGHT, BLUE_ARC),
)


def gauge_svg(percent: float, *, blob_phase: float = 0.0) -> str:
    """电量环。``percent`` 为 0-100 的综合占用，映射到 360° 扫角。"""
    sweep = min(359.5, max(0.5, percent * 3.6))

    parts = [
        f'<svg class="gauge-svg" width="{GAUGE_SIZE}" height="{GAUGE_SIZE}" '
        f'viewBox="0 0 {GAUGE_SIZE} {GAUGE_SIZE}" '
        f'xmlns="http://www.w3.org/2000/svg">',
    ]
    parts.extend(
        f'<path d="{arc_path(CX, CY, radius, start, end)}" fill="none" '
        f'stroke="{RAIL_COLOR}" stroke-width="3"/>'
        for radius, (start, end) in RAIL_ARCS
    )
    parts.extend(
        f'<path d="{arc_path(CX, CY, radius, start, end)}" fill="none" '
        f'stroke="{color}" stroke-width="28"/>'
        for radius, (start, end), color in BASE_ARCS
    )
    parts.extend(
        (
            f"<g>{stripes(OG_ARC, ARC_LEFT[0], ARC_LEFT[1], seed=31)}</g>",
            f"<g>{stripes(BLUE_ARC, ARC_RIGHT[0], ARC_RIGHT[1], seed=97)}</g>",
            f'<circle cx="{CX}" cy="{CY}" r="126" fill="{DISC_COLOR}"/>',
            blob_svg(phase_t=blob_phase),
            f'<circle cx="{CX}" cy="{CY}" r="151" fill="none" '
            f'stroke="{RING_BACK_COLOR}" stroke-width="24"/>',
            f'<circle cx="{CX}" cy="{CY}" r="150" fill="none" '
            f'stroke="{RING_TRACK_COLOR}" stroke-width="18"/>',
            f'<path d="{arc_path(CX, CY, 150, 0, sweep)}" fill="none" '
            f'stroke="{RING_PROGRESS_COLOR}" stroke-width="18" '
            f'stroke-linecap="round" '
            f'style="filter:drop-shadow(0 0 7px rgba(255,224,70,.5))"/>',
            "</svg>",
        ),
    )
    return "".join(parts)
