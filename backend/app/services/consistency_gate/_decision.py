"""一致性门禁统一判定函数

ADR-FHIC-14 第 5 点。所有门禁消费方只调 gate_decision，不自行解读 ConsistencyResult。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

from app.services.consistency_gate._models import CheckItem, ConsistencyResult

logger = logging.getLogger(__name__)

Consumer = Literal["chain_rule", "export_package"]


def _load_mode() -> str:
    """延迟加载 settings 避免导入环。"""
    from app.core.config import settings
    return getattr(settings, "CONSISTENCY_GATE_ENFORCEMENT", "observe")


@dataclass(frozen=True, slots=True)
class GateDecision:
    """gate_decision 返回值"""

    blocks: bool
    """当前模式下是否阻断"""

    items: list[CheckItem] = field(default_factory=list)
    """触发判定的检查项（observe 下 = would_block；enforce 下 = would_block）"""

    mode: str = "observe"
    """observe | enforce"""

    summary: str = ""
    """中文说明，可直接展示"""


def gate_decision(
    result: ConsistencyResult,
    *,
    consumer: Consumer,
) -> GateDecision:
    """统一判定函数。

    Parameters
    ----------
    result : ConsistencyResult
        run_all_checks 的返回值。
    consumer : "chain_rule" | "export_package"
        调用来源——chain_rule（sign_off / export_package 门禁规则）、
        export_package（导出打包服务）。

    Returns
    -------
    GateDecision
        blocks=True 表示当前模式下应阻断（chain_rule 返回 blocking 命中、
        export_package 抛 ConsistencyCheckError）。
    """
    mode = _load_mode()

    # 收集"会阻断"的检查项
    would_block_items = [c for c in result.checks if c.would_block_when_enforced]
    count = len(would_block_items)

    if count == 0:
        return GateDecision(blocks=False, items=[], mode=mode, summary="")

    if mode == "enforce":
        summary = f"一致性检查有 {count} 项未通过或未执行，请补齐数据后重新检查"
        return GateDecision(
            blocks=True,
            items=would_block_items,
            mode=mode,
            summary=summary,
        )

    # observe — 不阻断，但给出提示
    summary = f"一致性检查有 {count} 项未通过或未执行（当前为只提示模式）"
    return GateDecision(
        blocks=False,
        items=would_block_items,
        mode=mode,
        summary=summary,
    )
