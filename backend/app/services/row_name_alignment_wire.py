"""名称对齐 wire 编排（formula-row-name-alignment-confirmation Task 8）。

把候选生成（`build_candidates`）+ 四态分类（`classify`）+ 已落库映射
（`RowNameMappingService.load_active_mappings`）编排成**固定 wire 字段**，
供底稿级刷新端点逐行返回 match_state / 候选 / 映射来源。

wire 字段固定为（design §Components/后端 3）：
  row_key / match_state / candidates[] / target_identity / amount /
  similarity / source_kind / confirmed_by / confirmed_at / mapping_version / stale_reason

🔴 additive 反模式自查：这些字段的唯一前端消费方 =
`GtRowNameAlignmentDialog.vue`（Task 9）+ 行内标识（Task 10），非死代码。

spec: .kiro/specs/formula-row-name-alignment-confirmation/ Requirement 1.1 / 1.3 / 3.3
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from app.services.four_table.row_name_alignment import (
    Candidate,
    MatchState,
    SavedMapping,
    build_candidates,
    classify,
)
from app.services.row_name_mapping_service import MappingScope, RowNameMappingService

logger = logging.getLogger(__name__)


@dataclass
class RowAlignmentInput:
    """一行待对齐的输入（行名 + 该行定位出的科目前缀集）。"""

    row_key: str
    row_label: str
    account_prefixes: list[str]


def _mapping_source_wire(m: SavedMapping | None) -> dict:
    """映射来源 wire（Requirement 1.3：来自哪些明细、谁何时确认）。"""
    if m is None:
        return {
            "confirmed_by": None,
            "confirmed_at": None,
            "mapping_version": None,
            "target_identity": [],
        }
    return {
        "confirmed_by": m.confirmed_by,
        "confirmed_at": m.confirmed_at,
        "mapping_version": m.mapping_version,
        "target_identity": [
            {
                "source_kind": t.source_kind,
                "account_code": t.account_code,
                "aux_type": t.aux_type,
                "aux_name": t.aux_name,
                "dimension_key": t.dimension_key,
                "dataset_id": t.dataset_id,
            }
            for t in m.targets
        ],
    }


def _row_wire(
    row: RowAlignmentInput,
    candidates: list[Candidate],
    saved: SavedMapping | None,
    active_keys: frozenset[tuple],
) -> dict:
    """单行固定 wire。"""
    result = classify(
        row.row_label, candidates, saved, active_target_keys=active_keys
    )
    # 已确认行的金额来自其目标身份（在候选里能查到）；否则为 auto/ambiguous 命中的展示
    amount: Decimal | None = None
    if result.state is MatchState.USER_CONFIRMED and saved is not None:
        by_key = {c.target.identity_tuple(): c.amount for c in candidates}
        total = Decimal("0")
        for t in saved.targets:
            total += by_key.get(t.identity_tuple(), Decimal("0"))
        amount = total
    elif result.state is MatchState.AUTO_MATCHED and result.matched_targets:
        by_key = {c.target.identity_tuple(): c.amount for c in candidates}
        amount = by_key.get(result.matched_targets[0].identity_tuple())

    source = _mapping_source_wire(saved)
    return {
        "row_key": row.row_key,
        "match_state": result.state.value,
        "candidates": [c.as_wire() for c in candidates],
        # 已确认行：target_identity 来自映射；否则来自 auto 命中（供行内溯源）
        "target_identity": source["target_identity"]
        or [
            {
                "source_kind": t.source_kind,
                "account_code": t.account_code,
                "aux_type": t.aux_type,
                "aux_name": t.aux_name,
                "dimension_key": t.dimension_key,
                "dataset_id": t.dataset_id,
            }
            for t in result.matched_targets
        ],
        "amount": None if amount is None else str(amount),
        "similarity": (
            round(candidates[0].similarity, 4) if candidates else None
        ),
        "source_kind": (
            "user_confirmed"
            if result.state is MatchState.USER_CONFIRMED
            else ("auto" if result.state is MatchState.AUTO_MATCHED else None)
        ),
        "confirmed_by": source["confirmed_by"],
        "confirmed_at": source["confirmed_at"],
        "mapping_version": source["mapping_version"],
        "stale_reason": result.stale_reason,
    }


async def build_alignment_wire(
    db,
    scope: MappingScope,
    rows: list[RowAlignmentInput],
    *,
    dataset_id: str | None = None,
) -> dict:
    """底稿级刷新的名称对齐 wire：逐行 match_state + 候选 + 映射来源。

    Returns:
        {
          "rows": [ <固定 wire> ... ],
          "unmatched_count": int,       # unmatched + ambiguous 待确认行数
          "has_pending": bool,          # 是否存在待人工确认行（前端据此决定弹窗）
        }
    """
    svc = RowNameMappingService(db)
    saved_map = await svc.load_active_mappings(scope)

    wire_rows: list[dict] = []
    pending = 0
    for row in rows:
        candidates = await build_candidates(
            db,
            scope.project_id,
            scope.year,
            row.account_prefixes,
            row.row_label,
            dataset_id=dataset_id,
        )
        active_keys = frozenset(c.target.identity_tuple() for c in candidates)
        saved = saved_map.get(row.row_key)
        w = _row_wire(row, candidates, saved, active_keys)
        if w["match_state"] in (
            MatchState.UNMATCHED.value,
            MatchState.AMBIGUOUS.value,
        ):
            pending += 1
        wire_rows.append(w)

    return {
        "rows": wire_rows,
        "unmatched_count": pending,
        "has_pending": pending > 0,
    }


__all__ = [
    "RowAlignmentInput",
    "build_alignment_wire",
]
