"""生成固定帧的电量环 SVG。几何层与纹理采样分开，便于保持画面可复现。"""

from __future__ import annotations

import colorsys
import math
from collections.abc import Iterator

GAUGE_SIZE = 470
CX = CY = 235.0

# 两段装饰弧分别使用错位的纹理栅格，避免镜像般的重复。
_DECORATIONS = (
    (270.0, 360.0, "#ecb063", 0),
    (90.0, 180.0, "#7fb2cc", 23),
)
_COLLAR = "#cfcfc9"
_DISC = "#ededea"
_BLOB_DOT = "#a8a8a1"
_BACK = "#d3d3ce"
_TRACK = "#f2edc4"
_PROGRESS = "#ffe23d"


def _radical_inverse(index: int, base: int) -> float:
    """把整数的进制位反转为 [0, 1) 小数，供二维均匀取样。"""
    fraction = 1.0 / base
    value = 0.0
    while index:
        index, digit = divmod(index, base)
        value += digit * fraction
        fraction /= base
    return value


def polar(cx: float, cy: float, radius: float, deg: float) -> tuple[float, float]:
    angle = math.radians(deg - 90)
    return cx + radius * math.cos(angle), cy + radius * math.sin(angle)


def _arc(radius: float, start: float, stop: float) -> str:
    destination = stop + 360 if stop < start else stop
    begin_x, begin_y = polar(CX, CY, radius, start)
    end_x, end_y = polar(CX, CY, radius, destination)
    long_way = int(destination - start > 180)
    return (
        f"M {begin_x:.2f} {begin_y:.2f} A {radius} {radius} 0 "
        f"{long_way} 1 {end_x:.2f} {end_y:.2f}"
    )


def _stroke(radius: float, start: float, stop: float, color: str, width: int) -> str:
    return (
        f'<path d="{_arc(radius, start, stop)}" fill="none" '
        f'stroke="{color}" stroke-width="{width}"/>'
    )


def _stripe_geometry(start: float, stop: float) -> str:
    corners = (
        polar(CX, CY, radius, angle)
        for angle, radius in (
            (start, 189.0),
            (start, 215.0),
            (stop, 215.0),
            (stop, 189.0),
        )
    )
    points = [f"{x:.2f} {y:.2f}" for x, y in corners]
    return f"M {points[0]} L {points[1]} L {points[2]} L {points[3]} Z"


def _stripes(start: float, stop: float, color: str, offset: int) -> str:
    rgb = tuple(int(color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    hue, lightness, saturation = colorsys.rgb_to_hls(*rgb)
    pieces: list[str] = []
    # 把弧切为近似均匀的小格，再用不同进制的序列错开位置、宽度和颜色。
    # 与逐条抽取随机宽度/间距不同，格数和覆盖密度不随采样波动。
    slots = 81
    cell = (stop - start - 2) / slots
    for index in range(slots):
        sample = index + offset + 1
        angle = start + 1 + (index + 0.12 + _radical_inverse(sample, 2) * 0.48) * cell
        width = (0.26 + _radical_inverse(sample, 3) * 0.62) * cell
        next_angle = min(angle + width, stop - 0.5)
        if next_angle <= angle:
            continue
        shade = min(
            88.0,
            max(30.0, lightness * 100 + (_radical_inverse(sample, 5) - 0.5) * 14),
        )
        tint = min(
            96.0,
            max(24.0, saturation * 100 + (_radical_inverse(sample, 7) - 0.5) * 10),
        )
        pieces.append(
            f'<path d="{_stripe_geometry(angle, next_angle)}" '
            f'fill="hsl({hue * 360:.0f},{tint:.0f}%,{shade:.0f}%)"/>'
        )
    return "".join(pieces)


def _particle_positions() -> Iterator[tuple[float, float, float]]:
    # 球面等面积映射：纬度用二进制反位序，经度用三进制反位序。
    # 采用非相邻的索引错位两轴，避免球上出现螺旋带状轨迹。
    for index in range(1, 651):
        latitude = 1 - 2 * _radical_inverse(index, 2)
        longitude = math.tau * _radical_inverse(index + 37, 3)
        parallel = math.sqrt(max(0.0, 1 - latitude * latitude))
        yield latitude, parallel * math.cos(longitude), parallel * math.sin(longitude)


def _blob(phase_t: float) -> str:
    breath = 0.5 + 0.5 * math.sin(phase_t * 0.9)
    rotation_cos, rotation_sin = math.cos(0.35), math.sin(0.35)
    circles: list[str] = []
    for index, (y, x, z) in enumerate(_particle_positions(), start=1):
        # 低频空间波纹只改变轮廓的细节，不改变球面上点的密度。
        ripple = 0.55 * math.sin(5 * x + 4 * y + phase_t * 0.3)
        ripple += 0.45 * math.cos(6 * z - 3 * y - phase_t * 0.2)
        fine = _radical_inverse(index + 11, 5) - 0.5
        distance = 126 * (0.79 + 0.12 * breath + 0.045 * ripple + 0.035 * fine)
        projected_x = x * rotation_cos - z * rotation_sin
        depth = (x * rotation_sin + z * rotation_cos + 1) / 2
        circles.append(
            f'<circle cx="{145 + projected_x * distance:.1f}" '
            f'cy="{145 + y * distance:.1f}" '
            f'r="{0.7 + depth * 1.2:.2f}" '
            f'fill="{_BLOB_DOT}" fill-opacity="{0.10 + depth * 0.40:.2f}"/>'
        )
    return (
        '<svg x="90" y="90" width="290" height="290" '
        f'viewBox="0 0 290 290">{"".join(circles)}</svg>'
    )


def _shell() -> Iterator[str]:
    # 描边先于底弧，纹理覆于底弧；中心的圆盘最后遮住纹理内缘。
    for start, stop, _, _ in _DECORATIONS:
        for radius in (221, 183):
            yield _stroke(radius, start, stop, _COLLAR, 3)
    for start, stop, color, _ in _DECORATIONS:
        yield _stroke(202, start, stop, color, 28)
    for start, stop, color, seed in _DECORATIONS:
        yield f"<g>{_stripes(start, stop, color, seed)}</g>"
    yield f'<circle cx="{CX}" cy="{CY}" r="126" fill="{_DISC}"/>'


def gauge_svg(percent: float, *, blob_phase: float = 0.0) -> str:
    """占用百分比对应的静态画面；正角度自 12 点顺时针量取。"""
    sweep = min(359.5, max(0.5, percent * 3.6))
    layers = [
        f'<svg class="gauge-svg" width="{GAUGE_SIZE}" height="{GAUGE_SIZE}" '
        f'viewBox="0 0 {GAUGE_SIZE} {GAUGE_SIZE}" '
        f'xmlns="http://www.w3.org/2000/svg">',
        *_shell(),
        _blob(blob_phase),
        f'<circle cx="{CX}" cy="{CY}" r="151" fill="none" '
        f'stroke="{_BACK}" stroke-width="24"/>',
        f'<circle cx="{CX}" cy="{CY}" r="150" fill="none" '
        f'stroke="{_TRACK}" stroke-width="18"/>',
        f'<path d="{_arc(150, 0, sweep)}" fill="none" '
        f'stroke="{_PROGRESS}" stroke-width="18" '
        f'stroke-linecap="round" '
        f'style="filter:drop-shadow(0 0 7px rgba(255,224,70,.5))"/>',
        "</svg>",
    ]
    return "".join(layers)
