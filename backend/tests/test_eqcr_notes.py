"""EQCR 独立复核笔记端点测试

任务 10 验收：
- CRUD 笔记（GET/POST/PATCH/DELETE）
- 分享到项目组（share-to-team）
- 权限控制（只有创建人可编辑/删除/分享）
- 已分享笔记不可重复分享
- 分享后同步到 Project.wizard_state.communications
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.base import Base

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

# 注册所有模型
import app.models.core  # noqa: E402, F401
import app.models.audit_platform_models  # noqa: E402, F401
import app.models.report_models  # noqa: E402, F401
import app.models.workpaper_models  # noqa: E402, F401
import app.models.consolidation_models  # noqa: E402, F401
import app.models.staff_models  # noqa: E402, F401
import app.models.collaboration_models  # noqa: E402, F401
import app.models.ai_models  # noqa: E402, F401
import app.models.extension_models  # noqa: E402, F401
import app.models.gt_coding_models  # noqa: E402, F401
import app.models.t_account_models  # noqa: E402, F401
import app.models.attachment_models  # noqa: E402, F401
import app.models.phase13_models  # noqa: E402, F401
import app.models.eqcr_models  # noqa: E402, F401
import app.models.related_party_models  # noqa: E402, F401

from app.models.base import ProjectStatus, ProjectType, UserRole  # noqa: E402
from app.models.core import Project, User  # noqa: E402
from app.models.eqcr_models import EqcrReviewNote  # noqa: E402
from app.models.staff_models import ProjectAssignment, StaffMember  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def setup_data(db_session: AsyncSession):
    """创建用户 + 项目 + EQCR 委派。"""
    user = User(
        id=uuid.uuid4(),
        username="eqcr_user",
        email="eqcr@test.com",
        hashed_password="x",
        role=UserRole.partner,
    )
    other_user = User(
        id=uuid.uuid4(),
        username="other_user",
        email="other@test.com",
        hashed_password="x",
        role=UserRole.auditor,
    )
    admin_user = User(
        id=uuid.uuid4(),
        username="admin_user",
        email="admin@test.com",
        hashed_password="x",
        role=UserRole.admin,
    )
    project = Project(
        id=uuid.uuid4(),
        name="Test Project",
        client_name="Test Client",
        project_type=ProjectType.annual,
        status=ProjectStatus.execution,
        audit_period_end=date.today() + timedelta(days=30),
        wizard_state=None,
    )
    db_session.add_all([user, other_user, admin_user, project])
    await db_session.flush()

    staff = StaffMember(
        id=uuid.uuid4(),
        user_id=user.id,
        name="EQCR User",
        employee_no="E001",
    )
    db_session.add(staff)
    await db_session.flush()

    assignment = ProjectAssignment(
        id=uuid.uuid4(),
        project_id=project.id,
        staff_id=staff.id,
        role="eqcr",
    )
    db_session.add(assignment)
    await db_session.commit()

    return {
        "user": user,
        "other_user": other_user,
        "admin_user": admin_user,
        "project": project,
    }


# ---------------------------------------------------------------------------
# 路由端点测试（直接调用路由函数，绕过 HTTP 层）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_note(db_session: AsyncSession, setup_data):
    """POST 创建笔记：成功创建，默认 shared_to_team=false。"""
    from app.routers.eqcr import create_eqcr_note, EqcrNoteCreate

    data = setup_data
    payload = EqcrNoteCreate(title="关联交易可疑", content="需要进一步证据")
    result = await create_eqcr_note(
        project_id=data["project"].id,
        payload=payload,
        db=db_session,
        current_user=data["user"],
    )
    assert result["title"] == "关联交易可疑"
    assert result["content"] == "需要进一步证据"
    assert result["shared_to_team"] is False
    assert result["shared_at"] is None
    assert result["created_by"] == str(data["user"].id)


@pytest.mark.asyncio
async def test_list_notes_only_own(db_session: AsyncSession, setup_data):
    """GET 列出笔记：非 admin 只看自己的。"""
    from app.routers.eqcr import create_eqcr_note, list_eqcr_notes, EqcrNoteCreate

    data = setup_data
    # 创建两条笔记（不同用户）
    note1 = EqcrReviewNote(
        project_id=data["project"].id,
        title="Note by EQCR",
        content="content1",
        created_by=data["user"].id,
    )
    note2 = EqcrReviewNote(
        project_id=data["project"].id,
        title="Note by other",
        content="content2",
        created_by=data["other_user"].id,
    )
    db_session.add_all([note1, note2])
    await db_session.commit()

    # EQCR 用户只看到自己的
    result = await list_eqcr_notes(
        project_id=data["project"].id,
        db=db_session,
        current_user=data["user"],
    )
    assert len(result) == 1
    assert result[0]["title"] == "Note by EQCR"

    # admin 看到所有
    result_admin = await list_eqcr_notes(
        project_id=data["project"].id,
        db=db_session,
        current_user=data["admin_user"],
    )
    assert len(result_admin) == 2


@pytest.mark.asyncio
async def test_update_note(db_session: AsyncSession, setup_data):
    """PATCH 更新笔记：只有创建人可改。"""
    from app.routers.eqcr import update_eqcr_note, EqcrNoteUpdate

    data = setup_data
    note = EqcrReviewNote(
        project_id=data["project"].id,
        title="Original",
        content="original content",
        created_by=data["user"].id,
    )
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)

    # 创建人更新成功
    payload = EqcrNoteUpdate(title="Updated Title")
    result = await update_eqcr_note(
        project_id=data["project"].id,
        note_id=note.id,
        payload=payload,
        db=db_session,
        current_user=data["user"],
    )
    assert result["title"] == "Updated Title"

    # 其他人更新失败
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await update_eqcr_note(
            project_id=data["project"].id,
            note_id=note.id,
            payload=EqcrNoteUpdate(title="Hacked"),
            db=db_session,
            current_user=data["other_user"],
        )
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_delete_note(db_session: AsyncSession, setup_data):
    """DELETE 软删除笔记：只有创建人可删。"""
    from app.routers.eqcr import delete_eqcr_note

    data = setup_data
    note = EqcrReviewNote(
        project_id=data["project"].id,
        title="To Delete",
        content="will be deleted",
        created_by=data["user"].id,
    )
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)

    # 创建人删除成功
    result = await delete_eqcr_note(
        project_id=data["project"].id,
        note_id=note.id,
        db=db_session,
        current_user=data["user"],
    )
    assert result["detail"] == "已删除"

    # 验证软删除
    await db_session.refresh(note)
    assert note.is_deleted is True
    assert note.deleted_at is not None


@pytest.mark.asyncio
async def test_share_note_to_team(db_session: AsyncSession, setup_data):
    """POST share-to-team：分享后 shared_to_team=True，同步到 wizard_state。"""
    from app.routers.eqcr import share_note_to_team

    data = setup_data
    note = EqcrReviewNote(
        project_id=data["project"].id,
        title="Share This",
        content="important finding",
        created_by=data["user"].id,
    )
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)

    result = await share_note_to_team(
        note_id=note.id,
        db=db_session,
        current_user=data["user"],
    )
    assert result["shared_to_team"] is True
    assert result["shared_at"] is not None

    # 验证 Project.wizard_state.communications 已同步
    await db_session.refresh(data["project"])
    ws = data["project"].wizard_state
    assert ws is not None
    assert "communications" in ws
    assert len(ws["communications"]) == 1
    comm = ws["communications"][0]
    assert comm["source"] == "EQCR 独立复核笔记"
    assert comm["title"] == "Share This"
    assert comm["content"] == "important finding"
    assert comm["shared_by"] == str(data["user"].id)
    assert comm["note_id"] == str(note.id)


@pytest.mark.asyncio
async def test_share_note_already_shared_idempotent(db_session: AsyncSession, setup_data):
    """POST share-to-team：已分享的笔记再次分享返回 200（幂等），不报错。"""
    from app.routers.eqcr import share_note_to_team
    from datetime import datetime, timezone

    data = setup_data
    shared_time = datetime.now(timezone.utc)
    note = EqcrReviewNote(
        project_id=data["project"].id,
        title="Already Shared",
        content="content",
        shared_to_team=True,
        shared_at=shared_time,
        created_by=data["user"].id,
    )
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)

    # 幂等：已分享的笔记直接返回 200，不报错
    result = await share_note_to_team(
        note_id=note.id,
        db=db_session,
        current_user=data["user"],
    )
    assert result["shared_to_team"] is True
    assert result["shared_at"] is not None


@pytest.mark.asyncio
async def test_share_note_permission_denied(db_session: AsyncSession, setup_data):
    """POST share-to-team：非创建人不可分享。"""
    from app.routers.eqcr import share_note_to_team

    data = setup_data
    note = EqcrReviewNote(
        project_id=data["project"].id,
        title="Not Yours",
        content="content",
        created_by=data["user"].id,
    )
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await share_note_to_team(
            note_id=note.id,
            db=db_session,
            current_user=data["other_user"],
        )
    assert exc_info.value.status_code == 403
