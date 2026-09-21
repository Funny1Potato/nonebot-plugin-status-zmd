"""pytest 公共夹具：初始化 NoneBot 后各测试模块才能导入插件配置。"""

from __future__ import annotations

import sys
from pathlib import Path

import nonebot
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ensure_nonebot_init() -> None:
    try:
        nonebot.get_driver()
    except ValueError:
        # htmlrender >= 0.8 需要显式选择 Provider；老版本会忽略这个键
        nonebot.init(render={"provider": "playwright", "startup": "warmup"})


_ensure_nonebot_init()


@pytest.fixture()
def restore_config():
    """改动 config 的测试用它自动还原。"""
    from nonebot_plugin_status_zmd.config import config

    snapshot = config.model_dump()
    yield config
    for key, value in snapshot.items():
        setattr(config, key, value)


@pytest.fixture()
def render_guard():
    """浏览器内核缺失时跳过，而不是把环境问题报成用例失败。"""

    def guard(exc: BaseException) -> None:
        text = str(exc)
        # 只有「浏览器没装」这一类才跳过，真实渲染错误照常抛出去
        if (
            "Executable doesn't exist" in text
            or "install_required" in text
            or "playwright install" in text
        ):
            pytest.skip(f"未安装 Playwright 浏览器内核：{text.splitlines()[0]}")

    return guard
