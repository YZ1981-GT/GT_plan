"""R1 需求 2：工单 → ReviewRecord / WorkingPaper.review_status 反向同步集成测试

覆盖（见 ``refinement-round1-review-closure/tasks.md`` Task 6）：

正常路径
  1. 工单 ``open → in_fix → pending_recheck`` → 关联 ``ReviewRecord.reply_text``
     追加 "已整改，请复验"、状态 open → replied、``replied_by/replied_at`` 更新。
  2. 工单 ``pending_recheck → closed`` → ``ReviewRecord.status=resolved`` +
     关联底稿 ``review_status`` 从 ``level1_rejected`` 回退至 ``pending_level1``。
  3. 同链路下底稿若是 ``level2_rejected``，closed 时回退到 ``pending_level2``。

边界
  4. ``source='L2'``（非 review_comment）工单状态变更 → 不触碰 ReviewRecord
     与底稿 review_status（纯旁路）。
  5. ``source_ref_id`` 指向的 ReviewRecord 不存在（例如已软删除）→ 工单
     状态仍成功变更，仅记 warning。
  6. WorkingPaper.review_status 非 rejected（例如已是 ``pending_level1``）→
     closed 时不回退，避免打乱流程。

幂等
  7. 连续两次切 ``closed`` → 第二次因合法状态迁移校验先被阻断（预期行为），
     若跳过校验直接调 helper，ReviewRecord.status 仍 resolved 不变、底稿
     review_status 已回退后再触发也不再重复回退。

Validates: Requirements 2 (refinement-round1-review-closure)
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.base import Base

# 显式导入 trace_event / phase14/phase15 模型以确保 Base.metadata.create_all
# 创建 `trace_events` 等表。否则 issue_ticket_service.update_status 内部的
# trace_event_service.write 首次调用会懒加载模型但此时表已未创建，
# INSERT 失败并污染会话进入 PendingRollbackError。
import app.models.phase14_models  # noqa: F401
import app.models.phase15_models  # noqa: F401
from app.models.core import Project, ProjectStatus, ProjectType
from app.models.phase15_enums import IssueSource, IssueStatus
from app.models.phase15_models import IssueTicket
from app.models.workpaper_models import (
    ReviewCommentStatus,
    ReviewRecord,
    WorkingPaper,
    WpFileStatus,
    WpIndex,
    WpReviewStatus,
    WpSourceType,
    WpStatus,
)

# SQLite 不支持 JSONB，用 JSON 兼容
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

FAKE_AUTHOR_ID = uuid.uuid4()  # 编制人
FAKE_REVIEWER_ID = uuid.uuid4()  # 复核人
FAKE_PROJECT_ID = uuid.uuid4()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
    """初始化一套 Project + WpIndex + WorkingPaper + ReviewRecord + IssueTicket"""
    project = Project(
        id=FAKE_PROJECT_ID,
        name="工单反向同步_测试项目",
        client_name="测试客户A",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=FAKE_AUTHOR_ID,
    )
    db_session.add(project)
    await db_session.flush()

    idx = WpIndex(
        project_id=FAKE_PROJECT_ID,
        wp_code="B2-1",
        wp_name="应收账款函证底稿",
        audit_cycle="B",
        status=WpStatus.in_progress,
    )
    db_session.add(idx)
    await db_session.flush()

    wp = WorkingPaper(
        project_id=FAKE_PROJECT_ID,
        wp_index_id=idx.id,
        file_path=f"{FAKE_PROJECT_ID}/2025/B2-1.xlsx",
        source_type=WpSourceType.template,
        status=WpFileStatus.revision_required,
        review_status=WpReviewStatus.level1_rejected,
        file_version=1,
        created_by=FAKE_AUTHOR_ID,
        assigned_to=FAKE_AUTHOR_ID,
        reviewer=FAKE_REVIEWER_ID,
    )
    db_session.add(wp)
    await db_session.flush()

    review = ReviewRecord(
        working_paper_id=wp.id,
        cell_reference="B5",
        comment_text="金额与试算表不符，请核对",
        commenter_id=FAKE_REVIEWER_ID,
        status=ReviewCommentStatus.open,
    )
    db_session.add(review)
    await db_session.flush()

    ticket = IssueTicket(
        project_id=FAKE_PROJECT_ID,
        wp_id=wp.id,
        source=IssueSource.review_comment.value,
        source_ref_id=review.id,
        severity="major",
        category="procedure_incomplete",
        title="复核退回：金额不符",
        description="金额与试算表不符，请核对",
        owner_id=FAKE_AUTHOR_ID,
        status=IssueStatus.open.value,
        trace_id="trc_test_reverse_sync",
        evidence_refs=[],
    )
    db_session.add(ticket)
    await db_session.commit()

    return {"wp": wp, "review": review, "ticket": ticket, "project_id": FAKE_PROJECT_ID}


# ---------------------------------------------------------------------------
# 情形 1 & 2 & 3：正常反向同步链路
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pending_recheck_appends_reply_text(db_session, seeded):
    """工单 → pending_recheck 时 ReviewRecord.reply_text 追加已整改。

    Validates: Requirements 2.4 (refinement-round1-review-closure)
    """
    from app.services.issue_ticket_service import issue_ticket_service

    ticket: IssueTicket = seeded["ticket"]
    review: ReviewRecord = seeded["review"]

    # open → in_fix
    await issue_ticket_service.update_status(
        db_session,
        ticket.id,
        IssueStatus.in_fix.value,
        operator_id=FAKE_AUTHOR_ID,
        reason_code="IN_FIX",
    )
    await db_session.commit()

    # in_fix → pending_recheck
    await issue_ticket_service.update_status(
        db_session,
        ticket.id,
        IssueStatus.pending_recheck.value,
        operator_id=FAKE_AUTHOR_ID,
        reason_code="FIXED",
    )
    await db_session.commit()

    refreshed = await db_session.get(ReviewRecord, review.id)
    assert refreshed is not None
    assert refreshed.reply_text == "已整改，请复验"
    assert refreshed.status == ReviewCommentStatus.replied
    assert refreshed.replier_id == FAKE_AUTHOR_ID
    assert refreshed.replied_at is not None


@pytest.mark.asyncio
async def test_closed_resolves_review_and_reverts_wp_level1(db_session, seeded):
    """工单 → closed 时 ReviewRecord.resolved + 底稿 level1_rejected→pending_level1。

    Validates: Requirements 2.5 (refinement-round1-review-closure)
    """
    from app.services.issue_ticket_service import issue_ticket_service

    ticket: IssueTicket = seeded["ticket"]
    review: ReviewRecord = seeded["review"]
    wp: WorkingPaper = seeded["wp"]

    # 推到 pending_recheck
    await issue_ticket_service.update_status(
        db_session, ticket.id, IssueStatus.in_fix.value,
        operator_id=FAKE_AUTHOR_ID, reason_code="IN_FIX",
    )
    await issue_ticket_service.update_status(
        db_session, ticket.id, IssueStatus.pending_recheck.value,
        operator_id=FAKE_AUTHOR_ID, reason_code="FIXED",
    )
    await db_session.commit()

    # pending_recheck → closed（复验通过）
    await issue_ticket_service.update_status(
        db_session, ticket.id, IssueStatus.closed.value,
        operator_id=FAKE_REVIEWER_ID, reason_code="RECHECK_PASSED",
    )
    await db_session.commit()

    # ReviewRecord 变 resolved
    refreshed_review = await db_session.get(ReviewRecord, review.id)
    assert refreshed_review.status == ReviewCommentStatus.resolved
    assert refreshed_review.resolved_by == FAKE_REVIEWER_ID
    assert refreshed_review.resolved_at is not None

    # 底稿 review_status 回退
    refreshed_wp = await db_session.get(WorkingPaper, wp.id)
    assert refreshed_wp.review_status == WpReviewStatus.pending_level1


@pytest.mark.asyncio
async def test_closed_reverts_wp_level2_rejected(db_session, seeded):
    """底稿处于 level2_rejected 时，closed 应回退到 pending_level2。

    Validates: Requirements 2.5 (refinement-round1-review-closure)
    """
    from app.services.issue_ticket_service import issue_ticket_service

    ticket: IssueTicket = seeded["ticket"]
    wp: WorkingPaper = seeded["wp"]

    # 将底稿改为 level2_rejected 以测试二级驳回场景
    wp.review_status = WpReviewStatus.level2_rejected
    await db_session.flush()
    await db_session.commit()

    await issue_ticket_service.update_status(
        db_session, ticket.id, IssueStatus.in_fix.value,
        operator_id=FAKE_AUTHOR_ID, reason_code="IN_FIX",
    )
    await issue_ticket_service.update_status(
        db_session, ticket.id, IssueStatus.pending_recheck.value,
        operator_id=FAKE_AUTHOR_ID, reason_code="FIXED",
    )
    await issue_ticket_service.update_status(
        db_session, ticket.id, IssueStatus.closed.value,
        operator_id=FAKE_REVIEWER_ID, reason_code="RECHECK_PASSED",
    )
    await db_session.commit()

    refreshed_wp = await db_session.get(WorkingPaper, wp.id)
    assert refreshed_wp.review_status == WpReviewStatus.pending_level2


# ---------------------------------------------------------------------------
# 情形 4：非 review_comment 来源工单不触碰 ReviewRecord/底稿
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_review_comment_source_does_not_touch_review_record(
    db_session, seeded
):
    """source='L2' 工单状态变更 → ReviewRecord + 底稿 review_status 保持不变。

    Validates: Requirements 2 边界（refinement-round1-review-closure）
    """
    from app.services.issue_ticket_service import issue_ticket_service

    # 新建一张来源为 L2 的独立工单（不关联 ReviewRecord）
    l2_ticket = IssueTicket(
        project_id=seeded["project_id"],
        wp_id=seeded["wp"].id,
        source=IssueSource.L2.value,
        source_ref_id=seeded["review"].id,  # 即便填了也不该触发同步（source 不匹配）
        severity="major",
        category="procedure_incomplete",
        title="L2 质控问题",
        owner_id=FAKE_AUTHOR_ID,
        status=IssueStatus.open.value,
        trace_id="trc_l2_test",
        evidence_refs=[],
    )
    db_session.add(l2_ticket)
    await db_session.commit()

    await issue_ticket_service.update_status(
        db_session, l2_ticket.id, IssueStatus.in_fix.value,
        operator_id=FAKE_AUTHOR_ID, reason_code="IN_FIX",
    )
    await issue_ticket_service.update_status(
        db_session, l2_ticket.id, IssueStatus.pending_recheck.value,
        operator_id=FAKE_AUTHOR_ID, reason_code="FIXED",
    )
    await issue_ticket_service.update_status(
        db_session, l2_ticket.id, IssueStatus.closed.value,
        operator_id=FAKE_REVIEWER_ID, reason_code="CLOSED",
    )
    await db_session.commit()

    refreshed_review = await db_session.get(ReviewRecord, seeded["review"].id)
    assert refreshed_review.status == ReviewCommentStatus.open
    assert refreshed_review.reply_text is None

    refreshed_wp = await db_session.get(WorkingPaper, seeded["wp"].id)
    assert refreshed_wp.review_status == WpReviewStatus.level1_rejected


# ---------------------------------------------------------------------------
# 情形 5：source_ref_id 指向的 ReviewRecord 不存在 → 状态仍变更，仅 warning
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_review_record_does_not_block_status_change(
    db_session, seeded, caplog
):
    """source_ref_id 指向的 ReviewRecord 不存在时，工单状态变更仍成功。

    Validates: Requirements 2 边界（refinement-round1-review-closure）
    """
    from app.services.issue_ticket_service import issue_ticket_service

    ticket: IssueTicket = seeded["ticket"]

    # 模拟 ReviewRecord 被物理删除 / source_ref_id 指向不存在的 UUID
    orphan_source_ref = uuid.uuid4()
    ticket.source_ref_id = orphan_source_ref
    await db_session.flush()
    await db_session.commit()

    with caplog.at_level("WARNING"):
        await issue_ticket_service.update_status(
            db_session, ticket.id, IssueStatus.in_fix.value,
            operator_id=FAKE_AUTHOR_ID, reason_code="IN_FIX",
        )
        await issue_ticket_service.update_status(
            db_session, ticket.id, IssueStatus.pending_recheck.value,
            operator_id=FAKE_AUTHOR_ID, reason_code="FIXED",
        )
        await db_session.commit()

    # 工单状态已变更（状态流转不受 ReviewRecord 缺失阻断）
    refreshed_ticket = await db_session.get(IssueTicket, ticket.id)
    assert refreshed_ticket.status == IssueStatus.pending_recheck.value

    # warning 日志记录了 ReviewRecord 缺失
    assert any(
        "ReviewRecord not found" in rec.message and str(orphan_source_ref) in rec.message
        for rec in caplog.records
    )


# ---------------------------------------------------------------------------
# 情形 6：底稿 review_status 非 rejected → closed 时不回退
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_closed_does_not_revert_non_rejected_review_status(db_session, seeded):
    """底稿 review_status 已是 pending_level1（非 rejected），closed 不回退。

    Validates: Requirements 2 边界（refinement-round1-review-closure）
    """
    from app.services.issue_ticket_service import issue_ticket_service

    ticket: IssueTicket = seeded["ticket"]
    wp: WorkingPaper = seeded["wp"]

    # 将底稿置为 not_submitted 以模拟编制人重新提交后的路径
    wp.review_status = WpReviewStatus.not_submitted
    await db_session.flush()
    await db_session.commit()

    await issue_ticket_service.update_status(
        db_session, ticket.id, IssueStatus.in_fix.value,
        operator_id=FAKE_AUTHOR_ID, reason_code="IN_FIX",
    )
    await issue_ticket_service.update_status(
        db_session, ticket.id, IssueStatus.pending_recheck.value,
        operator_id=FAKE_AUTHOR_ID, reason_code="FIXED",
    )
    await issue_ticket_service.update_status(
        db_session, ticket.id, IssueStatus.closed.value,
        operator_id=FAKE_REVIEWER_ID, reason_code="CLOSED",
    )
    await db_session.commit()

    refreshed_wp = await db_session.get(WorkingPaper, wp.id)
    # 没有从 rejected 回退的语义，review_status 应保持 not_submitted
    assert refreshed_wp.review_status == WpReviewStatus.not_submitted


# ---------------------------------------------------------------------------
# 情形 7：幂等 — 直接重复调用 helper 不应重复追加 reply_text
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reverse_sync_is_idempotent_on_repeated_calls(db_session, seeded):
    """重复触发 pending_recheck 反向同步 reply_text 不重复追加、resolved 不重复切。

    Validates: Requirements 2 幂等（refinement-round1-review-closure）

    注：工单状态机本身不允许 ``closed → closed``（VALID_TRANSITIONS 拦截），
    这里直接复用 helper 方法验证"状态已是终态"场景下的幂等行为。
    """
    from app.services.issue_ticket_service import issue_ticket_service

    ticket: IssueTicket = seeded["ticket"]
    review: ReviewRecord = seeded["review"]

    # 正常推进到 pending_recheck，reply_text 写入一次
    await issue_ticket_service.update_status(
        db_session, ticket.id, IssueStatus.in_fix.value,
        operator_id=FAKE_AUTHOR_ID, reason_code="IN_FIX",
    )
    await issue_ticket_service.update_status(
        db_session, ticket.id, IssueStatus.pending_recheck.value,
        operator_id=FAKE_AUTHOR_ID, reason_code="FIXED",
    )
    await db_session.commit()

    refreshed_review = await db_session.get(ReviewRecord, review.id)
    first_reply = refreshed_review.reply_text
    assert first_reply == "已整改，请复验"

    # 再次直接调用 helper（模拟"多实例写"或"手动重试"） → 不应重复追加
    await issue_ticket_service._sync_review_record_on_status_change(
        db_session,
        ticket=ticket,
        new_status=IssueStatus.pending_recheck.value,
        operator_id=FAKE_AUTHOR_ID,
    )
    await db_session.commit()

    refreshed_review2 = await db_session.get(ReviewRecord, review.id)
    assert refreshed_review2.reply_text == first_reply, "reply_text 不得重复追加"

    # closed 一次
    await issue_ticket_service.update_status(
        db_session, ticket.id, IssueStatus.closed.value,
        operator_id=FAKE_REVIEWER_ID, reason_code="RECHECK_PASSED",
    )
    await db_session.commit()

    refreshed_review3 = await db_session.get(ReviewRecord, review.id)
    first_resolved_at = refreshed_review3.resolved_at
    assert refreshed_review3.status == ReviewCommentStatus.resolved

    # 直接再次调用 helper with closed → 应幂等（resolved_at 不变更）
    await issue_ticket_service._sync_review_record_on_status_change(
        db_session,
        ticket=ticket,
        new_status=IssueStatus.closed.value,
        operator_id=FAKE_REVIEWER_ID,
    )
    await db_session.commit()

    refreshed_review4 = await db_session.get(ReviewRecord, review.id)
    assert refreshed_review4.status == ReviewCommentStatus.resolved
    assert refreshed_review4.resolved_at == first_resolved_at, (
        "已 resolved 时 resolved_at 不应被重复刷新"
    )
