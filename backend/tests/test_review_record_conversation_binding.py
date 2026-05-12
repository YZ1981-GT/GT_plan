"""复核批注 × 对话绑定 — 服务层逻辑测试

验证 R6 需求 3 AC2-5：
1. 关闭对话失败：对话下有未解决的 ReviewRecord 时拒绝关闭
2. 关闭对话成功：所有 ReviewRecord 已解决后可正常关闭
3. 去重校验：重复创建 IssueTicket 时返回已有工单 id

需求 3 AC2-5。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.base import Base

# SQLite JSONB 兼容
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

# 注册所有模型（确保 create_all 能建出所有表）
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
import app.models.phase10_models  # noqa: E402, F401
import app.models.phase13_models  # noqa: E402, F401
import app.models.eqcr_models  # noqa: E402, F401
import app.models.related_party_models  # noqa: E402, F401
import app.models.phase14_models  # noqa: E402, F401
import app.models.phase15_models  # noqa: E402, F401
import app.models.qc_rule_models  # noqa: E402, F401

from app.models.core import Project, User  # noqa: E402
from app.models.phase10_models import ReviewConversation  # noqa: E402
from app.models.phase15_models import IssueTicket  # noqa: E402
from app.models.phase15_enums import IssueSource, IssueStatus  # noqa: E402
from app.models.workpaper_models import (  # noqa: E402
    ReviewCommentStatus,
    ReviewRecord,
    WorkingPaper,
    WpIndex,
)


@pytest_asyncio.fixture
async def db_session():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(
        _engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _create_user(db: AsyncSession) -> uuid.UUID:
    """创建测试用户并返回 id。"""
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        username=f"test_{user_id.hex[:8]}",
        email=f"{user_id.hex[:8]}@test.com",
        hashed_password="hashed",
        role="admin",
    )
    db.add(user)
    await db.flush()
    return user_id


async def _create_project(db: AsyncSession) -> uuid.UUID:
    """创建测试项目并返回 id。"""
    project_id = uuid.uuid4()
    project = Project(
        id=project_id,
        name="测试项目",
        client_name="测试客户",
        status="execution",
    )
    db.add(project)
    await db.flush()
    return project_id


async def _create_conversation(
    db: AsyncSession, project_id: uuid.UUID, initiator_id: uuid.UUID, target_id: uuid.UUID
) -> uuid.UUID:
    """创建测试对话并返回 id。"""
    conv_id = uuid.uuid4()
    conv = ReviewConversation(
        id=conv_id,
        project_id=project_id,
        initiator_id=initiator_id,
        target_id=target_id,
        related_object_type="workpaper",
        title="测试对话",
        status="open",
    )
    db.add(conv)
    await db.flush()
    return conv_id


async def _create_wp_and_index(
    db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID
) -> uuid.UUID:
    """创建底稿索引 + 底稿文件并返回 working_paper.id。"""
    wp_index_id = uuid.uuid4()
    wp_index = WpIndex(
        id=wp_index_id,
        project_id=project_id,
        wp_code="D-100",
        wp_name="测试底稿",
    )
    db.add(wp_index)
    await db.flush()

    wp_id = uuid.uuid4()
    wp = WorkingPaper(
        id=wp_id,
        project_id=project_id,
        wp_index_id=wp_index_id,
        file_path="/tmp/test.xlsx",
        source_type="template",
        assigned_to=user_id,
        created_by=user_id,
    )
    db.add(wp)
    await db.flush()
    return wp_id


# ── 场景 1：关闭对话失败 — 有未解决的 ReviewRecord ─────────────────


@pytest.mark.asyncio
async def test_close_conversation_fails_with_unresolved_records(db_session: AsyncSession):
    """对话下有未解决的 ReviewRecord 时，close_conversation 应拒绝并返回错误码。"""
    user_id = await _create_user(db_session)
    target_id = await _create_user(db_session)
    project_id = await _create_project(db_session)
    conv_id = await _create_conversation(db_session, project_id, user_id, target_id)
    wp_id = await _create_wp_and_index(db_session, project_id, user_id)

    # 创建一条未解决的 ReviewRecord 绑定到此对话
    record = ReviewRecord(
        id=uuid.uuid4(),
        working_paper_id=wp_id,
        comment_text="需要补充说明",
        commenter_id=user_id,
        status=ReviewCommentStatus.open,
        conversation_id=conv_id,
    )
    db_session.add(record)
    await db_session.flush()

    # 尝试关闭对话
    from app.services.review_conversation_service import ReviewConversationService

    svc = ReviewConversationService()
    result = await svc.close_conversation(db_session, conv_id, user_id)

    # 应返回错误码而非正常关闭
    assert result.get("error_code") == "CONVERSATION_HAS_OPEN_RECORDS"
    assert result["open_record_count"] == 1

    # 对话状态应仍为 open
    conv = await db_session.get(ReviewConversation, conv_id)
    assert conv.status == "open"


# ── 场景 2：关闭对话成功 — 所有 ReviewRecord 已解决 ─────────────────


@pytest.mark.asyncio
async def test_close_conversation_succeeds_after_resolving_records(db_session: AsyncSession):
    """所有 ReviewRecord 已解决后，close_conversation 应正常关闭对话。"""
    user_id = await _create_user(db_session)
    target_id = await _create_user(db_session)
    project_id = await _create_project(db_session)
    conv_id = await _create_conversation(db_session, project_id, user_id, target_id)
    wp_id = await _create_wp_and_index(db_session, project_id, user_id)

    # 创建一条已解决的 ReviewRecord 绑定到此对话
    record = ReviewRecord(
        id=uuid.uuid4(),
        working_paper_id=wp_id,
        comment_text="已修正",
        commenter_id=user_id,
        status=ReviewCommentStatus.resolved,
        conversation_id=conv_id,
        resolved_by=user_id,
        resolved_at=datetime.now(timezone.utc),
    )
    db_session.add(record)
    await db_session.flush()

    # 关闭对话应成功
    from app.services.review_conversation_service import ReviewConversationService

    svc = ReviewConversationService()
    result = await svc.close_conversation(db_session, conv_id, user_id)

    # 应返回正常的对话字典（无 error_code）
    assert "error_code" not in result
    assert result["status"] == "closed"
    assert result["id"] == str(conv_id)

    # 对话状态应为 closed
    conv = await db_session.get(ReviewConversation, conv_id)
    assert conv.status == "closed"
    assert conv.closed_at is not None


# ── 场景 3：去重校验 — 重复创建 IssueTicket 返回已有工单 ─────────────


@pytest.mark.asyncio
async def test_duplicate_ticket_creation_returns_existing(db_session: AsyncSession):
    """已存在 IssueTicket(source='review_comment', source_ref_id=record.id) 时，
    wp_review_service 的去重逻辑应返回已有工单而非重复创建。"""
    user_id = await _create_user(db_session)
    project_id = await _create_project(db_session)
    wp_id = await _create_wp_and_index(db_session, project_id, user_id)

    # 创建一条 ReviewRecord
    record_id = uuid.uuid4()
    record = ReviewRecord(
        id=record_id,
        working_paper_id=wp_id,
        comment_text="数据不一致",
        commenter_id=user_id,
        status=ReviewCommentStatus.open,
    )
    db_session.add(record)
    await db_session.flush()

    # 手动创建一张已存在的 IssueTicket（模拟首次创建成功）
    existing_ticket_id = uuid.uuid4()
    existing_ticket = IssueTicket(
        id=existing_ticket_id,
        project_id=project_id,
        wp_id=wp_id,
        source=IssueSource.review_comment.value,
        source_ref_id=record_id,
        severity="major",
        category="procedure_incomplete",
        title="复核退回：数据不一致",
        owner_id=user_id,
        status=IssueStatus.open.value,
        trace_id=f"trc_test_{uuid.uuid4().hex[:12]}",
    )
    db_session.add(existing_ticket)
    await db_session.flush()

    # 调用 _build_and_persist_issue_ticket 应返回已有工单（去重）
    from app.services.wp_review_service import _build_and_persist_issue_ticket

    result_ticket = await _build_and_persist_issue_ticket(
        db_session,
        review_record=record,
        commenter_id=user_id,
    )

    # 应返回已有工单而非新建
    assert result_ticket.id == existing_ticket_id
    assert result_ticket.source_ref_id == record_id

    # 确认数据库中只有 1 张工单
    import sqlalchemy as sa

    count_stmt = (
        sa.select(sa.func.count())
        .select_from(IssueTicket)
        .where(
            IssueTicket.source == IssueSource.review_comment.value,
            IssueTicket.source_ref_id == record_id,
        )
    )
    count_result = await db_session.execute(count_stmt)
    assert count_result.scalar() == 1
