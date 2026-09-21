"""localstore 缓存目录与头像缓存。"""

from __future__ import annotations

import pytest

from nonebot_plugin_status_zmd import storage

JPEG = b"\xff\xd8\xff\xe0hello"


@pytest.fixture()
def temp_cache(tmp_path, monkeypatch):
    """把缓存根指到临时目录，并清掉 lru_cache。"""
    monkeypatch.setattr(storage, "FALLBACK_CACHE_DIR", tmp_path)
    storage.cache_dir.cache_clear()
    yield tmp_path
    storage.cache_dir.cache_clear()


def test_cache_dir_falls_back_outside_plugin_context(temp_cache):
    # 测试不在插件加载上下文里，localstore 认不出调用者 → 退回临时目录
    assert storage.cache_dir() == temp_cache


def test_cache_dir_is_cached(temp_cache):
    assert storage.cache_dir() is storage.cache_dir()


async def test_avatar_roundtrip(temp_cache):
    assert await storage.read_avatar("10001") is None

    await storage.write_avatar("10001", JPEG)
    assert await storage.read_avatar("10001") == JPEG
    assert (temp_cache / "avatar" / "10001").is_file()


async def test_avatar_expires(temp_cache, monkeypatch):
    await storage.write_avatar("10001", JPEG)
    # 负 TTL 保证一定判定为过期（文件的 mtime 可能略大于 time.time()）
    monkeypatch.setattr(storage, "AVATAR_TTL", -1)
    assert await storage.read_avatar("10001") is None


async def test_avatar_size_limit(temp_cache):
    await storage.write_avatar("10002", b"x" * (storage.AVATAR_MAX_BYTES + 1))
    assert await storage.read_avatar("10002") is None

    await storage.write_avatar("10003", b"")
    assert await storage.read_avatar("10003") is None


async def test_avatar_id_is_escaped(temp_cache):
    # self_id 来自适配器，不能让路径分隔符逃出缓存目录
    await storage.write_avatar("../evil", JPEG)
    written = [p.name for p in (temp_cache / "avatar").iterdir()]
    assert written == [".._evil"]


def test_write_debug_html(temp_cache):
    path = storage.write_debug_html("<html>debug</html>", "case")
    assert path == temp_cache / "case.html"
    assert path.read_text(encoding="u8") == "<html>debug</html>"
