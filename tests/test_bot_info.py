"""Bot 信息缓存：成功要缓存，失败要节流（不能每条指令都重试一次超时）。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from nonebot_plugin_status_zmd import bot_info, storage
from nonebot_plugin_status_zmd.utils import bytes_to_data_uri

JPEG = b"\xff\xd8\xff\xe0jpg"


class FakeAdapter:
    def __init__(self, name: str = "Telegram") -> None:
        self._name = name

    def get_name(self) -> str:
        return self._name


class FakeBot:
    def __init__(self, self_id: str, adapter: str = "Telegram") -> None:
        self.self_id = self_id
        self.adapter = FakeAdapter(adapter)


async def _async_value(value):
    return value


@pytest.fixture()
def clean_meta_state(tmp_path, monkeypatch):
    """清内存缓存，并把 localstore 缓存根指到临时目录。"""
    bot_info._bot_meta.clear()
    bot_info._meta_attempted.clear()
    monkeypatch.setattr(storage, "FALLBACK_CACHE_DIR", tmp_path / "cache")
    storage.cache_dir.cache_clear()
    yield tmp_path / "cache"
    bot_info._bot_meta.clear()
    bot_info._meta_attempted.clear()
    storage.cache_dir.cache_clear()


@pytest.mark.usefixtures("clean_meta_state")
async def test_success_is_cached(monkeypatch):
    user = SimpleNamespace(name="终末地终端", avatar=None)
    monkeypatch.setattr(
        bot_info,
        "get_interface",
        lambda _bot: SimpleNamespace(get_user=lambda _id: _async_value(user)),
    )

    bot = FakeBot("10001")
    await bot_info._load_bot_meta(bot)
    assert bot_info._bot_meta["10001"] == ("终末地终端", None)

    # 命中缓存后不再触发任何请求
    monkeypatch.setattr(
        bot_info,
        "get_interface",
        lambda _bot: pytest.fail("命中缓存后不应再次请求 Bot 信息"),
    )
    await bot_info._load_bot_meta(bot)


@pytest.mark.usefixtures("clean_meta_state")
async def test_failure_is_throttled(monkeypatch):
    calls = {"n": 0}

    def raising_interface(_bot):
        calls["n"] += 1
        raise RuntimeError("模拟适配器不支持 get_login_info")

    monkeypatch.setattr(bot_info, "get_interface", raising_interface)

    bot = FakeBot("10002")
    await bot_info._load_bot_meta(bot)
    assert calls["n"] == 1
    # 拿不到就别缓存，否则永远重试不了
    assert "10002" not in bot_info._bot_meta

    # 重试间隔内直接跳过，不再白等一次 API 超时
    await bot_info._load_bot_meta(bot)
    assert calls["n"] == 1

    # 过了间隔才重试
    monkeypatch.setattr(bot_info, "META_RETRY_INTERVAL", 0.0)
    await bot_info._load_bot_meta(bot)
    assert calls["n"] == 2


@pytest.mark.usefixtures("clean_meta_state")
async def test_prime_bot_meta_skips_requests(monkeypatch):
    monkeypatch.setattr(
        bot_info,
        "get_interface",
        lambda _bot: pytest.fail("注入过信息就不该再请求"),
    )
    bot_info.prime_bot_meta("10003", "注入的昵称")
    await bot_info._load_bot_meta(FakeBot("10003"))
    assert bot_info._bot_meta["10003"] == ("注入的昵称", None)


@pytest.mark.usefixtures("clean_meta_state")
async def test_onebot_fallback_url_is_used(monkeypatch):
    fetched: list[str] = []

    async def fake_fetch(url: str):
        fetched.append(url)
        return JPEG

    monkeypatch.setattr(bot_info, "_fetch_avatar", fake_fetch)
    monkeypatch.setattr(bot_info, "get_interface", lambda _bot: None)

    await bot_info._load_bot_meta(FakeBot("10004", adapter="OneBot V11"))
    assert fetched == ["https://q.qlogo.cn/headimg_dl?dst_uin=10004&spec=160"]
    assert bot_info._bot_meta["10004"][1] == bytes_to_data_uri(JPEG)


@pytest.mark.usefixtures("clean_meta_state")
async def test_avatar_is_written_to_localstore_cache(clean_meta_state, monkeypatch):
    async def fake_fetch(url: str):
        return JPEG

    monkeypatch.setattr(bot_info, "_fetch_avatar", fake_fetch)
    monkeypatch.setattr(bot_info, "get_interface", lambda _bot: None)

    await bot_info._load_bot_meta(FakeBot("10006", adapter="OneBot V11"))
    assert (clean_meta_state / "avatar" / "10006").read_bytes() == JPEG


@pytest.mark.usefixtures("clean_meta_state")
async def test_avatar_cache_hit_skips_network(clean_meta_state, monkeypatch):
    await storage.write_avatar("10007", JPEG)

    async def fail_fetch(url: str):
        pytest.fail("命中 localstore 缓存后不应再拉网络")

    monkeypatch.setattr(bot_info, "_fetch_avatar", fail_fetch)
    monkeypatch.setattr(bot_info, "get_interface", lambda _bot: None)

    await bot_info._load_bot_meta(FakeBot("10007", adapter="OneBot V11"))
    assert bot_info._bot_meta["10007"][1] == bytes_to_data_uri(JPEG)


@pytest.mark.usefixtures("clean_meta_state")
async def test_avatar_disabled_by_config(monkeypatch, restore_config):
    async def fake_fetch(url: str):
        pytest.fail("关掉头像开关后不应发起请求")

    restore_config.stzmd_show_bot_avatar = False
    monkeypatch.setattr(bot_info, "_fetch_avatar", fake_fetch)
    monkeypatch.setattr(bot_info, "get_interface", lambda _bot: None)

    await bot_info._load_bot_meta(FakeBot("10005", adapter="OneBot V11"))
    assert "10005" not in bot_info._bot_meta  # 什么都没拿到，留给下次
