# -*- coding: utf-8 -*-
"""已生成又被裁掉的底稿收口 —— 真实 PostgreSQL（spec procedure-trim-generation-delegation-chain 任务 19）。

全部数据建在一个外层事务里的【测试】项目上，用例结束回滚。覆盖：系统按无数据自动裁剪、新判定有数据的恢复执行并记
「系统误判更正」（驳回那条建议）；用户自己填理由裁的有数据也不动；其余粗裁原样重放 —— 覆盖范围内已生成的底稿（含程序表、
子表）两层移入回收站，范围内未终结的任务（循环快照兜底成 A 的也算）级联取消；有编制内容的未确认 409 不改；执行后对账
不变式不成立即报错；重跑计划为空；按模板集重新生成不新建已裁的。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.models.base import ProjectStatus, UserRole
from app.models.core import Project, User
from app.models.procedure_models import ProcedureInstance, ProcedureRowTask
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType, WpStatus, WpTemplateSet
from app.services import procedure_trim_cleanup as cleanup
from tests.procedure_delegation_visibility._factories import mk_row_task, mk_staff

pytestmark = pytest.mark.pg_only

AUTO = "自动裁剪：该科目在试算平衡表中无数据（科目余额 未在试算平衡表中出现），无可实施实质性程序的对象，故标记为不适用。"
MANUAL = "本期另行出具专项报告"
AVAILABILITY = {
    "subject_with_data": ["H3", "Q9"], "subject_no_data": ["M4"], "subject_unknown": [],
    "evidence": {"H3": {"label": "投资性房地产", "closing": 7689744.44, "opening": 7000000.0, "debit": 0, "credit": 0}},
}
TRIMMED_PAPERS = ["M4", "M4-1", "M4A", "Q9"]


@pytest_asyncio.fixture
async def db(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # 模板集生成按相对路径建项目底稿目录
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    conn = await engine.connect()
    trans = await conn.begin()
    s = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        yield s
    finally:
        await s.close()
        await trans.rollback()
        await conn.close()
        await engine.dispose()


async def _seed(db):
    admin = User(username=f"tc_{uuid.uuid4().hex[:10]}", email=f"{uuid.uuid4().hex[:10]}@t.example",
                 hashed_password="x", role=UserRole.admin, is_active=True)
    project = Project(name="【测试】裁剪收口", client_name="【测试】裁剪收口", status=ProjectStatus.execution,
                      template_type="soe", report_scope="standalone", audit_year=2025, scenario="normal")
    db.add_all([admin, project])
    await db.flush()
    pid = project.id
    for cycle, code, status, reason, state in (
        ("H", "H3", "not_applicable", AUTO, {"reason_code": "no_data"}),
        ("M", "M4", "not_applicable", AUTO, {"reason_code": "no_data"}),
        ("Q", "Q9", "skip", MANUAL, None),
        ("D", "D2", "execute", None, None),
    ):
        db.add(ProcedureInstance(project_id=pid, audit_cycle=cycle, procedure_code=code, procedure_name=code,
                                 status=status, skip_reason=reason, suggestion_state=state, wp_code=code))
    idx: dict[str, WpIndex] = {}
    for code in ("H3", "H3-1", "M4", "M4A", "M4-1", "Q9", "D2"):
        wi = WpIndex(project_id=pid, wp_code=code, wp_name=f"底稿{code}", audit_cycle=code[0],
                     status=WpStatus.not_started)
        db.add(wi)
        await db.flush()
        db.add(WorkingPaper(project_id=pid, wp_index_id=wi.id, file_path="", file_version=1,
                            source_type=WpSourceType.template))
        idx[code] = wi
    await db.flush()
    staff = await mk_staff(db)
    cascade = await mk_row_task(db, pid, idx["M4-1"].id, sheet_key="M4-1A", wp_code="M4-1", audit_cycle="A",
                                assignee_staff_id=staff.id)  # 物化时循环快照兜底成 A
    cascade.workflow_status = "assigned"
    keep = await mk_row_task(db, pid, idx["H3"].id, sheet_key="H3A", wp_code="H3", audit_cycle="H")
    await db.flush()
    return admin, pid, cascade, keep


async def _instances(db, pid) -> dict[str, tuple]:
    rows = (await db.execute(sa.select(ProcedureInstance.wp_code, ProcedureInstance.status,
                                       ProcedureInstance.skip_reason, ProcedureInstance.suggestion_state)
                             .where(ProcedureInstance.project_id == pid))).all()
    return {r[0]: (r[1], r[2], r[3]) for r in rows}


async def _papers(db, pid) -> dict[str, tuple[bool, bool]]:
    rows = (await db.execute(sa.select(WpIndex.wp_code, WpIndex.is_deleted, WorkingPaper.is_deleted)
                             .join(WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id)
                             .where(WpIndex.project_id == pid))).all()
    return {r[0]: (bool(r[1]), bool(r[2])) for r in rows}


async def _task(db, task_id) -> tuple[str, str]:
    row = (await db.execute(sa.select(ProcedureRowTask.workflow_status, ProcedureRowTask.applicability_status)
                            .where(ProcedureRowTask.id == task_id))).one()
    return row[0], row[1]


@pytest.mark.asyncio
async def test_cleanup_restores_misjudged_recycles_the_rest_and_is_idempotent(db):
    admin, pid, cascade, keep = await _seed(db)
    before = await cleanup.reconcile(db, pid)
    assert before["live_trimmed"] == ["H3", "H3-1", "M4", "M4-1", "M4A", "Q9"] and before["wp_index_in_recycle"] == 0

    plan = await cleanup.plan_cleanup(db, pid, actor_user_id=admin.id, restore_misjudged=True,
                                      availability=AVAILABILITY)
    assert [m["code"] for m in plan.misjudged] == ["H3"]
    assert plan.misjudged[0]["correction"].startswith("系统误判更正：投资性房地产有数据（期末 7,689,744.44，期初 7,000,000.00")
    assert [k["code"] for k in plan.kept] == ["M4", "Q9"]
    assert [d["code"] for d in plan.data_but_manual] == ["Q9"], "用户自己填理由裁的，有数据也不自动恢复"
    assert sorted(plan.recycle_preview["to_recycle"]) == TRIMMED_PAPERS, "程序表 M4A、子表 M4-1 跟随 M4"
    assert plan.recycle_preview["substantive"] == []
    assert [t["task_id"] for t in plan.cascade_tasks] == [str(cascade.id)], "循环快照兜底成 A 的任务按底稿归属也算"
    snap = await cleanup.snapshot(db, plan)
    assert sorted(x["wp_code"] for x in snap["wp_index"]) == TRIMMED_PAPERS
    assert {x["wp_code"] for x in snap["procedure_instances"]} == {"H3", "M4", "Q9"} and len(snap["working_paper"]) == 4

    out = await cleanup.apply_cleanup(db, plan, actor_user_id=admin.id, request_id="tc-1")
    assert out["recycled_codes"] == TRIMMED_PAPERS and out["corrected"] == ["H3"]
    assert out["after"]["live_trimmed"] == [] and out["after"]["open_tasks_under_recycled"] == 0
    inst = await _instances(db, pid)
    assert inst["H3"][:2] == ("execute", None)
    assert inst["H3"][2]["rejected"] is True and inst["H3"][2]["rejected_reason"] == plan.misjudged[0]["correction"]
    assert inst["H3"][2]["reason_code"] == "no_data", "驳回保留原建议理由码作留痕"
    assert inst["M4"] == ("not_applicable", AUTO, {"reason_code": "no_data"}), "原样重放不改状态、理由"
    assert inst["Q9"] == ("skip", MANUAL, None)
    assert await _papers(db, pid) == {
        "H3": (False, False), "H3-1": (False, False), "D2": (False, False),
        **{c: (True, True) for c in TRIMMED_PAPERS},
    }
    assert await _task(db, cascade.id) == ("cancelled", "not_applicable")
    assert await _task(db, keep.id) == ("unassigned", "execute")

    again = await cleanup.plan_cleanup(db, pid, actor_user_id=admin.id, restore_misjudged=True,
                                       availability=AVAILABILITY)
    assert again.is_empty and again.misjudged == [] and again.cascade_tasks == [], "可重跑：第二次 0 动作"

    ts = WpTemplateSet(set_name=f"【测试】裁剪收口{uuid.uuid4().hex[:8]}",
                       template_codes=["D2", "H3", "H3-1", "M4", "M4A", "M4-1", "Q9"])
    db.add(ts)
    await db.flush()
    assert (await cleanup.pick_template_set(db, pid)).id == ts.id
    regen = await cleanup.regenerate(db, pid, template_set_id=ts.id, year=2025, actor_user_id=admin.id)
    assert regen["created"] == [] and sorted(regen["skipped_trimmed_codes"]) == TRIMMED_PAPERS
    rec = await cleanup.reconcile(db, pid, template_codes=ts.template_codes)
    assert (rec["live_trimmed"], rec["open_tasks_under_recycled"], rec["generation"]["would_create"]) == ([], 0, [])
    assert (rec["wp_index_live"], rec["in_recycle_by_kind"]) == (3, {"trim": 4})


@pytest.mark.asyncio
async def test_substantive_workpaper_needs_confirmation_and_broken_invariant_rolls_back(db, monkeypatch):
    admin, pid, _cascade, _keep = await _seed(db)
    m41 = (await db.execute(sa.select(WorkingPaper).join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id).where(
        WpIndex.project_id == pid, WpIndex.wp_code == "M4-1"))).scalar_one()
    m41.content_revision = 2
    await db.flush()
    plan = await cleanup.plan_cleanup(db, pid, actor_user_id=admin.id, restore_misjudged=True,
                                      availability=AVAILABILITY)
    assert [t["wp_code"] for t in plan.recycle_preview["substantive"]] == ["M4-1"]

    with pytest.raises(HTTPException) as ei:
        async with db.begin_nested():
            await cleanup.apply_cleanup(db, plan, actor_user_id=admin.id, request_id="tc-2")
    assert ei.value.status_code == 409 and ei.value.detail["error"] == "substantive_recycle_unconfirmed"
    assert (await _instances(db, pid))["H3"][0] == "not_applicable" and (await _papers(db, pid))["M4-1"] == (False, False)

    real = cleanup.reconcile

    async def _broken(session, project_id, **kw):
        out = await real(session, project_id, **kw)
        return {**out, "open_tasks_under_recycled": 1}

    monkeypatch.setattr(cleanup, "reconcile", _broken)
    with pytest.raises(cleanup.CleanupError, match="对账不变式不成立"):
        async with db.begin_nested():
            await cleanup.apply_cleanup(db, plan, actor_user_id=admin.id, request_id="tc-3", confirm_substantive=True)
    monkeypatch.setattr(cleanup, "reconcile", real)

    out = await cleanup.apply_cleanup(db, plan, actor_user_id=admin.id, request_id="tc-4", confirm_substantive=True)
    assert "M4-1" in out["recycled_codes"] and (await _papers(db, pid))["M4-1"] == (True, True)
