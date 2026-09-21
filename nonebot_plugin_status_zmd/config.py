"""插件配置模型。所有配置项均以 ``ZMD_`` 为前缀。"""

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
    zmd_command: list[str] = ["status", "系统状态"]
    zmd_only_superuser: bool = True
    zmd_need_at: bool = False
    zmd_reply_target: bool = True
    # endregion

    # region 版式
    zmd_layout: LayoutType = "full"
    zmd_blocks: list[str] = list(ALL_BLOCKS)
    zmd_host_name: str | None = None
    # endregion

    # region 电量环
    zmd_gauge_value_max: float = 325799
    zmd_gauge_cpu_weight: float = 0.4
    zmd_gauge_mem_weight: float = 0.6
    # endregion

    # region 渲染
    zmd_pic_format: PicFormatType = "jpeg"
    zmd_pic_quality: int = 90
    zmd_device_scale_factor: float = 2.0
    zmd_render_timeout: float = 30.0
    zmd_font_family: str | None = None
    zmd_font_path: Path | None = None
    zmd_extra_css: Path | None = None
    # endregion

    # region 采样
    zmd_collect_interval: int = 5
    zmd_history_size: int = 180
    zmd_proc_len: int = 8
    zmd_proc_sort_by: ProcSortByType = "cpu"
    zmd_ignore_parts: list[str] = Field(default_factory=list)
    zmd_ignore_nets: list[str] = [r"^lo(op)?\d*$|^(Loopback|本地连接)"]
    zmd_ignore_procs: list[str] = [r"^System Idle Process$"]
    zmd_proc_cpu_max_100p: bool = False
    # endregion

    # region Bot 状态
    zmd_count_message_sent: bool = True
    zmd_show_bot_avatar: bool = True
    zmd_disconnect_reset_counter: bool = True
    zmd_req_timeout: int = 10
    # endregion

    @field_validator("zmd_command")
    @classmethod
    def _check_command(cls, v: list[str]) -> list[str]:
        commands = [c.strip() for c in v if c.strip()]
        if not commands:
            raise ValueError("ZMD_COMMAND 至少需要一个指令名")
        return commands

    @field_validator("zmd_blocks")
    @classmethod
    def _check_blocks(cls, v: list[str]) -> list[str]:
        valid = set(ALL_BLOCKS)
        blocks = [b.strip() for b in v if b.strip()]
        if unknown := [b for b in blocks if b not in valid]:
            raise ValueError(
                f"ZMD_BLOCKS 含未知板块 {unknown}，可选值：{sorted(valid)}",
            )
        if not blocks:
            raise ValueError("ZMD_BLOCKS 不能为空")
        return blocks

    @field_validator("zmd_pic_quality")
    @classmethod
    def _check_quality(cls, v: int) -> int:
        if not 1 <= v <= 100:
            raise ValueError("ZMD_PIC_QUALITY 需在 1-100 之间")
        return v

    @field_validator("zmd_device_scale_factor")
    @classmethod
    def _check_scale(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("ZMD_DEVICE_SCALE_FACTOR 需为正数")
        return v

    @field_validator("zmd_render_timeout")
    @classmethod
    def _check_render_timeout(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("ZMD_RENDER_TIMEOUT 需为正数")
        return v

    @field_validator("zmd_collect_interval")
    @classmethod
    def _check_interval(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("ZMD_COLLECT_INTERVAL 需为正整数")
        return v

    @field_validator("zmd_history_size")
    @classmethod
    def _check_history_size(cls, v: int) -> int:
        if v < 2:
            raise ValueError("ZMD_HISTORY_SIZE 至少为 2")
        return v

    @field_validator("zmd_proc_len")
    @classmethod
    def _check_proc_len(cls, v: int) -> int:
        if v < 1:
            raise ValueError("ZMD_PROC_LEN 至少为 1")
        return v

    @field_validator("zmd_gauge_value_max")
    @classmethod
    def _check_gauge_max(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("ZMD_GAUGE_VALUE_MAX 需为正数")
        return v

    @field_validator("zmd_gauge_cpu_weight", "zmd_gauge_mem_weight")
    @classmethod
    def _check_weight(cls, v: float) -> float:
        if v < 0:
            raise ValueError("电量环权重不能为负数")
        return v

    def enabled_blocks(self) -> set[str]:
        """当前版式下实际生效的板块集合。"""
        allowed = set(LAYOUT_BLOCKS[self.zmd_layout])
        return set(self.zmd_blocks) & allowed

    def skipped_blocks(self) -> list[str]:
        """被版式排除掉的板块（用于启动日志提示）。"""
        allowed = set(LAYOUT_BLOCKS[self.zmd_layout])
        return [b for b in self.zmd_blocks if b not in allowed]


config: ConfigModel = get_plugin_config(ConfigModel)
