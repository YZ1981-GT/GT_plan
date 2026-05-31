"""附注级合并穿透服务（consol-phase3-frontend-drilldown / Phase 3）.

读 `disclosure_notes.consolidation_breakdown` provenance（V2 generate_full_consol_notes
汇总时写入），反查"该合并章节由哪些子公司哪些章节贡献多少"，供前端
ConsolBreakdownDialog(source=note) 穿透展示。

数据契约（mirror Phase 0 consol_trial provenance / 报表穿透 report/consol-breakdown）：
    {
      "section_id": str,
      "section_title": str,
      "by_company": [{company_code, company_name, section_title, amount}],
      "computed_at": str | None,
      "has_breakdown": bool,
      "message": str | None,   # has_breakdown=false 时的友好提示（EH1/EH3）
    }

错误处理（design.md §七 EH1/EH3 / 需求 2.5 / 风险 R1）：
- 章节不存在或 consolidation_breakdown 为空/None（未跑 V2）→ 返回空 by_company +
  has_breakdown=false + 中文友好提示，HTTP 200（不 404/500），不阻断前端。

Validates: Requirements 2.3, 2.4, 2.5; Properties T2; Error scenarios EH1, EH3.
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import DisclosureNote

logger = logging.getLogger(__name__)

# 无合并明细时的中文友好提示（EH1/EH3）
EMPTY_BREAKDOWN_MESSAGE = "该章节暂无合并明细，请先用 V2 生成合并附注"


async def get_note_consol_breakdown(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    section_id: str,
) -> dict:
    """获取某合并附注章节的子公司贡献明细（穿透）.

    Args:
        db: AsyncSession
        project_id: 合并母项目 ID
        year: 报告年度
        section_id: 附注章节 ID（优先匹配 section_id，回退 note_section）

    Returns:
        dict：见模块 docstring 数据契约。无 breakdown 时友好空返回（HTTP 200）。
    """
    note = await _load_note(db, project_id, year, section_id)

    breakdown = note.consolidation_breakdown if note is not None else None
    by_company = (breakdown or {}).get("by_company") if isinstance(breakdown, dict) else None

    # 空/None/非列表 → 友好空返回（EH1/EH3）
    if not by_company:
        return {
            "section_id": section_id,
            "section_title": note.section_title if note is not None else None,
            "by_company": [],
            "computed_at": None,
            "has_breakdown": False,
            "message": EMPTY_BREAKDOWN_MESSAGE,
        }

    return {
        "section_id": section_id,
        "section_title": note.section_title,
        "by_company": by_company,
        "computed_at": breakdown.get("computed_at"),
        "has_breakdown": True,
        "message": None,
    }


async def _load_note(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    section_id: str,
) -> DisclosureNote | None:
    """加载 (project_id, year, section_id) 的附注行；优先 section_id，回退 note_section."""
    # 优先按稳定 section_id 匹配
    stmt = (
        select(DisclosureNote)
        .where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.section_id == section_id,
            DisclosureNote.is_deleted.is_(False),
        )
        .limit(1)
    )
    result = await db.execute(stmt)
    note = result.scalar_one_or_none()
    if note is not None:
        return note

    # 回退：按 note_section 匹配（老数据可能未填 section_id）
    stmt_fallback = (
        select(DisclosureNote)
        .where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.note_section == section_id,
            DisclosureNote.is_deleted.is_(False),
        )
        .limit(1)
    )
    result_fallback = await db.execute(stmt_fallback)
    return result_fallback.scalar_one_or_none()
