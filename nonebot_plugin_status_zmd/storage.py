"""由 nonebot-plugin-localstore 管理的缓存目录。

目录解析方式与 nonebot-plugin-aigf 保持一致（``require`` 后取 localstore 的
缓存目录）。缓存里放两类可再生数据：

- ``avatar/<self_id>``：Bot 头像原图，避免每次重启都重新拉一遍网络
- ``render_debug.html``：渲染失败时落盘的 HTML，便于定位样式问题

测试与 ``tools/preview.py`` 不在插件加载上下文里，localstore 靠调用栈认不出
调用者，这时退回系统临时目录，保证模块在任何上下文都能导入。
"""

from __future__ import annotations

import tempfile
import time
from functools import lru_cache
from pathlib import Path

import anyio
import nonebot_plugin_localstore as store

#: 头像缓存有效期（秒），过期后重新拉取
AVATAR_TTL = 7 * 86400
#: 头像最大字节数，超过就不落盘（防止异常大的图写爆缓存）
AVATAR_MAX_BYTES = 512 * 1024

AVATAR_SUBDIR = "avatar"
FALLBACK_CACHE_DIR = Path(tempfile.gettempdir()) / "nonebot_plugin_status_zmd"


@lru_cache(maxsize=1)
def cache_dir() -> Path:
    """缓存根目录（``<localstore cache>/nonebot_plugin_status_zmd``）。"""
    try:
        return store.get_plugin_cache_dir()
    except RuntimeError:
        # 非插件加载上下文：localstore 无法识别调用者
        FALLBACK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        return FALLBACK_CACHE_DIR


def avatar_dir() -> Path:
    path = cache_dir() / AVATAR_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _avatar_path(self_id: str) -> Path:
    # self_id 来自适配器，转义掉可能的路径分隔符
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in self_id)
    return avatar_dir() / safe


async def read_avatar(self_id: str) -> bytes | None:
    """读缓存的头像原图；不存在或已过期返回 None。"""
    path = anyio.Path(_avatar_path(self_id))
    try:
        if not await path.is_file():
            return None
        stat = await path.stat()
        if time.time() - stat.st_mtime > AVATAR_TTL:
            return None
        return await path.read_bytes()
    except OSError:
        return None


async def write_avatar(self_id: str, data: bytes) -> None:
    if not data or len(data) > AVATAR_MAX_BYTES:
        return
    try:
        await anyio.Path(_avatar_path(self_id)).write_bytes(data)
    except OSError:
        return  # 缓存写失败不影响出图


def write_debug_html(html: str, name: str = "render_debug") -> Path:
    """渲染失败时把 HTML 落到缓存目录，便于本地排查。"""
    path = cache_dir() / f"{name}.html"
    path.write_text(html, encoding="u8")
    return path
