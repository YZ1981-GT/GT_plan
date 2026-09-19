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
from typing import Any, NamedTuple, Sequence
from uuid import UUID

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


# ─── 账龄空骨架（Phase 2 / Task 12：配置驱动，不塞首段，Requirement 7.1~7.3/7.6） ──
#
# 🔴 四表库无账龄源 ⇒ 账龄由审计师人工填列，取数**只生成空骨架、绝不写入任何账龄金额**
#   （红基线④ / Property 5「不伪造账龄分布」；严禁 `bucket[first_key]=amount` 整额落首段）。
#   段键集必须来自项目级账龄配置 `get_effective_segments(project_id, subject, db)`，与前端
#   `useAgingConfig` 同一真源（Requirement 7.1）。D3/D5/D6/D7 均为 **2-period** 科目
#   （对齐 `useAgingConfig` 的 `THREE_PERIOD_SUBJECTS = {D2,K1,K3,G5,F1}`）⇒ 只生成
#   `agingPrior`/`agingAudited` 两组，**不含** `agingCurrent`（Requirement 7.2）。


def _segment_keys(segments: Sequence[Any]) -> list[str]:
    """从账龄段对象/字典/字符串里抽 key 序列（去重、保序）。

    与 `four_table.k1_aux_detail._segment_keys` 同款范式（K1 是 3-period 参照实现）。
    """
    keys: list[str] = []
    for s in segments or []:
        if isinstance(s, str):
            key = s
        elif isinstance(s, dict):
            key = str(s.get("key") or "")
        else:
            key = str(getattr(s, "key", "") or "")
        key = key.strip()
        if key and key not in keys:
            keys.append(key)
    return keys


def _empty_aging(seg_keys: Sequence[str]) -> dict[str, float]:
    """空账龄骨架：每段值=0（Property 5「不伪造账龄分布」）。

    绝不把余额整笔落首段（`bucket[first_key]=amount` 即活体伪造）。
    """
    return {k: 0.0 for k in seg_keys}


def build_two_period_aging_skeleton(segments: Sequence[Any]) -> dict[str, dict[str, float]]:
    """D3/D5/D6/D7（2-period）账龄空骨架：`agingPrior` + `agingAudited`，每段值=0。

    段键来自 `resolve_d_cycle_segments`（项目账龄配置真源）。**不含** `agingCurrent`
    （2-period 科目，Requirement 7.2）。骨架嵌套键式（nested keyed），与前端
    `useAgingConfig` / `createEmptyAgingData` 及 D3/D7 明细行 `agingPrior.{key}` 对齐。
    """
    seg_keys = _segment_keys(segments)
    return {
        "agingPrior": _empty_aging(seg_keys),
        "agingAudited": _empty_aging(seg_keys),
    }


async def resolve_d_cycle_segments(
    db: AsyncSession, project_id: str, subject: str
) -> list[Any]:
    """某 D 循环的有效账龄段：项目级配置 `get_effective_segments(project_id, subject, db)`。

    🔴 段键集是账龄空骨架的唯一真源（Requirement 7.1）——必须来自项目账龄配置，
    禁止硬编码段键或写死 `["within1"]` 兜底。读取失败时按 subject 默认 preset
    （`DEFAULT_SUBJECT_PRESETS`：D3/D7→THREE_YEAR，其余缺省 FIVE_YEAR）兜底，
    绝不回退单段（Requirement 7.6）。与 `_k1_import_export._resolve_k1_segments` 同款范式。
    """
    from app.services.aging_config_service import (
        DEFAULT_SUBJECT_PRESETS,
        AgingPreset,
        get_effective_segments,
        resolve_segments,
    )

    try:
        return await get_effective_segments(UUID(str(project_id)), subject, db)
    except Exception:  # noqa: BLE001 — 配置读取失败按 subject 默认 preset 兜底，不回退单段
        logger.exception(
            "resolve_d_cycle_segments fallback: project=%s subject=%s", project_id, subject
        )
        return resolve_segments(
            DEFAULT_SUBJECT_PRESETS.get(subject, AgingPreset.FIVE_YEAR), None
        )


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
    "build_two_period_aging_skeleton",
    "resolve_d_cycle_gross_prefixes",
    "resolve_d_cycle_segments",
    "spec_of",
]
