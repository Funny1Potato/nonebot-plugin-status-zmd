"""指令注册与图片发送。"""

from __future__ import annotations

import nonebot
from nonebot import logger, on_command
from nonebot.adapters import Message
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.rule import Rule, to_me
from nonebot_plugin_alconna.uniseg import UniMessage

from .bot_info import ensure_bot_meta
from .config import config
from .render import RenderBackendError, render_status_image


def _empty_arg_rule(arg: Message = CommandArg()) -> bool:
    """后面跟了别的内容就不触发，避免抢占其他用法的同名指令。"""
    return not arg.extract_plain_text().strip()


def _rule() -> Rule:
    rule = Rule(_empty_arg_rule)
    if config.stzmd_need_at:
        rule &= to_me()
    return rule


_cmd, *_alias = config.stzmd_command
stat_matcher = on_command(
    _cmd,
    aliases=set(_alias),
    rule=_rule(),
    permission=SUPERUSER if config.stzmd_only_superuser else None,
)


@stat_matcher.handle()
async def _handle_status() -> None:
    bots = list(nonebot.get_bots().values())
    if bots:
        await ensure_bot_meta(bots)

    try:
        image = await render_status_image(bots)
    except RenderBackendError as e:
        logger.error("ZMD 渲染后端不可用：{}", e)
        await UniMessage(str(e)).send(reply_to=config.stzmd_reply_target)
        return
    except Exception:  # noqa: BLE001
        logger.exception("获取终末状态图失败")
        await UniMessage("获取状态图失败，请检查后台输出").send(
            reply_to=config.stzmd_reply_target,
        )
        return

    await UniMessage.image(raw=image).send(reply_to=config.stzmd_reply_target)
    logger.debug(
        "终末状态图已发送，{} 字节",
        len(image),
    )
