"""nonebot-plugin-htmlrender 兼容层。

htmlrender 0.8 是破坏性重构：``get_new_page`` / ``html_to_pic`` 等符号被整体删除，
官方明确「不做歧义兼容」，Playwright 也从内置依赖变成 ``[playwright]`` extra。

三代版本唯一一致的入口是「拿到原生 Playwright Page」，所以这里只做一件事：
按探测到的版本走对应的取 Page 方式，渲染逻辑本身完全不感知版本差异。

- 0.6.x：``get_new_page(**ctx_opts)``（浏览器是包内依赖）
- 0.7.x：``get_render_context(**ctx_opts)``
- 0.8+：``extensions.playwright.browser()`` + ``browser.new_page(**ctx_opts)``

0.7 的 ``get_new_page`` 被官方加了 ``@deprecated``，调用会持续刷告警，因此 0.7
走的是它内部转发到的 ``get_render_context``。
"""

from __future__ import annotations

import importlib.util
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any

import nonebot_plugin_htmlrender as htmlrender

if TYPE_CHECKING:
    from playwright.async_api import Page

V8 = "0.8+"
V7 = "0.7"
V6 = "0.6"

PROVIDER_HINT = (
    "htmlrender 0.8 起不再内置浏览器后端，请依次确认：\n"
    "  1) 安装 Playwright extra：\n"
    '     pip install "nonebot-plugin-htmlrender[playwright]>=0.8"\n'
    "  2) 在 .env 里选择 Provider：\n"
    '     RENDER={"provider":"playwright","startup":"warmup"}\n'
    "  3) 安装浏览器内核：\n"
    "     playwright install chromium"
)


class RenderBackendError(RuntimeError):
    """渲染后端不可用，消息里带可执行的修复提示。"""


def detect_version() -> str:
    """按 API 形状探测，不解析版本号。"""
    if hasattr(htmlrender, "get_default_application"):
        return V8
    if hasattr(htmlrender, "get_render_context"):
        return V7
    return V6


BACKEND_VERSION = detect_version()


def installed_version() -> str:
    try:
        return version("nonebot-plugin-htmlrender")
    except PackageNotFoundError:  # pragma: no cover
        return "unknown"


def backend_label() -> str:
    """用于底栏展示，如 ``HTMLRENDER 0.8.1 / 0.8+``。"""
    return f"HTMLRENDER {installed_version()} / {BACKEND_VERSION}"


@asynccontextmanager
async def new_page(**context_options: Any) -> AsyncIterator[Page]:
    """取一个原生 Playwright Page。

    ``context_options`` 直接交给浏览器上下文（``viewport`` /
    ``device_scale_factor`` / ``locale`` 等）。
    """
    if BACKEND_VERSION == V8:
        from nonebot_plugin_htmlrender import get_default_application

        try:
            playwright = get_default_application().extensions.playwright
            browser_cm = playwright.browser
        except Exception as e:
            raise RenderBackendError(PROVIDER_HINT) from e

        async with browser_cm() as browser:
            # Browser 归 Provider 所有不能关；自建的 context/page 必须自己关
            page = await browser.new_page(**context_options)
            try:
                yield page
            finally:
                await page.context.close()
        return

    if BACKEND_VERSION == V7:
        from nonebot_plugin_htmlrender import get_render_context

        async with get_render_context(**context_options) as page:
            yield page
        return

    from nonebot_plugin_htmlrender import get_new_page

    async with get_new_page(**context_options) as page:
        yield page


def probe() -> tuple[bool, str]:
    """启动期探测：返回（是否可用, 说明）。不抛异常。"""
    if BACKEND_VERSION == V8:
        try:
            from nonebot_plugin_htmlrender import get_default_application

            # 未选 Provider 时属性访问本身就会抛 CapabilityUnavailable
            playwright = get_default_application().extensions.playwright
        except Exception:  # noqa: BLE001
            return False, PROVIDER_HINT
        if playwright is None:
            return False, PROVIDER_HINT
        return True, backend_label()

    if importlib.util.find_spec("playwright") is None:
        return (
            False,
            "未安装 playwright，请先 pip install playwright 并执行 "
            "playwright install chromium",
        )
    return True, backend_label()
