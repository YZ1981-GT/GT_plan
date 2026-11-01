"""调整分录提交复核 / 撤回提交 / 批量复核与通知（spec adjustment-hall-entry-review-closure 任务 3、4）。

真请求（httpx ASGITransport）+ SQLite 内存库 + 真实鉴权链：只覆写内层 get_db / get_current_user，
``require_project_permission`` 按 ProjectUser 级别与 ProjectAssignment 角色真实判定。
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.adjustment_review_models import (
    AdjustmentClientBooking,
    AdjustmentReviewTask,
    AdjustmentTreatmentEvent,
)
from app.models.audit_platform_models import (
    AccountCategory, AccountChart, AccountDirection, AccountSource, Adjustment, AdjustmentEntry,
    AdjustmentType, Materiality, ReviewStatus, TbLedger, TrialBalance, UnadjustedMisstatement,
)
from app.models.audit_platform_schemas import AdjustmentCreate, AdjustmentLineItem
from app.models.base import Base, PermissionLevel, ProjectUserRole, UserRole
from app.models.core import Notification, Project, ProjectStatus, ProjectType, ProjectUser, User
from app.models.evidence_governance_models import AttachmentVersion, EvidenceRef
from app.models.dataset_models import (
    DatasetStatus,
    ImportEventConsumption,
    ImportEventOutbox,
    LedgerDataset,
)
from app.models.staff_models import ProjectAssignment, StaffMember
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.routers.adjustment_client_booking import router as booking_router
from app.routers.adjustment_review import router as review_router
from app.routers.adjustment_treatment import router as treatment_router
from app.routers.adjustments import router as adj_router
from app.services import notification_types as nt
from app.services.adjustment_service import AdjustmentService
from app.services.voucher_identity import VoucherKey

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
YEAR = 2025


class _World:
    def __init__(self):
        self.current: User | None = None


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    # 仅建本复核流触达的表。全量 metadata 含 PostgreSQL 专用 JSONB CHECK，
    # SQLite 无法编译；显式清单也能防测试悄悄依赖无关领域表。
    tables = [
        User.__table__,
        Project.__table__,
        ProjectUser.__table__,
        StaffMember.__table__,
        ProjectAssignment.__table__,
        AccountChart.__table__,
        Materiality.__table__,
        TrialBalance.__table__,
        WpIndex.__table__,
        WorkingPaper.__table__,
        Adjustment.__table__,
        AdjustmentEntry.__table__,
        AdjustmentReviewTask.__table__,
        AdjustmentClientBooking.__table__,
        AdjustmentTreatmentEvent.__table__,
        LedgerDataset.__table__,
        TbLedger.__table__,
        UnadjustedMisstatement.__table__,
        AttachmentVersion.__table__,
        EvidenceRef.__table__,
        ImportEventOutbox.__table__,
        ImportEventConsumption.__table__,
        Notification.__table__,
    ]
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    async with async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)() as session:
        yield session
    await eng.dispose()


async def _user(db, name: str, role: UserRole = UserRole.auditor) -> User:
    u = User(id=uuid.uuid4(), username=name, email=f"{name}@t.com", hashed_password="x", role=role)
    db.add(u)
    await db.flush()
    db.add(StaffMember(id=uuid.uuid4(), user_id=u.id, name=f"{name}姓名"))
    await db.flush()
    return u


async def _member(db, project_id, user: User, role: str, level: PermissionLevel):
    staff_id = (await db.execute(sa.select(StaffMember.id).where(StaffMember.user_id == user.id))).scalar_one()
    project_user_role = {
        "manager": ProjectUserRole.manager,
        "partner": ProjectUserRole.partner,
        "signing_partner": ProjectUserRole.partner,
    }.get(role, ProjectUserRole.auditor)
    db.add(ProjectUser(id=uuid.uuid4(), project_id=project_id, user_id=user.id,
                       role=project_user_role, permission_level=level))
    db.add(ProjectAssignment(id=uuid.uuid4(), project_id=project_id, staff_id=staff_id, role=role,
                             assigned_at=date.today()))
    await db.flush()


@pytest_asyncio.fixture
async def world(db: AsyncSession):
    w = _World()
    project = Project(id=uuid.uuid4(), name="复核流转测试_2025", client_name="复核流转测试",
                      project_type=ProjectType.annual, status=ProjectStatus.execution)
    db.add(project)
    await db.flush()
    w.pid = project.id
    for code, name in [("1122", "应收账款"), ("1231", "坏账准备"), ("6702", "信用减值损失")]:
        db.add(AccountChart(project_id=w.pid, account_code=code, account_name=name, direction=AccountDirection.debit,
                            level=1, category=AccountCategory.asset, source=AccountSource.standard))
    w.preparer = await _user(db, "preparer")
    w.reviewer = await _user(db, "reviewer")
    w.reviewer2 = await _user(db, "reviewer2")
    w.owner = await _user(db, "owner")
    await _member(db, w.pid, w.preparer, "auditor", PermissionLevel.edit)
    await _member(db, w.pid, w.reviewer, "manager", PermissionLevel.edit)
    await _member(db, w.pid, w.reviewer2, "manager", PermissionLevel.edit)
    # D2（应收账款）底稿负责人 = owner
    idx = WpIndex(project_id=w.pid, wp_code="D2", wp_name="应收账款", assigned_to=w.owner.id)
    db.add(idx)
    await db.flush()
    source_type = WorkingPaper.__table__.c["source_type"].type.enum_class("template")
    db.add(WorkingPaper(project_id=w.pid, wp_index_id=idx.id, file_path="D2.xlsx", source_type=source_type,
                        assigned_to=w.owner.id))
    await db.commit()

    app = FastAPI()
    app.include_router(adj_router)
    app.include_router(review_router)
    app.include_router(booking_router)
    app.include_router(treatment_router)

    async def _db():
        yield db

    async def _cur():
        return w.current

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _cur
    w.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://t")
    yield w
    await w.client.aclose()


async def _entry(db, w, amount="100", creator: User | None = None) -> str:
    res = await AdjustmentService(db).create_entry(w.pid, AdjustmentCreate(
        adjustment_type=AdjustmentType.aje, year=YEAR, description="补提坏账",
        line_items=[AdjustmentLineItem(standard_account_code="6702", debit_amount=Decimal(amount)),
                    AdjustmentLineItem(standard_account_code="1122", credit_amount=Decimal(amount))],
    ), (creator or w.preparer).id)
    await db.commit()
    return str(res.entry_group_id)


async def _status(db, gid) -> ReviewStatus:
    return (await db.execute(sa.select(Adjustment.review_status).where(
        Adjustment.entry_group_id == uuid.UUID(gid), Adjustment.is_deleted == sa.false()))).scalars().first()


async def _notes(db) -> list[Notification]:
    return list((await db.execute(sa.select(Notification).order_by(Notification.created_at))).scalars().all())


def _url(w, tail: str) -> str:
    return f"/api/projects/{w.pid}/adjustments{tail}"


@pytest.mark.asyncio
async def test_auditor_submits_for_review_and_reviewers_are_notified(db, world):
    w = world
    gid = await _entry(db, w)
    w.current = w.preparer
    resp = await w.client.post(_url(w, "/submit-review"), json={"entry_group_ids": [gid], "note": "请复核"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [it["entry_group_id"] for it in body["succeeded"]] == [gid] and body["failed"] == []
    assert body["succeeded"][0]["review_task_id"]
    task = (await db.execute(sa.select(AdjustmentReviewTask).where(
        AdjustmentReviewTask.entry_group_id == uuid.UUID(gid),
        AdjustmentReviewTask.status == "pending",
    ))).scalar_one()
    assert set(task.assigned_reviewer_ids) == {str(w.reviewer.id), str(w.reviewer2.id)}
    assert task.group_content_revision == 1
    w.current = w.reviewer
    mine = await w.client.get(_url(w, "/review-tasks"), params={"year": YEAR})
    assert mine.status_code == 200 and [item["entry_group_id"] for item in mine.json()] == [gid]
    w.current = w.preparer
    assert (await w.client.get(_url(w, "/review-tasks"), params={"year": YEAR})).json() == []
    assert await _status(db, gid) == ReviewStatus.pending_review
    notes = await _notes(db)
    assert {n.recipient_id for n in notes} == {w.reviewer.id, w.reviewer2.id}, "通知全部复核人，不通知提交人"
    n = notes[0]
    assert n.message_type == nt.ADJ_REVIEW_SUBMITTED and "preparer姓名" in n.title and "请复核" in n.content
    assert n.notification_metadata["object_id"] == gid and n.notification_metadata["year"] == YEAR
    assert {r["user_id"] for r in body["notified"]} == {str(w.reviewer.id), str(w.reviewer2.id)}

    # 审计员仍不能审批（/review 门禁不变）
    resp = await w.client.post(_url(w, f"/{gid}/review"), json={"status": "approved"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_submit_to_chosen_reviewer_only_and_invalid_reviewer_rejected(db, world):
    w = world
    gid = await _entry(db, w)
    w.current = w.preparer
    bad = await w.client.post(_url(w, "/submit-review"),
                              json={"entry_group_ids": [gid], "reviewer_ids": [str(w.owner.id)]})
    assert bad.status_code == 400 and bad.json()["detail"]["error_code"] == "INVALID_REVIEWER"
    assert await _status(db, gid) == ReviewStatus.draft, "复核人不合法时整体不提交"
    ok = await w.client.post(_url(w, "/submit-review"),
                             json={"entry_group_ids": [gid], "reviewer_ids": [str(w.reviewer2.id)]})
    assert ok.status_code == 200
    assert [n.recipient_id for n in await _notes(db)] == [w.reviewer2.id]


@pytest.mark.asyncio
async def test_withdraw_submission_and_review_cannot_move_pending_to_draft(db, world):
    w = world
    gid = await _entry(db, w)
    w.current = w.preparer
    await w.client.post(_url(w, "/submit-review"), json={"entry_group_ids": [gid]})
    w.current = w.reviewer
    resp = await w.client.post(_url(w, f"/{gid}/review"), json={"status": "draft"})
    assert resp.status_code == 400 and "只接受批准或驳回" in resp.text
    w.current = w.preparer
    resp = await w.client.post(_url(w, f"/{gid}/withdraw-submission"))
    assert resp.status_code == 200, resp.text
    assert await _status(db, gid) == ReviewStatus.draft
    again = await w.client.post(_url(w, f"/{gid}/withdraw-submission"))
    assert again.status_code == 400 and "只有待复核的分录可以撤回提交" in again.json()["detail"]["message"]


@pytest.mark.asyncio
async def test_batch_approve_reports_per_item_and_notifies_preparer_and_owner_once(db, world):
    w = world
    g1, g2, g3 = await _entry(db, w, "100"), await _entry(db, w, "200"), await _entry(db, w, "300")
    w.current = w.preparer
    await w.client.post(_url(w, "/submit-review"), json={"entry_group_ids": [g1, g2]})
    await db.execute(sa.delete(Notification))
    await db.commit()
    w.current = w.reviewer
    first = await w.client.post(_url(w, "/review-batch"), json={"entry_group_ids": [g3], "status": "approved"})
    assert first.status_code == 200
    assert first.json()["succeeded"] == []
    assert first.json()["failed"][0]["entry_group_id"] == g3
    assert "先提交复核" in first.json()["failed"][0]["reason"], "草稿不得绕过持久化复核任务直接批准"
    await db.execute(sa.delete(Notification))
    await db.commit()
    resp = await w.client.post(_url(w, "/review-batch"), json={"entry_group_ids": [g1, g2, g3], "status": "approved"})
    body = resp.json()
    assert resp.status_code == 200, resp.text
    assert sorted(it["entry_group_id"] for it in body["succeeded"]) == sorted([g1, g2])
    assert [f["entry_group_id"] for f in body["failed"]] == [g3] and "先提交复核" in body["failed"][0]["reason"]

    # 批准状态与 TB 调整列在路由 commit 前同一事务成立；下游事件已进入耐久 outbox。
    tb_values = {code: (aje, audited) for code, aje, audited in (await db.execute(
        sa.select(TrialBalance.standard_account_code, TrialBalance.aje_adjustment, TrialBalance.audited_amount)
        .where(TrialBalance.project_id == w.pid, TrialBalance.year == YEAR)
    )).all()}
    assert tb_values["6702"] == (Decimal("300"), Decimal("300"))
    assert tb_values["1122"] == (Decimal("-300"), Decimal("-300"))
    outbox = list((await db.execute(sa.select(ImportEventOutbox).where(
        ImportEventOutbox.project_id == w.pid,
    ))).scalars().all())
    assert len(outbox) == 4
    assert {row.event_type for row in outbox} == {"adjustment.approved", "trial_balance.updated"}
    assert all(getattr(row.status, "value", row.status) == "published" for row in outbox)

    notes = await _notes(db)
    by_user = {n.recipient_id: n for n in notes}
    assert set(by_user) == {w.preparer.id, w.owner.id} and len(notes) == 2, "每个接收人一条汇总通知"
    assert by_user[w.preparer.id].message_type == nt.ADJ_REVIEW_APPROVED and "2 笔" in by_user[w.preparer.id].title
    assert "同一复核事务计入" in by_user[w.preparer.id].content
    assert "正在更新" not in by_user[w.preparer.id].content
    impact = by_user[w.owner.id]
    assert impact.message_type == nt.ADJ_APPROVED_IMPACT and impact.notification_metadata["affected_wp_codes"] == ["D2"]
    assert "同一事务更新" in impact.content and "正在处理" not in impact.content


@pytest.mark.asyncio
async def test_batch_reject_requires_reason_and_rejected_entry_can_be_resubmitted(db, world):
    w = world
    g1, g2 = await _entry(db, w), await _entry(db, w)
    w.current = w.preparer
    submitted = await w.client.post(_url(w, "/submit-review"), json={"entry_group_ids": [g1, g2]})
    assert submitted.status_code == 200
    w.current = w.reviewer
    resp = await w.client.post(_url(w, "/review-batch"), json={
        "entry_group_ids": [g1, g2], "status": "rejected", "reasons": {g1: "金额依据不足"},
    })
    body = resp.json()
    assert [it["entry_group_id"] for it in body["succeeded"]] == [g1]
    assert body["failed"][0]["entry_group_id"] == g2 and body["failed"][0]["reason"] == "驳回必须填写原因"
    rejected = [n for n in await _notes(db) if n.message_type == nt.ADJ_REVIEW_REJECTED]
    assert len(rejected) == 1 and "金额依据不足" in rejected[0].content and rejected[0].recipient_id == w.preparer.id
    # 被驳回后不改明细直接重新提交
    w.current = w.preparer
    again = await w.client.post(_url(w, "/submit-review"), json={"entry_group_ids": [g1]})
    assert again.status_code == 200 and len(again.json()["succeeded"]) == 1
    assert await _status(db, g1) == ReviewStatus.pending_review


@pytest.mark.asyncio
async def test_revoke_notifies_preparer_with_reason_and_reviewers_endpoint_lists_candidates(db, world):
    w = world
    gid = await _entry(db, w)
    w.current = w.preparer
    await w.client.post(_url(w, "/submit-review"), json={"entry_group_ids": [gid]})
    w.current = w.reviewer
    approved = await w.client.post(_url(w, f"/{gid}/review"), json={"status": "approved"})
    assert approved.status_code == 200, approved.text
    await db.execute(sa.delete(Notification))
    await db.commit()
    resp = await w.client.post(_url(w, f"/{gid}/revoke-review"), json={"reason": "期后事项需重估"})
    assert resp.status_code == 200, resp.text
    kinds = {(n.recipient_id, n.message_type) for n in await _notes(db)}
    assert (w.preparer.id, nt.ADJ_REVIEW_REVOKED) in kinds and (w.owner.id, nt.ADJ_APPROVED_IMPACT) in kinds
    revoked = next(n for n in await _notes(db) if n.message_type == nt.ADJ_REVIEW_REVOKED)
    assert "期后事项需重估" in revoked.content

    w.current = w.preparer
    reviewers = (await w.client.get(_url(w, "/reviewers"))).json()
    assert {r["user_id"] for r in reviewers} == {str(w.reviewer.id), str(w.reviewer2.id)}, "审计员不是复核人候选"
    assert [r["name"] for r in reviewers] == sorted(r["name"] for r in reviewers)
    assert all(r["project_role"] == "manager" for r in reviewers)


@pytest.mark.asyncio
async def test_list_is_enriched_with_names(db, world):
    w = world
    gid = await _entry(db, w)
    w.current = w.preparer
    await w.client.post(_url(w, "/submit-review"), json={"entry_group_ids": [gid]})
    w.current = w.reviewer
    rejected = await w.client.post(_url(w, f"/{gid}/review"), json={"status": "rejected", "reason": "缺依据"})
    assert rejected.status_code == 200, rejected.text
    items = (await w.client.get(_url(w, ""), params={"year": YEAR})).json()["items"]
    row = next(it for it in items if it["entry_group_id"] == gid)
    assert row["creator_name"] == "preparer姓名" and row["reviewer_name"] == "reviewer姓名"
    assert row["rejection_reason"] == "缺依据" and row["has_active_collaboration"] is False


@pytest.mark.asyncio
async def test_preparer_cannot_review_own_entry_and_assigned_reviewer_can(db, world):
    """经理编制的分录也必须交给另一位复核人，不能自我复核。"""
    w = world
    gid = await _entry(db, w, creator=w.reviewer)
    w.current = w.reviewer
    submitted = await w.client.post(_url(w, "/submit-review"), json={
        "entry_group_ids": [gid], "reviewer_ids": [str(w.reviewer2.id)],
    })
    assert submitted.status_code == 200, submitted.text

    own = await w.client.post(_url(w, "/review-batch"), json={"entry_group_ids": [gid], "status": "approved"})
    assert own.status_code == 200 and own.json()["succeeded"] == []
    assert own.json()["failed"][0]["error_code"] == "NOT_ASSIGNED_REVIEWER"
    assert await _status(db, gid) == ReviewStatus.pending_review

    await db.execute(sa.delete(Notification))
    await db.commit()
    w.current = w.reviewer2
    approved_response = await w.client.post(
        _url(w, "/review-batch"), json={"entry_group_ids": [gid], "status": "approved"},
    )
    assert approved_response.status_code == 200 and len(approved_response.json()["succeeded"]) == 1
    notes = {(n.recipient_id, n.message_type) for n in await _notes(db)}
    assert (w.reviewer.id, nt.ADJ_REVIEW_APPROVED) in notes, "编制人收到另一位复核人的批准通知"
    assert (w.owner.id, nt.ADJ_APPROVED_IMPACT) in notes


@pytest.mark.asyncio
async def test_workpaper_origin_approval_notifies_preparer_but_not_wp_owner(db, world):
    """底稿来源分录批准只完成集中复核，金额须由来源底稿显式发布；因此只通知编制人，
    不提前通知其他底稿负责人刷新审定表。"""
    w = world
    gid = await _entry(db, w)
    await db.execute(sa.update(Adjustment).where(Adjustment.entry_group_id == uuid.UUID(gid))
                     .values(origin="workpaper", source_ref=f"{uuid.uuid4()}:D2-adj-1"))
    await db.commit()
    w.current = w.preparer
    submitted = await w.client.post(_url(w, "/submit-review"), json={"entry_group_ids": [gid]})
    assert submitted.status_code == 200, submitted.text
    w.current = w.reviewer
    resp = await w.client.post(_url(w, "/review-batch"), json={"entry_group_ids": [gid], "status": "approved"})
    assert resp.status_code == 200 and len(resp.json()["succeeded"]) == 1, resp.text
    kinds = {(n.recipient_id, n.message_type) for n in await _notes(db)}
    assert (w.preparer.id, nt.ADJ_REVIEW_APPROVED) in kinds, "编制人照常收到「已批准」"
    assert all(t != nt.ADJ_APPROVED_IMPACT for _, t in kinds), "底稿来源不发底稿负责人影响通知"
    approved_note = next(n for n in await _notes(db) if n.message_type == nt.ADJ_REVIEW_APPROVED)
    assert "来源底稿完成显式发布后才计入试算表" in approved_note.content
    assert (await db.execute(sa.select(sa.func.count()).select_from(ImportEventOutbox).where(
        ImportEventOutbox.project_id == w.pid,
    ))).scalar_one() == 0, "底稿来源批准本身不改 TB，也不应发正式财务事件"
    assert {r["kind"] for r in resp.json()["notified"]} == {"preparer"}


@pytest.mark.asyncio
async def test_tb_failure_rolls_back_approval_task_notifications_and_outbox(db, world, monkeypatch):
    """TB 核心写失败时，不能留下“已批准但数字没更新”的半成品。"""
    from app.services.trial_balance_service import TrialBalanceService

    w = world
    gid = await _entry(db, w)
    w.current = w.preparer
    submitted = await w.client.post(_url(w, "/submit-review"), json={
        "entry_group_ids": [gid], "reviewer_ids": [str(w.reviewer.id)],
    })
    assert submitted.status_code == 200
    await db.execute(sa.delete(Notification))
    await db.commit()

    async def fail_recalc(*_args, **_kwargs):
        raise RuntimeError("故障注入：审定数重算失败")

    monkeypatch.setattr(TrialBalanceService, "recalc_audited", fail_recalc)
    w.current = w.reviewer
    response = await w.client.post(_url(w, "/review-batch"), json={
        "entry_group_ids": [gid], "status": "approved",
    })
    assert response.status_code == 200, response.text
    assert response.json()["succeeded"] == []
    assert "审定数重算失败" in response.json()["failed"][0]["reason"]
    assert await _status(db, gid) == ReviewStatus.pending_review
    task = (await db.execute(sa.select(AdjustmentReviewTask).where(
        AdjustmentReviewTask.entry_group_id == uuid.UUID(gid),
    ))).scalar_one()
    assert task.status == "pending"
    assert await _notes(db) == []
    assert (await db.execute(sa.select(sa.func.count()).select_from(ImportEventOutbox).where(
        ImportEventOutbox.project_id == w.pid,
    ))).scalar_one() == 0


@pytest.mark.asyncio
async def test_client_booking_and_treatment_routes_enforce_scope_and_preserve_history(db, world):
    w = world
    gid = await _entry(db, w)
    w.current = w.preparer
    await w.client.post(_url(w, "/submit-review"), json={
        "entry_group_ids": [gid], "reviewer_ids": [str(w.reviewer.id)],
    })
    w.current = w.reviewer
    approved = await w.client.post(_url(w, "/review-batch"), json={
        "entry_group_ids": [gid], "status": "approved",
    })
    assert len(approved.json()["succeeded"]) == 1

    company_code = (await db.execute(sa.select(Adjustment.company_code).where(
        Adjustment.entry_group_id == uuid.UUID(gid),
    ))).scalars().first()
    dataset = LedgerDataset(
        id=uuid.uuid4(), project_id=w.pid, year=YEAR, status=DatasetStatus.active,
        source_type="import", created_by=w.preparer.id,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    db.add(dataset)
    await db.flush()
    key = VoucherKey.of(
        year=YEAR, company_code=company_code,
        voucher_date=date(YEAR, 12, 31), voucher_type="记", voucher_no="0088",
    )
    for seq, (code, debit, credit) in enumerate([
        ("6702", Decimal("100"), Decimal("0")),
        ("1122", Decimal("0"), Decimal("100")),
    ], 1):
        db.add(TbLedger(
            id=uuid.uuid4(), project_id=w.pid, year=YEAR, company_code=company_code,
            voucher_date=key.date_value, voucher_type=key.voucher_type, voucher_no=key.voucher_no,
            entry_seq=seq, account_code=code, account_name=code,
            debit_amount=debit, credit_amount=credit, summary="客户年末入账",
            dataset_id=dataset.id,
        ))
    await db.commit()

    w.current = w.owner
    forbidden = await w.client.post(_url(w, f"/{gid}/client-booking"), json={
        "year": YEAR, "voucher_keys": [key.to_str()],
    })
    assert forbidden.status_code == 403

    w.current = w.preparer
    marked = await w.client.post(_url(w, f"/{gid}/client-booking"), json={
        "year": YEAR, "voucher_keys": [key.to_str()], "note": "客户已提供凭证",
    })
    assert marked.status_code == 200, marked.text
    assert marked.json()["client_booking"]["effective"] is True
    current = await w.client.get(_url(w, f"/{gid}/treatment"), params={"year": YEAR})
    assert current.json()["status"] == "client_booked"
    history = await w.client.get(_url(w, f"/{gid}/treatment/history"), params={"year": YEAR})
    assert [item["action"] for item in history.json()][:2] == ["client_booked", "include_in_working_tb"]

    unadjusted = await w.client.post(_url(w, f"/{gid}/treatment/unadjusted"), json={
        "year": YEAR,
        "management_reason": "管理层认为金额不重大",
        "management_communication_at": "2025-12-31T10:00:00+08:00",
        "auditor_evaluation": "累计后未超过整体重要性",
    })
    assert unadjusted.status_code == 200, unadjusted.text
    assert (await w.client.get(_url(w, f"/{gid}/treatment"), params={"year": YEAR})).json()["status"] == "unadjusted_misstatement"

    w.current = w.reviewer
    missing_reason = await w.client.post(_url(w, f"/{gid}/treatment/withdraw"), json={"year": YEAR})
    assert missing_reason.status_code == 422
    withdrawn = await w.client.post(_url(w, f"/{gid}/treatment/withdraw"), json={
        "year": YEAR, "reason": "管理层同意调账",
    })
    assert withdrawn.status_code == 200, withdrawn.text
    final = await w.client.get(_url(w, f"/{gid}/treatment"), params={"year": YEAR})
    assert final.json()["status"] == "include_in_working_tb"


@pytest.mark.asyncio
async def test_material_adjustment_requires_partner_and_valid_evidence(db, world):
    w = world
    partner = await _user(db, "partner_reviewer", UserRole.partner)
    await _member(db, w.pid, partner, "partner", PermissionLevel.edit)
    db.add(Materiality(
        project_id=w.pid, year=YEAR, benchmark_type="revenue",
        benchmark_amount=Decimal("10000"), overall_percentage=Decimal("10"),
        overall_materiality=Decimal("1000"), performance_ratio=Decimal("10"),
        performance_materiality=Decimal("100"), trivial_ratio=Decimal("5"),
        trivial_threshold=Decimal("50"), calculated_by=partner.id,
    ))
    await db.commit()

    gid = await _entry(db, w, "100")
    w.current = w.preparer
    submitted = await w.client.post(_url(w, "/submit-review"), json={
        "entry_group_ids": [gid], "reviewer_ids": [str(w.reviewer.id), str(partner.id)],
    })
    assert submitted.status_code == 200, submitted.text
    task = (await db.execute(sa.select(AdjustmentReviewTask).where(
        AdjustmentReviewTask.entry_group_id == uuid.UUID(gid),
    ))).scalar_one()
    assert task.required_level == "partner"
    assert task.assigned_reviewer_ids == [str(partner.id)]

    # 即使篡改指派清单加入经理，核心协调器仍按 required_level 拒绝经理。
    task.assigned_reviewer_ids = [str(w.reviewer.id), str(partner.id)]
    await db.commit()
    w.current = w.reviewer
    manager_attempt = await w.client.post(_url(w, "/review-batch"), json={
        "entry_group_ids": [gid], "status": "approved",
    })
    assert manager_attempt.json()["failed"][0]["error_code"] == "PARTNER_APPROVAL_REQUIRED"

    w.current = partner
    no_evidence = await w.client.post(_url(w, "/review-batch"), json={
        "entry_group_ids": [gid], "status": "approved",
    })
    assert no_evidence.json()["failed"][0]["error_code"] == "ADJUSTMENT_EVIDENCE_REQUIRED"
    assert await _status(db, gid) == ReviewStatus.pending_review

    attachment_id, version_id = uuid.uuid4(), uuid.uuid4()
    db.add(AttachmentVersion(
        id=version_id, attachment_id=attachment_id, project_id=w.pid, audit_year=YEAR,
        version_no=1, storage_type="paperless", storage_key="test/evidence.pdf",
        media_type="application/pdf", byte_size=10, content_hash="a" * 64,
        availability="available", actor_type="user", actor_user_id=w.preparer.id,
    ))
    db.add(EvidenceRef(
        id=uuid.uuid4(), project_id=w.pid, audit_year=YEAR,
        source_type="adjustment", source_id=gid, source_version="1",
        evidence_type="attachment_version", evidence_id=str(version_id),
        attachment_version_id=version_id, target_version="1", target_hash="a" * 64,
        label="重大调整支持文件", intent_hash="b" * 64, status="active",
        actor_type="user", actor_user_id=w.preparer.id, created_by=w.preparer.id,
    ))
    await db.commit()
    approved = await w.client.post(_url(w, "/review-batch"), json={
        "entry_group_ids": [gid], "status": "approved",
    })
    assert len(approved.json()["succeeded"]) == 1, approved.text
    assert approved.json()["succeeded"][0]["risk"]["required_level"] == "partner"
    assert approved.json()["succeeded"][0]["evidence"][0]["label"] == "重大调整支持文件"
