"""插件配置模型。所有配置项均以 ``STZMD_`` 为前缀。"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from nonebot import get_plugin_config
from pydantic import BaseModel, Field, field_validator

PLUGIN_DIR = Path(__file__).parent
RES_DIR = PLUGIN_DIR / "res"
TEMPLATE_DIR = RES_DIR / "templates"
CSS_PATH = RES_DIR / "css" / "index.css"

LayoutType = Literal["full", "gauge", "perf"]
ProcSortByType = Literal["cpu", "mem"]
PicFormatType = Literal["jpeg", "png"]

#: 全部板块名，以及各版式允许出现的板块
BLOCK_HEADER = "header"
BLOCK_GAUGE = "gauge"
BLOCK_APPS = "apps"
BLOCK_BOTS = "bots"
BLOCK_PERF = "perf"
BLOCK_SPECS = "specs"
BLOCK_FOOTER = "footer"

LAYOUT_BLOCKS: dict[str, tuple[str, ...]] = {
    "full": (
        BLOCK_HEADER,
        BLOCK_GAUGE,
        BLOCK_APPS,
        BLOCK_BOTS,
        BLOCK_PERF,
        BLOCK_SPECS,
        BLOCK_FOOTER,
    ),
    "gauge": (BLOCK_HEADER, BLOCK_GAUGE, BLOCK_BOTS, BLOCK_SPECS, BLOCK_FOOTER),
    "perf": (BLOCK_HEADER, BLOCK_PERF, BLOCK_BOTS, BLOCK_SPECS, BLOCK_FOOTER),
}
ALL_BLOCKS: tuple[str, ...] = tuple(
    dict.fromkeys(b for blocks in LAYOUT_BLOCKS.values() for b in blocks)
)


class ConfigModel(BaseModel):
    # region nonebot 内置
    superusers: set[str] = set()
    nickname: set[str] = set()
    # endregion

    # region 全局
    proxy: str | None = None
    # endregion

    # region 行为
    stzmd_command: list[str] = ["status", "系统状态"]
    stzmd_only_superuser: bool = True
    stzmd_need_at: bool = False
    stzmd_reply_target: bool = True
    # endregion

    # region 版式
    stzmd_layout: LayoutType = "full"
    stzmd_blocks: list[str] = list(ALL_BLOCKS)
    stzmd_host_name: str | None = None
    # endregion

    # region 电量环
    stzmd_gauge_value_max: float = 325799
    stzmd_gauge_cpu_weight: float = 0.4
    stzmd_gauge_mem_weight: float = 0.6
    # endregion

    # region 渲染
    stzmd_pic_format: PicFormatType = "jpeg"
    stzmd_pic_quality: int = 90
    stzmd_device_scale_factor: float = 2.0
    stzmd_render_timeout: float = 30.0
    stzmd_font_family: str | None = None
    stzmd_font_path: Path | None = None
    stzmd_extra_css: Path | None = None
    # endregion

    # region 采样
    stzmd_collect_interval: int = 5
    stzmd_history_size: int = 180
    stzmd_proc_len: int = 8
    stzmd_proc_sort_by: ProcSortByType = "cpu"
    stzmd_ignore_parts: list[str] = Field(default_factory=list)
    stzmd_ignore_nets: list[str] = [r"^lo(op)?\d*$|^(Loopback|本地连接)"]
    stzmd_ignore_procs: list[str] = [r"^System Idle Process$"]
    stzmd_proc_cpu_max_100p: bool = False
    # endregion

    # region Bot 状态
    stzmd_count_message_sent: bool = True
    stzmd_show_bot_avatar: bool = True
    stzmd_disconnect_reset_counter: bool = True
    stzmd_req_timeout: int = 10
    # endregion

    @field_validator("stzmd_command")
    @classmethod
    def _check_command(cls, v: list[str]) -> list[str]:
        commands = [c.strip() for c in v if c.strip()]
        if not commands:
            raise ValueError("STZMD_COMMAND 至少需要一个指令名")
        return commands

    @field_validator("stzmd_blocks")
    @classmethod
    def _check_blocks(cls, v: list[str]) -> list[str]:
        valid = set(ALL_BLOCKS)
        blocks = [b.strip() for b in v if b.strip()]
        if unknown := [b for b in blocks if b not in valid]:
            raise ValueError(
                f"STZMD_BLOCKS 含未知板块 {unknown}，可选值：{sorted(valid)}",
            )
        if not blocks:
            raise ValueError("STZMD_BLOCKS 不能为空")
        return blocks

    @field_validator("stzmd_pic_quality")
    @classmethod
    def _check_quality(cls, v: int) -> int:
        if not 1 <= v <= 100:
            raise ValueError("STZMD_PIC_QUALITY 需在 1-100 之间")
        return v

    @field_validator("stzmd_device_scale_factor")
    @classmethod
    def _check_scale(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("STZMD_DEVICE_SCALE_FACTOR 需为正数")
        return v

    @field_validator("stzmd_render_timeout")
    @classmethod
    def _check_render_timeout(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("STZMD_RENDER_TIMEOUT 需为正数")
        return v

    @field_validator("stzmd_collect_interval")
    @classmethod
    def _check_interval(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("STZMD_COLLECT_INTERVAL 需为正整数")
        return v

    @field_validator("stzmd_history_size")
    @classmethod
    def _check_history_size(cls, v: int) -> int:
        if v < 2:
            raise ValueError("STZMD_HISTORY_SIZE 至少为 2")
        return v

    @field_validator("stzmd_proc_len")
    @classmethod
    def _check_proc_len(cls, v: int) -> int:
        if v < 1:
            raise ValueError("STZMD_PROC_LEN 至少为 1")
        return v

    @field_validator("stzmd_gauge_value_max")
    @classmethod
    def _check_gauge_max(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("STZMD_GAUGE_VALUE_MAX 需为正数")
        return v

    @field_validator("stzmd_gauge_cpu_weight", "stzmd_gauge_mem_weight")
    @classmethod
    def _check_weight(cls, v: float) -> float:
        if v < 0:
            raise ValueError("电量环权重不能为负数")
        return v

    def enabled_blocks(self) -> set[str]:
        """当前版式下实际生效的板块集合。"""
        allowed = set(LAYOUT_BLOCKS[self.stzmd_layout])
        return set(self.stzmd_blocks) & allowed

    def skipped_blocks(self) -> list[str]:
        """被版式排除掉的板块（用于启动日志提示）。"""
        allowed = set(LAYOUT_BLOCKS[self.stzmd_layout])
        return [b for b in self.stzmd_blocks if b not in allowed]


config: ConfigModel = get_plugin_config(ConfigModel)
