"""合并附注来源投影：整章级快速分类 + 统一写入 helper（批 5 / ADR-CRW-005）。

``source_mode`` 是章节最后一个写入方的分类——不是每格的所有权声明。格级所有权由
``data.manual_cells``、``locked_cells``、``_detail_provenance``、``_subtree_provenance``
和 ``last_formula_value`` 各自保持。

来源枚举与 ``record_write_source()`` 兼容：
- detail_mapping：明细映射 apply
- subtree_aggregate：子树重新汇总
- formula：按公式填入
- manual：手工保存（前端 PUT）
- mixed：同一次写入中自动列与手工/锁定格并存且属于不同来源
"""
from __future__ import annotations

import hashlib
from typing import Any, Literal
from uuid import UUID

from app.services.consol_version_vector import canonical_json

SourceMode = Literal["detail_mapping", "subtree_aggregate", "formula", "manual", "mixed"]

SOURCE_MODES: tuple[str, ...] = ("detail_mapping", "subtree_aggregate", "formula", "manual", "mixed")
# 自动写入方（非手工）
AUTO_WRITERS: frozenset[str] = frozenset({"detail_mapping", "subtree_aggregate", "formula"})


def compute_source_mode(
    writer: str,
    *,
    manual_cells: set[tuple[int, int]] | None = None,
    locked_cells: set[tuple[int, int]] | None = None,
    written_cells: set[tuple[int, int]] | None = None,
    previous_source: str | None = None,
) -> SourceMode:
    """推导整章来源投影。

    - 手工保存 → manual（不论保护集合）
    - 自动写入且写入格与手工/锁定格有交集 → mixed
    - 自动写入且前次来源是另一种自动写入 → mixed
    - 否则 → writer 本身
    """
    if writer == "manual":
        return "manual"
    protected = (manual_cells or set()) | (locked_cells or set())
    if written_cells and protected and written_cells & protected:
        return "mixed"
    if previous_source and previous_source in AUTO_WRITERS and previous_source != writer:
        return "mixed"
    return writer  # type: ignore[return-value]


def source_digest(data: Any) -> str:
    """对附注 data JSONB 计算内容摘要（写入后校验用；读取方比较两次摘要判断是否变化）。"""
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


def update_source_projection(
    record: Any,
    mode: SourceMode,
    *,
    operation_id: UUID | None = None,
    revision: int | None = None,
    digest: str | None = None,
) -> None:
    """统一更新四个来源投影字段（record 必须是 ConsolNoteData ORM 实例）。"""
    record.source_mode = mode
    record.source_operation_id = operation_id
    record.source_revision = revision
    record.source_digest = digest


__all__ = [
    "AUTO_WRITERS",
    "SOURCE_MODES",
    "SourceMode",
    "compute_source_mode",
    "source_digest",
    "update_source_projection",
]
