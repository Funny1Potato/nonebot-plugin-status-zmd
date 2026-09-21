"""渲染入口：采集结果 → HTML → 图片字节。"""

from __future__ import annotations

from typing import Any

import anyio
from nonebot import logger
from nonebot.adapters import Bot as BaseBot

from ..config import config
from ..sampler import SamplerDataUnavailable
from ..storage import write_debug_html
from .backend import RenderBackendError, backend_label, new_page, probe
from .env import build_html
from .model import VIEWPORT_WIDTH, RenderModel, build_model

#: 视口高度只是初始值，实际按 full_page 取内容高度
VIEWPORT_HEIGHT = 900
#: 等待字体就绪标记的最长时间（毫秒）
WAIT_MARKER_TIMEOUT = 10_000

__all__ = [
    "RenderBackendError",
    "RenderModel",
    "SamplerDataUnavailable",
    "backend_label",
    "build_html",
    "build_model",
    "new_page",
    "probe",
    "render_model",
    "render_status_image",
]


async def _screenshot(html: str) -> bytes:
    image_format = config.stzmd_pic_format
    options: dict[str, Any] = {"full_page": True, "type": image_format}
    if image_format == "jpeg":
        options["quality"] = config.stzmd_pic_quality

    with anyio.fail_after(config.stzmd_render_timeout):
        async with new_page(
            viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
            device_scale_factor=config.stzmd_device_scale_factor,
            locale="zh-CN",
        ) as page:
            await page.set_content(html, wait_until="load")
            await page.wait_for_function(
                "document.body.classList.contains('done')",
                timeout=WAIT_MARKER_TIMEOUT,
            )
            return await page.screenshot(**options)


async def render_model(model: RenderModel) -> bytes:
    """渲染一个已经组装好的模型（预览工具复用这条路径）。"""
    html = await build_html(model)
    try:
        return await _screenshot(html)
    except Exception:
        path = write_debug_html(html)
        logger.error("渲染状态图失败，HTML 已保存到 {}", path)
        raise


async def render_status_image(bots: list[BaseBot]) -> bytes:
    model = await build_model(bots, want_gauge="gauge" in config.enabled_blocks())
    return await render_model(model)
