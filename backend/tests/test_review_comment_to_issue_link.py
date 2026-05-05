"""R1 需求 2：复核意见 → IssueTicket 工单联动集成测试

覆盖：
  1. 正常：退回 + 意见 → ReviewRecord 创建 + IssueTicket 创建 +
     ``source_ref_id`` 与 ``source='review_comment'`` 对齐。
  2. 失败守卫：IssueTicket 创建抛异常 → ReviewRecord 仍成功 +
     ``REVIEW_RECORD_CREATED`` 事件被发出（外层事务不污染）。
  3. 补偿订阅：``event_handlers`` 订阅触发 → 若无对应 IssueTicket 则补建，
     二次触发幂等（不重复创建）。

Validates: Requirements 2 (refinement-round1-review-closure)
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.audit_platform_schemas import EventPayload, EventType
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType
from app.models.phase15_enums import IssueSource
from app.models.phase15_models import IssueTicket
from app.models.workpaper_models import (
    ReviewCommentStatus,
    ReviewRecord,
    WorkingPaper,
    WpFileStatus,
    WpIndex,
    WpSourceType,
    WpStatus,
)

# SQLite 不支持 JSONB，用 JSON 兼容
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

FAKE_USER_ID = uuid.uuid4()
FAKE_REVIEWER_ID = uuid.uuid4()
FAKE_PROJECT_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded(db_session: AsyncSession):
    project = Project(
        id=FAKE_PROJECT_ID,
        name="测试项目_2025",
        client_name="测试客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=FAKE_USER_ID,
    )
    db_session.add(project)
    await db_session.flush()

    idx = WpIndex(
        project_id=FAKE_PROJECT_ID,
        wp_code="B1-1",
        wp_name="穿行测试底稿",
        audit_cycle="B",
        status=WpStatus.in_progress,
    )
    db_session.add(idx)
    await db_session.flush()

    wp = WorkingPaper(
        project_id=FAKE_PROJECT_ID,
        wp_index_id=idx.id,
        file_path=f"{FAKE_PROJECT_ID}/2025/B1-1.xlsx",
        source_type=WpSourceType.template,
        status=WpFileStatus.draft,
        file_version=1,
        created_by=FAKE_USER_ID,
        assigned_to=FAKE_USER_ID,
    )
    db_session.add(wp)
    await db_session.commit()

    return {"wp": wp, "project_id": FAKE_PROJECT_ID}


# ---------------------------------------------------------------------------
# 情形 1：正常路径 — 退回 + 意见 → ReviewRecord + IssueTicket 对齐
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reject_comment_creates_review_record_and_issue_ticket(
    db_session, seeded
):
    """Validates: Requirements 2 (R1)"""
    from app.services.wp_review_service import WpReviewService

    svc = WpReviewService()
    result = await svc.add_comment(
        db=db_session,
        working_paper_id=seeded["wp"].id,
        commenter_id=FAKE_REVIEWER_ID,
        comment_text="B1-1 单元格金额与试算表不一致，请核对",
        cell_reference="B5",
        is_reject=True,
    )
    await db_session.commit()

    # ReviewRecord 必须写入
    assert result["status"] == ReviewCommentStatus.open.value
    review_id = uuid.UUID(result["id"])
    review = await db_session.get(ReviewRecord, review_id)
    assert review is not None
    assert review.cell_reference == "B5"

    # IssueTicket 必须同步创建
    tickets = (
        await db_session.execute(
            sa.select(IssueTicket).where(IssueTicket.source_ref_id == review_id)
        )
    ).scalars().all()
    assert len(tickets) == 1
    ticket = tickets[0]
    assert ticket.source == IssueSource.review_comment.value
    assert ticket.wp_id == seeded["wp"].id
    assert ticket.project_id == seeded["project_id"]
    # owner_id 应该是底稿 assigned_to（编制人）
    assert ticket.owner_id == FAKE_USER_ID
    assert "复核退回" in ticket.title
    assert ticket.description == "B1-1 单元格金额与试算表不一致，请核对"
    assert ticket.status == "open"
    assert ticket.severity == "major"
    assert ticket.trace_id  # 必填，非空


@pytest.mark.asyncio
async def test_non_reject_add_comment_does_not_create_ticket(db_session, seeded):
    """非退回场景（is_reject=False）不应创建工单。"""
    from app.services.wp_review_service import WpReviewService

    svc = WpReviewService()
    result = await svc.add_comment(
        db=db_session,
        working_paper_id=seeded["wp"].id,
        commenter_id=FAKE_REVIEWER_ID,
        comment_text="建议补充说明",
        is_reject=False,
    )
    await db_session.commit()

    review_id = uuid.UUID(result["id"])
    tickets = (
        await db_session.execute(
            sa.select(IssueTicket).where(IssueTicket.source_ref_id == review_id)
        )
    ).scalars().all()
    assert tickets == []


# ---------------------------------------------------------------------------
# 情形 2：失败守卫 — IssueTicket 创建抛异常，ReviewRecord 仍成功
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reject_comment_does_not_block_on_ticket_failure(db_session, seeded):
    """mock IssueTicket 创建抛异常 → ReviewRecord 仍成功，事件发出。"""
    from app.services import wp_review_service as wp_review_module
    from app.services.wp_review_service import WpReviewService

    published: list[EventPayload] = []

    async def _capture(payload: EventPayload) -> None:
        published.append(payload)

    from app.services.event_bus import event_bus

    event_bus.subscribe(EventType.REVIEW_RECORD_CREATED, _capture)

    try:
        with patch.object(
            wp_review_module,
            "_build_and_persist_issue_ticket",
            side_effect=RuntimeError("boom: ticket service down"),
        ):
            svc = WpReviewService()
            result = await svc.add_comment(
                db=db_session,
                working_paper_id=seeded["wp"].id,
                commenter_id=FAKE_REVIEWER_ID,
                comment_text="必须退回修改",
                is_reject=True,
            )
            await db_session.commit()
    finally:
        # Clean up subscription
        handlers = event_bus._handlers.get(EventType.REVIEW_RECORD_CREATED, [])
        if _capture in handlers:
            handlers.remove(_capture)

    # ReviewRecord 必须仍成功写入
    review_id = uuid.UUID(result["id"])
    review = await db_session.get(ReviewRecord, review_id)
    assert review is not None, "ReviewRecord 应在工单失败时仍保留"

    # 不应有对应 IssueTicket
    tickets = (
        await db_session.execute(
            sa.select(IssueTicket).where(IssueTicket.source_ref_id == review_id)
        )
    ).scalars().all()
    assert tickets == []

    # 必须发出 REVIEW_RECORD_CREATED 事件（供补偿）
    assert len(published) >= 1
    evt = published[-1]
    assert evt.event_type == EventType.REVIEW_RECORD_CREATED
    assert evt.extra.get("review_record_id") == str(review_id)
    assert evt.extra.get("ticket_created") is False


# ---------------------------------------------------------------------------
# 情形 3：补偿订阅 — 触发 REVIEW_RECORD_CREATED → 补建 + 幂等
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compensation_handler_rebuilds_missing_ticket(db_session, seeded):
    """直接调用补偿逻辑：缺失工单 → 补建；再次触发 → 幂等不重复。

    测试直接覆盖 ``_build_and_persist_issue_ticket`` 路径 + 幂等检查，
    不依赖 async_session_factory（默认指向生产 DB，集成测试走独立 engine）。
    """
    from app.models.workpaper_models import ReviewCommentStatus
    from app.services.wp_review_service import _build_and_persist_issue_ticket

    # 先创建一条 ReviewRecord 但不创建 IssueTicket（模拟工单创建失败后的状态）
    review = ReviewRecord(
        working_paper_id=seeded["wp"].id,
        cell_reference="C10",
        comment_text="补偿测试：请修正",
        commenter_id=FAKE_REVIEWER_ID,
        status=ReviewCommentStatus.open,
    )
    db_session.add(review)
    await db_session.commit()

    # 模拟补偿逻辑（与 event_handlers 中的 handler 等价的幂等路径）:
    async def _compensate() -> None:
        existing = (
            await db_session.execute(
                sa.select(IssueTicket).where(
                    IssueTicket.source_ref_id == review.id,
                    IssueTicket.source == IssueSource.review_comment.value,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return
        await _build_and_persist_issue_ticket(
            db_session,
            review_record=review,
            commenter_id=FAKE_REVIEWER_ID,
        )

    # 第一次触发：应补建一条
    await _compensate()
    await db_session.commit()

    tickets = (
        await db_session.execute(
            sa.select(IssueTicket).where(IssueTicket.source_ref_id == review.id)
        )
    ).scalars().all()
    assert len(tickets) == 1, "补偿应补建一条 IssueTicket"

    first_ticket_id = tickets[0].id

    # 第二次触发：幂等，不应重复创建
    await _compensate()
    await db_session.commit()

    tickets2 = (
        await db_session.execute(
            sa.select(IssueTicket).where(IssueTicket.source_ref_id == review.id)
        )
    ).scalars().all()
    assert len(tickets2) == 1, "补偿必须幂等，不得重复创建"
    assert tickets2[0].id == first_ticket_id


@pytest.mark.asyncio
async def test_review_record_created_event_type_exists():
    """验证枚举 REVIEW_RECORD_CREATED 已在 EventType 中注册。"""
    assert EventType.REVIEW_RECORD_CREATED.value == "review_record.created"
