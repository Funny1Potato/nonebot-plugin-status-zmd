"""配置模型：校验器与版式/板块的求交。"""

from __future__ import annotations

import pytest

from nonebot_plugin_status_zmd.config import (
    ALL_BLOCKS,
    LAYOUT_BLOCKS,
    ConfigModel,
)


def test_layout_blocks_cover_all_blocks():
    covered = {block for blocks in LAYOUT_BLOCKS.values() for block in blocks}
    assert covered == set(ALL_BLOCKS)


def test_unknown_block_rejected():
    with pytest.raises(ValueError, match="未知板块"):
        ConfigModel(stzmd_blocks=["header", "nope"])


def test_empty_block_list_rejected():
    with pytest.raises(ValueError, match="不能为空"):
        ConfigModel(stzmd_blocks=[])


def test_empty_command_rejected():
    with pytest.raises(ValueError, match="至少需要一个指令名"):
        ConfigModel(stzmd_command=["  "])


def test_enabled_blocks_respects_layout():
    model = ConfigModel(
        stzmd_layout="perf",
        stzmd_blocks=["header", "gauge", "apps", "bots", "perf", "specs", "footer"],
    )
    assert "perf" in model.enabled_blocks()
    assert "gauge" not in model.enabled_blocks()
    assert "apps" not in model.enabled_blocks()
    assert set(model.skipped_blocks()) == {"gauge", "apps"}


def test_enabled_blocks_is_intersection():
    model = ConfigModel(stzmd_layout="full", stzmd_blocks=["header", "gauge"])
    assert model.enabled_blocks() == {"header", "gauge"}
    assert model.skipped_blocks() == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"stzmd_pic_quality": 0},
        {"stzmd_pic_quality": 101},
        {"stzmd_device_scale_factor": 0},
        {"stzmd_render_timeout": 0},
        {"stzmd_collect_interval": 0},
        {"stzmd_history_size": 1},
        {"stzmd_proc_len": 0},
        {"stzmd_gauge_value_max": 0},
        {"stzmd_gauge_cpu_weight": -1},
        {"stzmd_layout": "unknown"},
    ],
)
def test_invalid_values_rejected(kwargs):
    with pytest.raises(ValueError):
        ConfigModel(**kwargs)


def test_defaults_are_safe():
    model = ConfigModel()
    assert model.stzmd_only_superuser is True
    assert model.stzmd_layout == "full"
    assert model.stzmd_blocks == list(ALL_BLOCKS)
    assert model.stzmd_gauge_value_max == 325799
    assert model.stzmd_gauge_cpu_weight + model.stzmd_gauge_mem_weight == pytest.approx(
        1.0
    )
