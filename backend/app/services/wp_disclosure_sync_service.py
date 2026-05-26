"""C 类底稿 → disclosure_notes 模块单向同步服务

按 design §12.1 推荐选项 A：底稿是编辑入口，disclosure_notes 模块仅作展示+独立编辑（向后兼容）。
当用户在 C 类附注底稿 sheet 保存数据时，自动 push 到 disclosure_notes 表对应 section。

Validates: Requirements 3.11.5 §4.2（附注双源问题）+ design §12.1
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import User
from app.models.report_models import (
    ContentType,
    DisclosureNote,
    NoteStatus,
    SourceTemplate,
)

logger = logging.getLogger(__name__)


def _count_rows_synced(sub_table_data: dict[str, list[dict]] | None) -> int:
    """统计 sub_table_data 中所有子表行数总和。"""
    if not sub_table_data:
        return 0
    total = 0
    for rows in sub_table_data.values():
        if isinstance(rows, list):
            total += len(rows)
    return total


def _derive_section_title(section_id: str) -> str:
    """从 section_id 派生默认标题（用于新建场景）。

    Examples:
        "五-1-1 应收账款" → "应收账款"
        "五-1-1" → "五-1-1"
    """
    if not section_id:
        return ""
    parts = section_id.strip().split(maxsplit=1)
    if len(parts) == 2:
        return parts[1]
    return section_id


def _derive_year(payload_year: int | None) -> int:
    """优先使用 payload 中的 year，否则取当前年（兜底）。"""
    if payload_year and isinstance(payload_year, int):
        return payload_year
    return datetime.now(timezone.utc).year


async def sync_from_workpaper(
    db: AsyncSession,
    project_id: UUID,
    *,
    wp_id: UUID,
    sheet_name: str,
    section_id: str,
    sub_table_data: dict[str, list[dict]],
    current_standard: str,
    user: User,
    year: int | None = None,
) -> dict[str, Any]:
    """C 类底稿 sheet 保存时，将 sub_table_data 同步到 disclosure_notes 模块对应 section。

    行为：
    - 查 disclosure_notes WHERE (project_id, year, note_section=section_id, is_deleted=false)
    - 已存在：更新 table_data（merge sub_table_data）+ 同步标记
    - 不存在：新建一条记录（status=draft，content_type=table）+ 同步标记

    Returns:
        {
            "success": True,
            "section_id": str,
            "synced_at": ISO timestamp,
            "rows_synced": int,
            "created": bool,  # 本次是否新建（True=create，False=update）
        }
    """
    if not section_id or not section_id.strip():
        raise ValueError("section_id 不能为空")
    section_id = section_id.strip()

    target_year = _derive_year(year)
    now = datetime.now(timezone.utc)
    rows_synced = _count_rows_synced(sub_table_data)

    # ─── 查现有记录 ───────────────────────────────────────────────────
    stmt = sa.select(DisclosureNote).where(
        DisclosureNote.project_id == project_id,
        DisclosureNote.year == target_year,
        DisclosureNote.note_section == section_id,
        DisclosureNote.is_deleted == sa.false(),
    )
    result = await db.execute(stmt)
    note = result.scalar_one_or_none()

    # 构建合并后的 table_data
    # 约定：将 C sheet 的 sub_table_data 整体写入 table_data["sub_table_data"]，
    #     并保留 _source / _current_standard / _last_sync_wp / _last_sync_sheet 元数据
    new_table_data: dict[str, Any] = dict(note.table_data) if note and note.table_data else {}
    new_table_data["sub_table_data"] = dict(sub_table_data or {})
    new_table_data["_source"] = "workpaper"
    new_table_data["_current_standard"] = current_standard
    new_table_data["_last_sync_wp_id"] = str(wp_id)
    new_table_data["_last_sync_sheet"] = sheet_name
    new_table_data["_last_sync_at"] = now.isoformat()

    created = False

    if note is None:
        # ─── 新建 ─────────────────────────────────────────────────────
        # 从 current_standard（如 "soe_standalone" / "listed_standalone"）派生 source_template
        source_template_value: SourceTemplate | None = None
        if current_standard:
            cs = current_standard.lower()
            if cs.startswith("listed"):
                source_template_value = SourceTemplate.listed
            elif cs.startswith("soe"):
                source_template_value = SourceTemplate.soe
        note = DisclosureNote(
            project_id=project_id,
            year=target_year,
            note_section=section_id,
            section_title=_derive_section_title(section_id),
            content_type=ContentType.table,
            table_data=new_table_data,
            source_template=source_template_value,
            status=NoteStatus.draft,
            last_sync_source="workpaper",
            last_sync_wp_id=wp_id,
            last_sync_at=now,
            last_sync_user_id=user.id,
            updated_by=user.id,
        )
        db.add(note)
        created = True
        logger.info(
            "wp_disclosure_sync: created new disclosure_note "
            "project=%s section=%s wp_id=%s rows=%d",
            project_id, section_id, wp_id, rows_synced,
        )
    else:
        # ─── 更新 ─────────────────────────────────────────────────────
        note.table_data = new_table_data
        note.last_sync_source = "workpaper"
        note.last_sync_wp_id = wp_id
        note.last_sync_at = now
        note.last_sync_user_id = user.id
        note.updated_by = user.id
        note.updated_at = now
        logger.info(
            "wp_disclosure_sync: updated disclosure_note "
            "id=%s section=%s wp_id=%s rows=%d",
            note.id, section_id, wp_id, rows_synced,
        )

    await db.commit()

    return {
        "success": True,
        "section_id": section_id,
        "synced_at": now.isoformat(),
        "rows_synced": rows_synced,
        "created": created,
    }
