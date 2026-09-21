# ruff: noqa: E402

from nonebot import get_driver, logger, require
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

require("nonebot_plugin_apscheduler")
require("nonebot_plugin_alconna")
require("nonebot_plugin_uninfo")
require("nonebot_plugin_localstore")
require("nonebot_plugin_htmlrender")

from . import cmd as cmd
from .config import ConfigModel, config
from .render import RenderBackendError as RenderBackendError
from .render import probe
from .sampler import sampler
from .utils import find_cjk_font

__version__ = "0.1.0"

usage = f"指令：{' / '.join(config.zmd_command)}"
if config.zmd_only_superuser:
    usage += "\n注意：仅 SUPERUSER 可以使用此指令"
if config.zmd_need_at:
    usage += "\n注意：使用指令时需要 @ 机器人"

__plugin_meta__ = PluginMetadata(
    name="ZMD-Status",
    description="以《明日方舟：终末地》电量系统风格展示机器人所在服务器的运行状态",
    usage=usage,
    type="application",
    homepage="https://github.com/Funny1Potato/nonebot-plugin-status-zmd",
    config=ConfigModel,
    supported_adapters=inherit_supported_adapters(
        "nonebot_plugin_alconna",
        "nonebot_plugin_uninfo",
    ),
    extra={"License": "MIT", "Author": "Funny1Potato"},
)

driver = get_driver()


@driver.on_startup
async def _startup() -> None:
    available, detail = probe()
    if available:
        logger.info("ZMD 渲染后端就绪：{}", detail)
    else:
        logger.warning("ZMD 渲染后端不可用：\n{}", detail)

    if skipped := config.skipped_blocks():
        logger.info(
            "ZMD 版式 {} 下这些板块不会渲染：{}",
            config.zmd_layout,
            ", ".join(skipped),
        )

    if find_cjk_font() is None and not config.zmd_font_path:
        logger.warning(
            "未探测到系统中文字体，出图里的中文可能显示为方块；"
            "可用 ZMD_FONT_FAMILY 指定已安装字体，或用 ZMD_FONT_PATH "
            "指向字体文件",
        )

    await sampler.start()
