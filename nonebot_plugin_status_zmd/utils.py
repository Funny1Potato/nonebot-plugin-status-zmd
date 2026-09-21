"""格式化、字体探测与异步辅助工具。"""

from __future__ import annotations

import base64
import functools
import platform
import re
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, TypeVar

import anyio

from .config import cache_dir

T = TypeVar("T")

# region 数值格式化

_BYTE_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


def human_bytes(value: float, *, precision: int = 1) -> str:
    """1024 进制的人类可读字节量，如 ``9.8 GB``。"""
    sign = "-" if value < 0 else ""
    value = abs(float(value))
    index = 0
    while value >= 1024 and index < len(_BYTE_UNITS) - 1:
        value /= 1024
        index += 1
    digits = 0 if index == 0 else precision
    return f"{sign}{value:.{digits}f} {_BYTE_UNITS[index]}"


def human_bytes_pair(used: float, total: float, *, precision: int = 1) -> str:
    """把单位提到末尾的成对字节量，如 ``1.2 / 8.0 GB``。

    单位按总量选取，但若已用量会显示成 ``0.x`` 就退一档——``0.5 / 1.0 TB``
    把 486.2GB 压成了 0.5TB，精度丢得太多，退成 ``486.2 / 1024.0 GB`` 更接近
    参考实现的 ``486 / 1024 GB`` 口径。
    """
    if total <= 0:
        return f"{human_bytes(used, precision=precision)} / —"
    index = 0
    scaled_total = float(total)
    while scaled_total >= 1024 and index < len(_BYTE_UNITS) - 1:
        scaled_total /= 1024
        index += 1
    while index > 0 and scaled_total < 10 and used / 1024**index < 1:
        scaled_total *= 1024
        index -= 1
    factor = 1024**index
    digits = 0 if index == 0 else precision
    values = f"{used / factor:.{digits}f} / {scaled_total:.{digits}f}"
    return f"{values} {_BYTE_UNITS[index]}"


def format_bitrate(bytes_per_sec: float, *, precision: int = 1) -> str:
    """字节/秒转为比特率文本，如 ``12.4 Mbps``。"""
    bits = max(0.0, bytes_per_sec) * 8
    for scale, unit in ((1e9, "Gbps"), (1e6, "Mbps"), (1e3, "Kbps")):
        if bits >= scale:
            return f"{bits / scale:.{precision}f} {unit}"
    return f"{bits:.0f} bps"


def format_byterate(bytes_per_sec: float, *, precision: int = 0) -> str:
    """字节/秒文本，如 ``126 MB/s``。"""
    return f"{human_bytes(max(0.0, bytes_per_sec), precision=precision)}/s"


def format_duration(seconds: float) -> str:
    """时长文本，不足一天时只给 ``HH:MM:SS``。"""
    seconds = max(0, int(seconds))
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    clock = f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{days}天 {clock}" if days else clock


def format_freq(mhz: float | None) -> str:
    """频率文本，如 ``3.62 GHz``。"""
    if not mhz:
        return "—"
    if mhz >= 1000:
        return f"{mhz / 1000:.2f} GHz"
    return f"{mhz:.0f} MHz"


def format_percent(value: float, *, precision: int = 1) -> str:
    return f"{value:.{precision}f}%"


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


# endregion

# region 匹配与杂项


def match_any(patterns: Iterable[str], text: str) -> bool:
    """文本是否命中任一正则（非法正则按字面量处理）。"""
    for pattern in patterns:
        if not pattern:
            continue
        try:
            if re.search(pattern, text):
                return True
        except re.error:
            if pattern in text:
                return True
    return False


def first_str(*values: Any, default: str = "—") -> str:
    return next(
        (str(v) for v in values if v not in (None, "", [], {})),
        default,
    )


async def run_sync(func: Callable[..., T], *args: Any) -> T:
    """把阻塞调用丢进线程池，避免卡住事件循环。"""
    return await anyio.to_thread.run_sync(functools.partial(func, *args))


def write_debug_html(html: str, name: str = "render_debug") -> Path:
    """渲染失败时把 HTML 落到缓存目录，便于本地排查。"""
    path = cache_dir() / f"{name}.html"
    path.write_text(html, encoding="u8")
    return path


# endregion

# region 字体

#: 各平台可能的中文字体（族名, 文件路径），按优先级排列
CJK_FONT_CANDIDATES: dict[str, tuple[tuple[str, str], ...]] = {
    "Windows": (
        ("Microsoft YaHei", "C:/Windows/Fonts/msyh.ttc"),
        ("Microsoft YaHei", "C:/Windows/Fonts/msyh.ttf"),
        ("SimHei", "C:/Windows/Fonts/simhei.ttf"),
    ),
    "Darwin": (
        ("PingFang SC", "/System/Library/Fonts/PingFang.ttc"),
        ("Hiragino Sans GB", "/System/Library/Fonts/Hiragino Sans GB.ttc"),
    ),
    "Linux": (
        ("Noto Sans CJK SC", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        ("Noto Sans CJK SC", "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        (
            "Noto Sans CJK SC",
            "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
        ),
        ("Source Han Sans SC", "/usr/share/fonts/adobe-source-han-sans/Regular.otf"),
        ("WenQuanYi Micro Hei", "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
        (
            "Droid Sans Fallback",
            "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        ),
    ),
}

FONT_MIME = {
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".ttc": "font/collection",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}


def find_cjk_font() -> tuple[str, Path] | None:
    """探测系统里第一份可用的中文字体，返回（族名, 路径）。"""
    for family, raw_path in CJK_FONT_CANDIDATES.get(platform.system(), ()):
        path = Path(raw_path)
        if path.is_file():
            return family, path
    return None


def file_to_data_uri(path: Path) -> str | None:
    """把字体等小文件转成 data URI，便于内联进 HTML。"""
    if not path.is_file():
        return None
    mime = FONT_MIME.get(path.suffix.lower(), "application/octet-stream")
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{payload}"


def _sniff_image_mime(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def bytes_to_data_uri(data: bytes, mime: str | None = None) -> str:
    """图片字节转 data URI（自动嗅探格式）。"""
    resolved = mime or _sniff_image_mime(data)
    payload = base64.b64encode(data).decode("ascii")
    return f"data:{resolved};base64,{payload}"


# endregion
