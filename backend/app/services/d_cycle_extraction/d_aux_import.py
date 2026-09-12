"""D2~D7 明细表「从余额表导入」端点共享件（G-C 迁移收敛）.

spec: .kiro/specs/four-table-extraction-entry-completion/  (Task 4, Requirements 2.3~2.6, 3.1, 3.5, 5.3)

历史上 D3/D5/D6/D7 各自内联一份裸 SQL（`SELECT aux_name ... FROM tb_aux_balance
WHERE ... is_deleted=false GROUP BY aux_name`），带四个铁律违规（红基线 ①②③④）：
① 不走 `get_active_filter`（跨数据集双算）；② `GROUP BY aux_name` 未先锁单一
`aux_type`（同科目挂多维度双算）；③ 科目码硬编码；④ 把余额全额塞进账龄首段。

本模块把「解析科目前缀 → 调共享件归集 → 产出可辨别 reason 提示」这段收敛为一处，
四个端点（含新建的 D2）统一消费，**不再各自抄一份归集 SQL**（Requirement 3.1）：

  * 科目前缀经 `resolve_d_cycle_account_codes`（报表映射 `BS-046/BS-007/BS-011/
    BS-047/BS-006`，兜底常量注明 `source_ref`，DEC-3）解析，不裸字面量（②③ 治理）。
  * 归集经 `four_table.aux_aggregation.aggregate_aux_by_name_ex`（`get_active_filter`
    + `pick_aux_type` + 前缀匹配），拿回结构化 `reason` 码（①⑤ 治理，Requirement 5.2）。
  * 账龄字段**留空**（不再塞全额），返回 message 提示需人工填账龄（④ 治理，
    Requirement 2.5 / 5.3）。
"""
from __future__ import annotations

import logging
from typing import Any, NamedTuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.d_cycle_extraction.d_account_resolver import (
    resolve_d_cycle_account_codes,
    spec_of,
)
from app.services.four_table.aux_aggregation import (
    AuxAggregationReason,
    AuxEntry,
    aggregate_aux_by_name_ex,
)

logger = logging.getLogger(__name__)


class _MiniCtx:
    """`resolve_report_line_accounts` / `resolve_d_cycle_account_codes` 只按属性访问
    `db` / `project_id`（鸭子类型），导入导出端点无需构造完整 `RenderContext`。

    与 `_k1_import_export._MiniCtx` 同款范式。
    """

    def __init__(self, db: AsyncSession, project_id: str):
        self.db = db
        self.project_id = project_id


class DAuxImportResult(NamedTuple):
    """一次 D 循环 aux 归集的完整结果 + 溯源。"""

    entries: list[AuxEntry]
    aux_type: str | None
    reason: AuxAggregationReason
    prefixes: list[str]
    row_code: str
    resolved_from: str


async def resolve_d_cycle_gross_prefixes(
    db: AsyncSession, project_id: str, wp_code: str
) -> tuple[list[str], str, str]:
    """解析某 D 循环原值科目原始码前缀（报表映射优先，兜底常量注明来源）.

    Returns:
        ``(prefixes, row_code, resolved_from)``。``prefixes`` 为空表示既无报表映射
        也无兜底码（DEC-3：此时归集应返回 ``no_prefixes``，禁静默用字面量）。
    """
    codes = await resolve_d_cycle_account_codes(_MiniCtx(db, project_id), wp_code)
    prefixes = [str(p).strip() for p in (codes.gross or []) if str(p or "").strip()]
    return prefixes, codes.row_code, codes.resolved_from


async def aggregate_d_cycle_aux(
    db: AsyncSession, project_id: str, year: int, wp_code: str
) -> DAuxImportResult:
    """D 循环明细表 aux 归集统一入口（四表库三铁律经共享件落地）.

    科目前缀走报表映射解析（`spec_of(wp_code)` 的 `row_code`，兜底常量注明来源），
    归集走 `aggregate_aux_by_name_ex`（active dataset 过滤 + 单一 aux_type 锁定 +
    前缀匹配），拿回结构化 `reason` 码供端点产出可辨别中文提示。
    """
    prefixes, row_code, resolved_from = await resolve_d_cycle_gross_prefixes(
        db, project_id, wp_code
    )
    result = await aggregate_aux_by_name_ex(db, project_id, year, prefixes)
    return DAuxImportResult(
        entries=result.entries,
        aux_type=result.aux_type,
        reason=result.reason,
        prefixes=prefixes,
        row_code=row_code,
        resolved_from=resolved_from,
    )


def aux_reason_message(
    reason: AuxAggregationReason, prefixes: list[str]
) -> str:
    """把 `reason` 码翻译为可辨别的中文提示（Requirement 4.4 / 5.2）。

    "接线错误"（``error``）与"真无数据"（``no_rows``）等在此文案上可分辨，
    不再统一说"导入 0 行"。
    """
    prefix_hint = prefixes[0] if prefixes else "（未解析出科目）"
    return {
        "no_prefixes": "未能从报表映射解析出该循环的科目码，请检查报表行配置（无兜底码）。",
        "no_aux_type": f"科目{prefix_hint}存在但未按往来单位维度挂账，无法按维度归集。",
        "no_active_dataset": "当前项目/年度无激活的账套数据集，请先激活数据集。",
        "no_rows": f"未找到科目{prefix_hint}的辅助余额数据。",
        "error": "从辅助余额表取数时发生异常（已记录日志），请联系管理员核查。",
    }.get(reason, f"未找到科目{prefix_hint}的辅助余额数据。")


__all__ = [
    "DAuxImportResult",
    "aggregate_d_cycle_aux",
    "aux_reason_message",
    "resolve_d_cycle_gross_prefixes",
    "spec_of",
]
