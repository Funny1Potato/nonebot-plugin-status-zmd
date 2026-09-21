"""htmlrender 三代兼容层的探测与降级路径。"""

from __future__ import annotations

import pytest

from nonebot_plugin_status_zmd.render import backend


class FakeModule:
    """用属性形状模拟某一代 htmlrender 的公共面。"""

    def __init__(self, **attrs: object) -> None:
        self.__dict__.update(attrs)


@pytest.fixture()
def fake_htmlrender(monkeypatch):
    def apply(**attrs: object):
        monkeypatch.setattr(backend, "htmlrender", FakeModule(**attrs))

    return apply


def test_detect_v08(fake_htmlrender):
    fake_htmlrender(get_default_application=object())
    assert backend.detect_version() == backend.V8


def test_detect_v08_wins_over_v07_symbols(fake_htmlrender):
    # 0.8 里没有 get_render_context，但顺序上也要保证 0.8 优先
    fake_htmlrender(get_default_application=object(), get_render_context=object())
    assert backend.detect_version() == backend.V8


def test_detect_v07(fake_htmlrender):
    fake_htmlrender(get_render_context=object())
    assert backend.detect_version() == backend.V7


def test_detect_v06(fake_htmlrender):
    fake_htmlrender(get_new_page=object())
    assert backend.detect_version() == backend.V6


def test_installed_version_is_readable():
    assert backend.installed_version() != ""
    label = backend.backend_label()
    assert label.startswith("HTMLRENDER ")
    assert "/" in label


def test_probe_returns_status_tuple():
    available, detail = backend.probe()
    assert isinstance(available, bool)
    assert detail


@pytest.mark.render
async def test_new_page_yields_native_playwright_page(render_guard):
    """真跑一次兼容层，确认拿到的确实是 Playwright Page（需已装浏览器）。"""
    playwright = pytest.importorskip("playwright.async_api")

    available, detail = backend.probe()
    if not available:
        pytest.skip(detail)

    try:
        async with backend.new_page(
            viewport={"width": 320, "height": 200},
            device_scale_factor=1,
            locale="zh-CN",
        ) as page:
            assert isinstance(page, playwright.Page)
            await page.set_content("<body><p id=t>ok</p></body>")
            assert await page.inner_text("#t") == "ok"
    except Exception as e:
        render_guard(e)
        raise
