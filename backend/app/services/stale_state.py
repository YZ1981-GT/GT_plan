"""DisclosureNote stale 状态统一写入口。

本模块只管理 ``disclosure_notes.is_stale`` 与 ``stale_source``。
调用方负责事务生命周期；本模块只执行更新并 flush，不自行 commit、rollback 或开新连接。
其他模型（合并附注、报表、底稿预填、知识库）的 ``is_stale`` 不得经此模块写入。
"""
from __future__ import annotations

from enum import StrEnum
from typing import Sequence
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import DisclosureNote


class StaleSource(StrEnum):
    """附注过期来源稳定编码及其中文展示口径。"""

    WORKPAPER_SAVED = "workpaper_saved"
    REPORT = "report"
    REPORT_FALLBACK = "report_fallback"
    DISCLOSURE_REFRESH_NO_DATA = "disclosure_refresh_no_data"
    CONSOL_CHILD_CHANGED = "consol_child_changed"
    ROLLBACK = "rollback"
    ADJUSTMENT = "adjustment"
    ADJUSTMENT_REVIEW_REVOKED = "adjustment_review_revoked"
    ADJUSTMENT_BATCH_COMMITTED = "adjustment_batch_committed"
    LEDGER_ACTIVATED = "ledger_activated"
    WORKPAPER_REVIEWED = "workpaper_reviewed"
    FORMULA_SETTINGS = "formula_settings"
    TRIAL_BALANCE = "trial_balance"
    FORMULA_PUSH = "formula_push"
    WORKPAPER_SYNC = "workpaper_sync"
    LINKAGE_PROPAGATION = "linkage_propagation"


STALE_SOURCE_LABELS: dict[StaleSource, str] = {
    StaleSource.WORKPAPER_SAVED: "底稿已保存",
    StaleSource.REPORT: "报表已变化",
    StaleSource.REPORT_FALLBACK: "报表变化（未定位具体行）",
    StaleSource.DISCLOSURE_REFRESH_NO_DATA: "附注刷新时缺少数据",
    StaleSource.CONSOL_CHILD_CHANGED: "合并子企业附注已变化",
    StaleSource.ROLLBACK: "账套已回滚",
    StaleSource.ADJUSTMENT: "调整分录已变化",
    StaleSource.ADJUSTMENT_REVIEW_REVOKED: "调整分录复核已撤回",
    StaleSource.ADJUSTMENT_BATCH_COMMITTED: "调整分录批量提交",
    StaleSource.LEDGER_ACTIVATED: "账套已激活",
    StaleSource.WORKPAPER_REVIEWED: "底稿复核已通过",
    StaleSource.FORMULA_SETTINGS: "公式设置已变化",
    StaleSource.TRIAL_BALANCE: "试算表已变化",
    StaleSource.FORMULA_PUSH: "公式推送已完成",
    StaleSource.WORKPAPER_SYNC: "底稿数据已同步",
    StaleSource.LINKAGE_PROPAGATION: "依赖链数据已变化",
}


def stale_source_label(source: str | StaleSource | None) -> str:
    """把存储编码转换为中文；历史空值和未知值都安全降级。"""
    if source is None or not str(source).strip():
        return "来源未记录"
    try:
        normalized = StaleSource(str(source))
    except ValueError:
        return "其他数据变化"
    return STALE_SOURCE_LABELS[normalized]


def _source_value(source: str | StaleSource) -> str:
    try:
        normalized = source if isinstance(source, StaleSource) else StaleSource(str(source))
    except ValueError as exc:
        raise ValueError(f"不支持的附注 stale 来源：{source}") from exc
    value = normalized.value
    if len(value) > 32:  # 与 DisclosureNote.stale_source String(32) 保持同一约束
        raise ValueError(f"附注 stale 来源超出数据库长度限制：{value}")
    return value


def _base_conditions(project_id: UUID | str, year: int | None) -> list:
    conditions = [
        DisclosureNote.project_id == project_id,
        DisclosureNote.is_deleted == sa.false(),
    ]
    if year is not None:
        conditions.append(DisclosureNote.year == year)
    return conditions


async def mark_note_stale(
    db: AsyncSession,
    project_id: UUID | str,
    *,
    source: str | StaleSource,
    sections: Sequence[str] | None = None,
    year: int | None = None,
) -> int:
    """在调用方当前事务内标记附注过期并记录来源。"""
    source_value = _source_value(source)
    if sections is not None and not sections:
        return 0

    conditions = _base_conditions(project_id, year)
    if sections is not None:
        conditions.append(DisclosureNote.note_section.in_(list(dict.fromkeys(sections))))
    result = await db.execute(
        sa.update(DisclosureNote)
        .where(*conditions)
        .values(is_stale=True, stale_source=source_value)
        .execution_options(synchronize_session=False)
    )
    await db.flush()
    return int(result.rowcount or 0)


async def clear_note_stale(
    db: AsyncSession,
    project_id: UUID | str,
    *,
    sections: Sequence[str],
    year: int | None = None,
) -> int:
    """在调用方当前事务内清除成功重算章节的 stale 和来源。"""
    unique_sections = list(dict.fromkeys(sections))
    if not unique_sections:
        return 0

    conditions = _base_conditions(project_id, year)
    conditions.extend([
        DisclosureNote.note_section.in_(unique_sections),
        DisclosureNote.is_stale == sa.true(),
    ])
    result = await db.execute(
        sa.update(DisclosureNote)
        .where(*conditions)
        .values(is_stale=False, stale_source=None)
        .execution_options(synchronize_session=False)
    )
    await db.flush()
    return int(result.rowcount or 0)


__all__ = [
    "STALE_SOURCE_LABELS",
    "StaleSource",
    "clear_note_stale",
    "mark_note_stale",
    "stale_source_label",
]
