"""A2/A3 调整分录组口径防回归测试。

业务数量按 entry_group_id 计“笔”，金额仍逐明细行求和；EQCR v2 每笔
冻结完整明细、来源和复核元数据。
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_models import (
    Adjustment,
    AdjustmentEntry,
    AdjustmentType,
    MisstatementType,
    ReviewStatus,
    UnadjustedMisstatement,
)
from app.models.base import Base
from app.models.core import Project
from app.models.phase15_models import IssueTicket
from app.models.workpaper_models import WorkingPaper, WpIndex

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
_ENGINE = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    # 全量 metadata 含 PG 专用 CHECK；这里只建本组口径测试真实触达的表。
    tables = [
        Project.__table__,
        WpIndex.__table__,
        WorkingPaper.__table__,
        Adjustment.__table__,
        AdjustmentEntry.__table__,
        UnadjustedMisstatement.__table__,
        IssueTicket.__table__,
    ]
    async with _ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    factory = async_sessionmaker(_ENGINE, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


async def _seed_group(
    db: AsyncSession,
    project_id: uuid.UUID,
    created_by: uuid.UUID,
    number: str,
    status: ReviewStatus,
    *,
    origin: str = "manual",
    source_ref: str | None = None,
    reviewer_id: uuid.UUID | None = None,
    passed: bool = False,
) -> uuid.UUID:
    group_id = uuid.uuid4()
    reviewed_at = datetime.now(timezone.utc) if reviewer_id else None
    passed_at = datetime.now(timezone.utc) if passed else None
    lines = [
        ("1001", "库存现金", Decimal("100.00"), Decimal("0.00")),
        ("6001", "主营业务收入", Decimal("0.00"), Decimal("100.00")),
    ]
    for line_no, (code, name, debit, credit) in enumerate(lines, start=1):
        adjustment_id = uuid.uuid4()
        db.add(Adjustment(
            id=adjustment_id,
            project_id=project_id,
            year=2025,
            company_code="001",
            adjustment_no=number,
            adjustment_type=AdjustmentType.aje,
            description=f"测试分录 {number}",
            account_code=code,
            account_name=name,
            debit_amount=debit,
            credit_amount=credit,
            entry_group_id=group_id,
            review_status=status,
            reviewer_id=reviewer_id,
            reviewed_at=reviewed_at,
            passed_reason="管理层不更正" if passed and line_no == 2 else None,
            passed_communication_date=passed_at if passed and line_no == 2 else None,
            origin=origin,
            source_ref=source_ref,
            created_by=created_by,
        ))
        db.add(AdjustmentEntry(
            id=uuid.uuid4(),
            adjustment_id=adjustment_id,
            entry_group_id=group_id,
            line_no=line_no,
            standard_account_code=code,
            account_name=name,
            report_line_code="BS-001" if line_no == 1 else "IS-001",
            debit_amount=debit,
            credit_amount=credit,
        ))
    await db.flush()
    return group_id


@pytest_asyncio.fixture
async def grouped_adjustments(db_session: AsyncSession):
    project_id = uuid.uuid4()
    creator = uuid.uuid4()
    reviewer = uuid.uuid4()
    ids = {
        "draft": await _seed_group(
            db_session, project_id, creator, "AJE-001", ReviewStatus.draft,
        ),
        "pending": await _seed_group(
            db_session, project_id, creator, "AJE-002", ReviewStatus.pending_review,
        ),
        "approved": await _seed_group(
            db_session,
            project_id,
            creator,
            "AJE-003",
            ReviewStatus.approved,
            origin="workpaper",
            source_ref=f"{uuid.uuid4()}:row:1",
            reviewer_id=reviewer,
        ),
        "passed": await _seed_group(
            db_session,
            project_id,
            creator,
            "AJE-004",
            ReviewStatus.rejected,
            passed=True,
        ),
    }
    return project_id, ids, reviewer


@pytest.mark.asyncio
async def test_group_helpers_count_entries_but_sum_line_amounts(
    db_session: AsyncSession, grouped_adjustments,
):
    from app.services.procedure_table_auto_service import ProcedureTableService
    from app.services.wp_adjustment_helpers import (
        count_adjustments,
        count_adjustments_with_pending,
    )

    project_id, ids, _reviewer = grouped_adjustments
    assert await count_adjustments(db_session, project_id, 2025, "aje") == 4

    # 未更正错报只认正式 unadjusted_misstatements：AJE-004 只有遗留 passed_reason，
    # 不构成错报（spec adjustment-practice-linkage-integrity-closure R6.3）。
    assert await count_adjustments(db_session, project_id, 2025, "passed") == 0

    # 内部复核驳回 ≠ 管理层不更正（R6.1）：AJE-004 仍是未完成内部复核的待处理项，
    # 遗留 passed_reason 不得再把它从待处理统计里抹掉。
    assert await count_adjustments_with_pending(
        db_session, project_id, 2025, "aje",
    ) == (4, 3, 400.0)

    procedure = ProcedureTableService(db_session)
    assert await procedure._count_adjustments(project_id, 2025, "aje") == 4
    assert await procedure._count_adjustments_with_pending(
        project_id, 2025, "aje",
    ) == (4, 3, 400.0)

    # 建立正式错报后才计入「未更正错报」笔数；软删 / 已转回的不计入。
    first_row_id = (await db_session.execute(
        sa.select(Adjustment.id)
        .where(Adjustment.entry_group_id == ids["passed"])
        .order_by(Adjustment.id)
        .limit(1)
    )).scalar_one()
    db_session.add(UnadjustedMisstatement(
        id=uuid.uuid4(), project_id=project_id, year=2025,
        source_adjustment_id=first_row_id,
        misstatement_description="管理层不予更正",
        misstatement_amount=Decimal("100.00"),
        misstatement_type=MisstatementType.factual,
        management_reason="金额不重大",
    ))
    await db_session.flush()
    assert await count_adjustments(db_session, project_id, 2025, "passed") == 1


@pytest.mark.asyncio
async def test_readiness_and_review_workflow_report_group_counts(
    db_session: AsyncSession, grouped_adjustments,
):
    from app.services.deliverable_readiness_service import DeliverableReadinessService
    from app.services.review_workflow_service import ReviewWorkflowService

    project_id, _ids, _reviewer = grouped_adjustments
    blockers = []
    status = await DeliverableReadinessService()._check_adjustments(
        db_session, project_id, 2025, blockers, [],
    )
    # 待确认 = draft + pending_review + rejected 三组；遗留 passed_reason 不再让
    # 未完成内部复核的分录从出具就绪口径里消失（R6.1）。
    assert status.count == 4
    assert status.detail == {"unconfirmed_count": 3}
    assert blockers[0].evidence == {
        "component": "adjustments",
        "unconfirmed_count": 3,
        "total_count": 4,
    }
    assert "3 笔" in blockers[0].message

    review = ReviewWorkflowService(db_session)
    assert await review._resolve_auto_check(
        "adjustment_review_status", project_id, 2025,
    ) == "待复核1笔"
    assert await review._resolve_auto_check(
        "all_adjustments_approved", project_id, 2025,
    ) == "待处理3笔"
    assert await review._resolve_auto_check(
        "signoff_readiness", project_id, 2025,
    ) == "⚠️ 调整3笔待审"


@pytest.mark.asyncio
async def test_eqcr_snapshot_groups_lines_amounts_source_and_review(
    db_session: AsyncSession, grouped_adjustments,
):
    from app.services.eqcr_snapshot_service import _aggregate_adjustments, _build_metadata

    project_id, ids, reviewer = grouped_adjustments
    groups = await _aggregate_adjustments(db_session, project_id, 2025)
    assert len(groups) == 4
    assert _build_metadata([])["snapshot_version"] == 2

    approved = next(item for item in groups if item["entry_group_id"] == str(ids["approved"]))
    assert approved["id"] == approved["entry_group_id"]
    assert [line["line_no"] for line in approved["line_items"]] == [1, 2]
    assert approved["total_debit"] == 100.0
    assert approved["total_credit"] == 100.0
    assert approved["origin"] == "workpaper"
    assert approved["source_ref"]
    assert approved["review_status"] == "approved"
    assert approved["reviewer_id"] == str(reviewer)
    assert approved["reviewed_at"]

    passed = next(item for item in groups if item["entry_group_id"] == str(ids["passed"]))
    assert passed["passed_reason"] == "管理层不更正"
    assert passed["passed_communication_date"]


@pytest.mark.asyncio
async def test_role_ai_summaries_count_groups(monkeypatch, db_session, grouped_adjustments):
    from app.services import role_ai_features

    project_id, _ids, _reviewer = grouped_adjustments

    async def _no_stale(*_args, **_kwargs):
        return []

    async def _weekly_text(_data):
        return "周报"

    async def _summary_text(_data):
        return "摘要"

    monkeypatch.setattr(role_ai_features, "get_stale_workpapers", _no_stale)
    monkeypatch.setattr(role_ai_features, "_llm_polish_report", _weekly_text)
    monkeypatch.setattr(role_ai_features, "_llm_generate_summary", _summary_text)

    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    weekly = await role_ai_features.generate_weekly_report(
        db_session, project_id, week_start=week_start,
    )
    summary = await role_ai_features.generate_project_summary(db_session, project_id)
    assert weekly["raw_data"]["new_adjustments"] == 4
    assert summary["metrics"]["adjustments"] == 4
