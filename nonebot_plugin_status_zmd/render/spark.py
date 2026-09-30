"""将设备历史序列绘制成可直接截图的双指标折线图。"""

from __future__ import annotations

from html import escape
from math import isfinite

from .model import PerfRow

WIDTH = 500
HEIGHT = 66
TOP = 11
BOTTOM = 3
PLOT_HEIGHT = HEIGHT - TOP - BOTTOM
COLORS = ("#ded24e", "#3ba3dc")


def _axis(values: list[float], unit: str) -> float:
    if not values:
        return 100.0 if unit == "%" else 1.0
    peak = max((value for value in values if isfinite(value)), default=0.0)
    top = max(1.0 if unit == "%" else 0.01, peak * 1.2)
    return min(top, 100.0) if unit == "%" else top


def _label(value: float, unit: str) -> str:
    if value >= 100:
        number = f"{value:.0f}"
    elif value >= 10:
        number = f"{value:.1f}"
    else:
        number = f"{value:.2f}"
    return escape(number + unit)


def _points(
    values: list[float], ceiling: float, slots: int
) -> list[tuple[float, float]]:
    visible = values[-slots:]
    offset = slots - len(visible)
    return [
        (
            (offset + index) * WIDTH / max(1, slots - 1),
            TOP + PLOT_HEIGHT * (1 - min(max(value, 0.0), ceiling) / ceiling),
        )
        for index, value in enumerate(visible)
    ]


def _series(points: list[tuple[float, float]], color: str, suffix: str) -> str:
    if not points:
        return ""
    end_x, end_y = points[-1]
    tip = f'<circle cx="{end_x:.2f}" cy="{end_y:.2f}" r="2.4" fill="{color}"/>'
    if len(points) == 1:
        return tip
    line = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    first_x = points[0][0]
    area = f"{first_x:.2f},{HEIGHT} {line} {end_x:.2f},{HEIGHT}"
    return (
        f'<polygon points="{area}" fill="url(#{suffix})"/>'
        f'<polyline points="{line}" fill="none" stroke="{color}" '
        'stroke-width="3.4" stroke-opacity=".27" stroke-linejoin="round" '
        'stroke-linecap="round" vector-effect="non-scaling-stroke"/>'
        f'<polyline points="{line}" fill="none" stroke="{color}" '
        'stroke-width="1.6" stroke-linejoin="round" '
        'stroke-linecap="round" vector-effect="non-scaling-stroke"/>' + tip
    )


def spark_svg(row: PerfRow, slots: int, index: int = 0) -> str:
    slots = max(2, slots)
    left_values = row.hist[-slots:]
    right_values = row.hist2[-slots:]
    shared_values = left_values if row.dual_axis else left_values + right_values
    left_max = _axis(shared_values, row.axis_unit1)
    right_max = _axis(right_values, row.axis_unit2) if row.dual_axis else left_max
    left = _points(left_values, left_max, slots)
    right = _points(right_values, right_max, slots)
    yellow_id = f"trend-yellow-{index}"
    blue_id = f"trend-blue-{index}"
    return (
        '<svg class="trend-svg" xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" preserveAspectRatio="none" role="img" '
        f'aria-label="{escape(row.cur1_label)}与{escape(row.cur2_label)}走势">'
        "<defs>"
        f'<linearGradient id="{blue_id}" x1="0" y1="0" x2="0" y2="1">'
        '<stop stop-color="#3ba3dc" stop-opacity=".31"/>'
        '<stop offset="1" stop-color="#3ba3dc" stop-opacity=".03"/>'
        "</linearGradient>"
        f'<linearGradient id="{yellow_id}" x1="0" y1="0" x2="0" y2="1">'
        '<stop stop-color="#ded24e" stop-opacity=".38"/>'
        '<stop offset="1" stop-color="#ded24e" stop-opacity=".04"/>'
        "</linearGradient>"
        "</defs>"
        f'<line x1="0" y1="{TOP + PLOT_HEIGHT / 2:.0f}" x2="{WIDTH}" '
        f'y2="{TOP + PLOT_HEIGHT / 2:.0f}" stroke="#b9b9b4"/>'
        + _series(right, COLORS[1], blue_id)
        + _series(left, COLORS[0], yellow_id)
        + f'<text x="9" y="9" fill="#2c2c2a" font-size="10">'
        f'<tspan fill="{COLORS[0]}">●</tspan> {_label(left_max, row.axis_unit1)}</text>'
        + f'<text x="9" y="{HEIGHT - 3}" fill="#2c2c2a" font-size="10">'
        f'<tspan fill="{COLORS[0]}">●</tspan> {_label(0, row.axis_unit1)}</text>'
        + (
            f'<text x="{WIDTH - 3}" y="9" text-anchor="end" '
            'fill="#2c2c2a" font-size="10">'
            f"{_label(right_max, row.axis_unit2)} "
            f'<tspan fill="{COLORS[1]}">●</tspan></text>'
            f'<text x="{WIDTH - 3}" y="{HEIGHT - 3}" text-anchor="end" '
            f'fill="#2c2c2a" font-size="10">{_label(0, row.axis_unit2)} '
            f'<tspan fill="{COLORS[1]}">●</tspan></text>'
            if row.dual_axis
            else ""
        )
        + "</svg>"
    )
