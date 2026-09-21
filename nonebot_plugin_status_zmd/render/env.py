"""Jinja 环境、字体注入与 HTML 组装。"""

from __future__ import annotations

import anyio
import jinja2
from nonebot import logger

from ..config import CSS_PATH, TEMPLATE_DIR, config
from ..utils import file_to_data_uri
from .icons import icon_svg
from .model import RenderModel

#: 单文件体积超过这个值就不内联，避免 HTML 膨胀到几十 MB
MAX_FONT_BYTES = 8 * 1024 * 1024

ENV = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=jinja2.select_autoescape(["html", "xml"]),
    enable_async=True,
    trim_blocks=True,
    lstrip_blocks=True,
)
ENV.globals["icon"] = icon_svg

_css_cache: str | None = None


async def load_css() -> str:
    global _css_cache
    if _css_cache is None:
        _css_cache = await anyio.Path(CSS_PATH).read_text(encoding="u8")
    return _css_cache


async def load_extra_css() -> str | None:
    path = config.stzmd_extra_css
    if path is None:
        return None
    if not await anyio.Path(path).is_file():
        logger.warning("STZMD_EXTRA_CSS 指向的文件不存在：{}", path)
        return None
    return await anyio.Path(path).read_text(encoding="u8")


def build_font_css() -> str | None:
    """把自定义字体配置翻译成一段 CSS（@font-face + 覆盖 --font）。"""
    blocks: list[str] = []
    family = config.stzmd_font_family

    if path := config.stzmd_font_path:
        try:
            size = path.stat().st_size
        except OSError:
            logger.warning("STZMD_FONT_PATH 不可读：{}", path)
        else:
            if size > MAX_FONT_BYTES:
                logger.warning(
                    "STZMD_FONT_PATH 文件过大（{}），已跳过内联；"
                    "请改用 STZMD_FONT_FAMILY 指定系统已安装的字体",
                    path,
                )
            elif uri := file_to_data_uri(path):
                blocks.append(
                    '@font-face{font-family:"ZMDStatusFont";'
                    f'src:url("{uri}");font-weight:500;font-display:block}}',
                )
                family = f'"ZMDStatusFont", {family}' if family else '"ZMDStatusFont"'

    if family:
        blocks.append(f":root{{--font: {family}, sans-serif}}")

    return "\n".join(blocks) or None


async def build_html(model: RenderModel) -> str:
    template = ENV.get_template("index.html.jinja")
    return await template.render_async(
        m=model,
        css=await load_css(),
        font_css=build_font_css(),
        extra_css=await load_extra_css(),
    )
