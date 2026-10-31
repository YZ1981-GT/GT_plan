"""调整分录提交复核 / 撤回提交 / 批量复核与通知（spec adjustment-hall-entry-review-closure 任务 3、4）。

真请求（httpx ASGITransport）+ SQLite 内存库 + 真实鉴权链：只覆写内层 get_db / get_current_user，
``require_project_permission`` 按 ProjectUser 级别与 ProjectAssignment 角色真实判定。
"""
from __future__ import annotations

import uuid
from datetime import date
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
from app.models.audit_platform_models import (
    AccountCategory, AccountChart, AccountDirection, AccountSource, Adjustment, AdjustmentType, ReviewStatus,
)
from app.models.audit_platform_schemas import AdjustmentCreate, AdjustmentLineItem
from app.models.base import Base, PermissionLevel, ProjectUserRole, UserRole
from app.models.core import Notification, Project, ProjectStatus, ProjectType, ProjectUser, User
from app.models.staff_models import ProjectAssignment, StaffMember
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.routers.adjustment_review import router as review_router
from app.routers.adjustments import router as adj_router
from app.services import notification_types as nt
from app.services.adjustment_service import AdjustmentService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
YEAR = 2025


class _World:
    def __init__(self):
        self.current: User | None = None


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
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
    db.add(ProjectUser(id=uuid.uuid4(), project_id=project_id, user_id=user.id,
                       role=ProjectUserRole.manager if role == "manager" else ProjectUserRole.auditor,
                       permission_level=level))
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
    assert resp.status_code == 400 and "撤回提交" in resp.text
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
    assert first.status_code == 200 and len(first.json()["succeeded"]) == 1, "草稿也可直接批准（既有行为）"
    await db.execute(sa.delete(Notification))
    await db.commit()
    resp = await w.client.post(_url(w, "/review-batch"), json={"entry_group_ids": [g1, g2, g3], "status": "approved"})
    body = resp.json()
    assert resp.status_code == 200, resp.text
    assert sorted(it["entry_group_id"] for it in body["succeeded"]) == sorted([g1, g2])
    assert [f["entry_group_id"] for f in body["failed"]] == [g3] and "已批准" in body["failed"][0]["reason"]
    notes = await _notes(db)
    by_user = {n.recipient_id: n for n in notes}
    assert set(by_user) == {w.preparer.id, w.owner.id} and len(notes) == 2, "每个接收人一条汇总通知"
    assert by_user[w.preparer.id].message_type == nt.ADJ_REVIEW_APPROVED and "2 笔" in by_user[w.preparer.id].title
    impact = by_user[w.owner.id]
    assert impact.message_type == nt.ADJ_APPROVED_IMPACT and impact.notification_metadata["affected_wp_codes"] == ["D2"]


@pytest.mark.asyncio
async def test_batch_reject_requires_reason_and_rejected_entry_can_be_resubmitted(db, world):
    w = world
    g1, g2 = await _entry(db, w), await _entry(db, w)
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
    w.current = w.reviewer
    await w.client.post(_url(w, f"/{gid}/review"), json={"status": "approved"})
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
    w.current = w.reviewer
    await w.client.post(_url(w, f"/{gid}/review"), json={"status": "rejected", "reason": "缺依据"})
    items = (await w.client.get(_url(w, ""), params={"year": YEAR})).json()["items"]
    row = next(it for it in items if it["entry_group_id"] == gid)
    assert row["creator_name"] == "preparer姓名" and row["reviewer_name"] == "reviewer姓名"
    assert row["rejection_reason"] == "缺依据" and row["has_active_collaboration"] is False


@pytest.mark.asyncio
async def test_actor_who_is_also_preparer_is_not_notified_but_owner_still_is(db, world):
    """经理自己录入、自己通过 / 撤回复核：不给自己发通知；受影响底稿负责人照常收到。

    浏览器实测是 admin 自己编制自己审批（收不到通知是对的），原有用例全是「编制人 ≠ 审批人」，
    去掉「不通知操作人」过滤的变异会存活 —— 本用例补这个分支。
    """
    w = world
    gid = await _entry(db, w, creator=w.reviewer)
    w.current = w.reviewer
    await db.execute(sa.delete(Notification))
    await db.commit()
    resp = await w.client.post(_url(w, "/review-batch"), json={"entry_group_ids": [gid], "status": "approved"})
    assert resp.status_code == 200 and len(resp.json()["succeeded"]) == 1, resp.text
    approved = {(n.recipient_id, n.message_type) for n in await _notes(db)}
    assert (w.reviewer.id, nt.ADJ_REVIEW_APPROVED) not in approved, "操作人就是编制人，不给自己发「已批准」"
    assert all(rid != w.reviewer.id for rid, _ in approved), "操作人一条通知都不该收到"
    assert (w.owner.id, nt.ADJ_APPROVED_IMPACT) in approved, "受影响底稿负责人仍要通知"
    assert {r["kind"] for r in resp.json()["notified"]} == {"owner"}

    await db.execute(sa.delete(Notification))
    await db.commit()
    resp = await w.client.post(_url(w, f"/{gid}/revoke-review"), json={"reason": "重估"})
    assert resp.status_code == 200, resp.text
    revoked = {(n.recipient_id, n.message_type) for n in await _notes(db)}
    assert all(rid != w.reviewer.id for rid, _ in revoked), "撤回复核同样不通知操作人自己"
    assert (w.owner.id, nt.ADJ_APPROVED_IMPACT) in revoked


@pytest.mark.asyncio
async def test_workpaper_origin_approval_notifies_preparer_but_not_wp_owner(db, world):
    """底稿推送来的分录（origin=workpaper）批准时只通知编制人，不给受影响底稿负责人发「涉及你负责的底稿」——
    这类分录的金额已由来源底稿审定表体现，提醒负责人去刷新审定表是误导（需求 4.4「手工来源」）。"""
    w = world
    gid = await _entry(db, w)
    await db.execute(sa.update(Adjustment).where(Adjustment.entry_group_id == uuid.UUID(gid))
                     .values(origin="workpaper", source_ref=f"{uuid.uuid4()}:D2-adj-1"))
    await db.commit()
    w.current = w.reviewer
    resp = await w.client.post(_url(w, "/review-batch"), json={"entry_group_ids": [gid], "status": "approved"})
    assert resp.status_code == 200 and len(resp.json()["succeeded"]) == 1, resp.text
    kinds = {(n.recipient_id, n.message_type) for n in await _notes(db)}
    assert (w.preparer.id, nt.ADJ_REVIEW_APPROVED) in kinds, "编制人照常收到「已批准」"
    assert all(t != nt.ADJ_APPROVED_IMPACT for _, t in kinds), "底稿来源不发底稿负责人影响通知"
    assert {r["kind"] for r in resp.json()["notified"]} == {"preparer"}
