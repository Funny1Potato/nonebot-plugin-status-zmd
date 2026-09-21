"""NoneBot 自身状态：运行时长、Bot 连接时长、收发计数、Bot 列表与头像。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeVar

import httpx
import nonebot
from nonebot import get_driver, logger, require
from nonebot.adapters import Bot as BaseBot
from nonebot.adapters import Event as BaseEvent
from nonebot.message import event_preprocessor

from .config import config
from .utils import bytes_to_data_uri

require("nonebot_plugin_uninfo")

from nonebot_plugin_uninfo import get_interface  # noqa: E402

_K = TypeVar("_K")

nonebot_run_time: datetime = datetime.now().astimezone()

bot_connect_time: dict[str, datetime] = {}
recv_num: dict[str, int | None] = {}
send_num: dict[str, int | None] = {}


@dataclass
class BotStatus:
    self_id: str
    adapter: str
    nickname: str | None = None
    avatar: str | None = None  # data URI
    online: bool = False
    connect_time: datetime | None = None
    recv: int | None = None
    send: int | None = None


_bot_meta: dict[str, tuple[str | None, str | None]] = {}

#: 各适配器用于发送消息的 API 名。逐一列举才能准确判断「这条 API 调用是不是发消息」
SEND_APIS: dict[str, list[str] | Callable[[str], bool]] = {
    "Console": ["send_msg"],
    "Ding": ["send"],
    "Discord": ["create_message"],
    "EFChat": ["chat", "whisper"],
    "Feishu": ["im/v1/messages"],
    "Kook": ["message_create", "directMessage_create"],
    "Kaiheila": ["message_create", "directMessage_create"],
    "Kritor": ["send_message", "send_channel_message", "send_message_by_res_id"],
    "Milky": ["send_private_message", "send_group_message"],
    "Minecraft": ["send_msg"],
    "Mirai": ["send_friend_message", "send_group_message", "send_temp_message"],
    "OneBot V11": ["send_private_msg", "send_group_msg", "send_msg"],
    "OneBot V12": ["send_message"],
    "QQ": [
        "post_dms_messages",
        "post_messages",
        "post_c2c_messages",
        "post_group_messages",
    ],
    "RedProtocol": ["send_message", "send_fake_forward"],
    "Satori": ["message_create"],
    "Tailchat": ["chat.message.sendMessage"],
    "Telegram": lambda x: x.startswith("send_"),
    "ntchat": lambda x: x.startswith("send_"),
    "VoceChat": ["send_message"],
    "YunHu": ["bot/send", "bot/send-stream"],
}


def is_send_api(adapter: str, api: str) -> bool:
    entry = SEND_APIS.get(adapter)
    if entry is None:
        return False
    return api in entry if isinstance(entry, list) else entry(api)


def _count_add(counter: dict[_K, int | None], key: _K, value: int = 1) -> None:
    current = counter[key]
    counter[key] = (0 if current is None else current) + value


# region hooks


if config.zmd_count_message_sent:

    @BaseBot.on_called_api
    async def _count_send_by_api(
        bot: BaseBot,
        exc: Exception | None,
        api: str,
        _data: dict[str, Any],
        _result: Any,
    ) -> None:
        if (
            exc is None
            and bot.self_id in send_num
            and is_send_api(bot.adapter.get_name(), api)
        ):
            _count_add(send_num, bot.self_id)


@event_preprocessor
async def _count_message(bot: BaseBot, event: BaseEvent) -> None:
    if bot.self_id not in recv_num:
        return

    event_type = event.get_type()
    if event_type == "message":
        if event.get_user_id() == bot.self_id:
            if config.zmd_count_message_sent:
                _count_add(send_num, bot.self_id)
        else:
            _count_add(recv_num, bot.self_id)
    elif event_type == "message_sent" and config.zmd_count_message_sent:
        _count_add(send_num, bot.self_id)


driver = get_driver()


async def _fetch_avatar(url: str) -> str | None:
    try:
        async with httpx.AsyncClient(
            proxy=config.proxy,
            timeout=config.zmd_req_timeout,
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except Exception as e:  # noqa: BLE001
        logger.debug("获取 Bot 头像失败 {}: {}", url, e)
        return None
    return bytes_to_data_uri(resp.content)


async def _load_bot_meta(bot: BaseBot) -> None:
    if bot.self_id in _bot_meta:
        return

    nickname: str | None = None
    avatar: str | None = None
    try:
        interface = get_interface(bot)
        user = (await interface.get_user(bot.self_id)) if interface else None
    except Exception as e:  # noqa: BLE001
        logger.debug("获取 Bot 信息失败 {}: {}", bot.self_id, e)
        user = None

    if user is not None:
        nickname = user.name or None
        if user.avatar and config.zmd_show_bot_avatar:
            avatar = await _fetch_avatar(user.avatar)

    if (
        avatar is None
        and config.zmd_show_bot_avatar
        and bot.adapter.get_name()
        in {
            "OneBot V11",
            "Milky",
        }
    ):
        avatar = await _fetch_avatar(
            f"https://q.qlogo.cn/headimg_dl?dst_uin={bot.self_id}&spec=160",
        )

    _bot_meta[bot.self_id] = (nickname, avatar)


async def ensure_bot_meta(bots: list[BaseBot] | None = None) -> None:
    """补全 Bot 昵称与头像（出图前调用，失败不影响出图）。"""
    for bot in bots or []:
        try:
            await _load_bot_meta(bot)
        except Exception as e:  # noqa: BLE001
            logger.debug("补全 Bot 信息失败 {}: {}", bot.self_id, e)


@driver.on_bot_connect
async def _on_connect(bot: BaseBot) -> None:
    bot_connect_time[bot.self_id] = datetime.now().astimezone()
    recv_num.setdefault(bot.self_id, None)
    send_num.setdefault(bot.self_id, None)
    try:
        await _load_bot_meta(bot)
    except Exception as e:  # noqa: BLE001
        logger.debug("Bot 连接时获取信息失败 {}: {}", bot.self_id, e)


@driver.on_bot_disconnect
async def _on_disconnect(bot: BaseBot) -> None:
    bot_connect_time.pop(bot.self_id, None)
    if config.zmd_disconnect_reset_counter:
        recv_num.pop(bot.self_id, None)
        send_num.pop(bot.self_id, None)


# endregion


def prime_bot_meta(
    self_id: str,
    nickname: str | None,
    avatar: str | None = None,
) -> None:
    """注入 Bot 昵称/头像（供测试与预览工具使用，跳过网络请求）。"""
    _bot_meta[self_id] = (nickname, avatar)


def collect_bot_status(bots: list[BaseBot]) -> list[BotStatus]:
    result: list[BotStatus] = []
    for bot in bots:
        nickname, avatar = _bot_meta.get(bot.self_id, (None, None))
        result.append(
            BotStatus(
                self_id=bot.self_id,
                adapter=bot.adapter.get_name(),
                nickname=nickname,
                avatar=avatar,
                online=True,
                connect_time=bot_connect_time.get(bot.self_id),
                recv=recv_num.get(bot.self_id),
                send=send_num.get(bot.self_id),
            ),
        )
    result.sort(key=lambda b: b.self_id)
    return result


def collect_offline_bots(bots: list[BaseBot]) -> list[BotStatus]:
    """已断开但仍有记录的 Bot（保留最近连接时长与计数）。"""
    online = {bot.self_id for bot in bots}
    result: list[BotStatus] = []
    for self_id in sorted(set(recv_num) - online):
        nickname, avatar = _bot_meta.get(self_id, (None, None))
        result.append(
            BotStatus(
                self_id=self_id,
                adapter="—",
                nickname=nickname,
                avatar=avatar,
                online=False,
                connect_time=None,
                recv=recv_num.get(self_id),
                send=send_num.get(self_id),
            ),
        )
    return result


def nonebot_env() -> tuple[int, int]:
    """（适配器数, 插件数）"""
    try:
        adapters = len(nonebot.get_loaded_adapters())
    except Exception:  # noqa: BLE001
        adapters = 0
    try:
        plugins = len(nonebot.get_loaded_plugins())
    except Exception:  # noqa: BLE001
        plugins = 0
    return adapters, plugins
