"""软删章节复活（唯一键含软删行）回归守卫。

背景（真实缺陷，live 实测）：
``uq_disclosure_notes_project_year_section`` 建在 (project_id, year, note_section)
且**不含 is_deleted** → 被软删的章节仍占唯一键。同步只查 active 行时会走 INSERT，
撞唯一键 → `附注同步失败: UniqueViolationError`（审计师删除某章节后底稿再同步必 500）。

修复：查不到 active 行时再查软删行，命中则复活复用（is_deleted=False）走更新分支。

Properties:
- P-R1 命中软删行 → 复活复用同一行（不 INSERT，不撞唯一键），返回 revived=True
- P-R2 复活行保留原 id（不新建）
- P-R3 无任何同键行 → 仍走新建（created=True/revived=False，零回归）
- P-R4 命中 active 行 → 不查软删分支（既有更新路径零回归）
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import DisclosureNote
from app.services.wp_disclosure_sync_service import sync_from_workpaper

PROJECT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WP_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
NOTE_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
SECTION = "五、96"


def _user() -> MagicMock:
    u = MagicMock()
    u.id = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
    return u


def _scalar_result(value):
    res = MagicMock()
    res.scalar_one_or_none = MagicMock(return_value=value)
    return res


def _make_db(*, active=None, deleted=None, audit_year: int | None = 2025) -> MagicMock:
    """按调用顺序返回：audit_year → active note → (可选) deleted note。"""
    db = MagicMock(spec=AsyncSession)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    sequence = [_scalar_result(audit_year), _scalar_result(active)]
    if active is None:
        sequence.append(_scalar_result(deleted))
    db.execute = AsyncMock(side_effect=sequence)
    return db


def _deleted_note() -> DisclosureNote:
    note = DisclosureNote(
        project_id=PROJECT_ID,
        year=2025,
        note_section=SECTION,
        section_title=SECTION,
        table_data={},
        is_deleted=True,
    )
    note.id = NOTE_ID
    return note


@pytest.mark.asyncio
async def test_revives_soft_deleted_note_instead_of_insert():
    """P-R1 + P-R2：复活软删行，不 INSERT。"""
    note = _deleted_note()
    db = _make_db(active=None, deleted=note)

    result = await sync_from_workpaper(
        db,
        PROJECT_ID,
        wp_id=WP_ID,
        sheet_name="X",
        section_id=SECTION,
        sub_table_data={"表": [{"label": "a"}]},
        current_standard="listed_standalone",
        user=_user(),
        commit=False,
    )

    assert result["revived"] is True
    assert result["created"] is False
    assert note.is_deleted is False          # 已复活
    assert note.id == NOTE_ID                # P-R2 复用同一行
    db.add.assert_not_called()               # 不 INSERT → 不撞唯一键


@pytest.mark.asyncio
async def test_creates_when_no_row_at_all():
    """P-R3：无同键行时仍走新建（零回归）。"""
    db = _make_db(active=None, deleted=None)

    result = await sync_from_workpaper(
        db,
        PROJECT_ID,
        wp_id=WP_ID,
        sheet_name="X",
        section_id=SECTION,
        sub_table_data={"表": [{"label": "a"}]},
        current_standard="listed_standalone",
        user=_user(),
        commit=False,
    )

    assert result["created"] is True
    assert result["revived"] is False
    db.add.assert_called_once()


@pytest.mark.asyncio
async def test_active_note_path_unchanged():
    """P-R4：命中 active 行走既有更新路径，不触发软删查询。"""
    active = DisclosureNote(
        project_id=PROJECT_ID,
        year=2025,
        note_section=SECTION,
        section_title="应付票据",
        table_data={},
        is_deleted=False,
    )
    active.id = NOTE_ID
    db = _make_db(active=active)

    result = await sync_from_workpaper(
        db,
        PROJECT_ID,
        wp_id=WP_ID,
        sheet_name="X",
        section_id=SECTION,
        sub_table_data={"表": [{"label": "a"}]},
        current_standard="listed_standalone",
        user=_user(),
        commit=False,
    )

    assert result["created"] is False
    assert result["revived"] is False
    db.add.assert_not_called()
    # audit_year + active 查询共 2 次；没有第 3 次（软删分支未触达）
    assert db.execute.await_count == 2
