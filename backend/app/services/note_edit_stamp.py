"""附注章节「最近一次编辑」盖章（disclosure-note-doc-upload-and-batch-fill 第 24 组）。

``disclosure_notes.updated_at`` 只有 ``server_default``、没有 ``onupdate``：哪条写入路径不显式赋值，
时间就停在上一次。首版单章保存（``PUT /api/disclosure-notes/{note_id}``）从不赋值 ⇒ 时间停在最近一次
批量写入，批量写入 apply 的 ``expected_updated_at`` 复核对单章编辑不起作用，底稿 HTML 同步的
「附注侧有手动编辑」冲突判定（``note.updated_at > last_sync_at``）也看不见编辑器里的修改。

语义：最近一次**有人**对本章做的编辑（含批量写入、底稿推送这类以用户身份发起的写入）。
模板重新生成、取数刷新、过期标记、同步簿记不盖章 —— 不是人工编辑，盖了会让上面的冲突判定误报。
不用模型级 ``onupdate``：它对每次 ORM flush / ``sa.update`` 都生效，过期标记与同步簿记也会改时间。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import DisclosureNote

__all__ = ["stamp_note_edit", "stamp_section_edit"]


def stamp_note_edit(note: Any, user_id: UUID | None) -> None:
    """已加载的章节对象：时间取调用这一刻（不用库 ``now()``：那是事务开始时间）。"""
    note.updated_at = datetime.now(timezone.utc)
    if user_id is not None:
        note.updated_by = user_id


async def stamp_section_edit(db: AsyncSession, *, project_id: UUID, year: int, note_section: str,
                             user_id: UUID | None) -> None:
    """按章节号盖章：改写发生在服务内部、路由手里没有章节对象时用（公式类端点）。"""
    values: dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
    if user_id is not None:
        values["updated_by"] = user_id
    await db.execute(
        sa.update(DisclosureNote)
        .where(DisclosureNote.project_id == project_id, DisclosureNote.year == year,
               DisclosureNote.note_section == note_section, DisclosureNote.is_deleted == sa.false())
        .values(**values)
    )
