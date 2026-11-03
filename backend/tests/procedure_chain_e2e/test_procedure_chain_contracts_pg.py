"""程序链真实接口的契约校验（spec procedure-chain-hardening-and-java-contracts R22 / R23）—— 真实 PostgreSQL。

与 tests/contracts/test_procedure_chain_contracts.py（不连库：schema 自检、共享用例、服务层产物）互补：这里走真实应用
（全部中间件、注册表、底稿门），把各接口响应的 data 与错误详情按 docs/contracts/procedure-chain 的 schema 校验，
请求体也按契约里的请求定义校验；并校验同一事务里落库的行（生命周期事件、程序行定义与任务、任务历史、outbox 载荷）
—— Java 版读写的是同一批表。每例一个外层事务，结束整体回滚；底稿文件生成到临时目录。

每处校验旁边都断言「确实有内容」（新建了几份、委派了几行、拒绝原因是什么），免得空列表让 schema 校验空转。
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from app.models.phase15_models import TaskEvent
from app.models.procedure_models import ProcedureRowDefinition, ProcedureRowTask, ProcedureRowTaskHistory
from app.models.workpaper_models import WpTemplateSet
from app.services.procedure_row_trim_service import normalize_program_no
from tests.contracts._contract_schemas import assert_valid, mapping_row, orm_row
from tests.procedure_chain_e2e import _chain_world as cw

pytestmark = [pytest.mark.pg_only, pytest.mark.asyncio]

GEN = "generation-receipt"
TRIM = "trimmed-scope"
PREVIEW = "delegation-preview"
APPLY = "delegation-apply"
IDENTITY = "program-row-identity"
PATCH = "program-row-patch"
TASK_EVENT = "procedure-task-event"


def _delegation(wp_index_id, staff_id, **extra) -> dict:
    return {"selector": {"kind": "workpaper", "wp_index_ids": [str(wp_index_id)]},
            "assignee_staff_id": str(staff_id), **extra}


async def _preview(c, pid, body: dict) -> dict:
    assert_valid(PREVIEW, body, "/$defs/request")
    r = await c.post(f"/api/projects/{pid}/procedure-delegations/preview", json=body)
    assert r.status_code == 200, r.text
    preview = cw.data(r)
    assert_valid(PREVIEW, preview)
    return preview


async def _apply(c, pid, body: dict, preview: dict, **extra):
    req = {**body, "preview_id": preview["preview_id"], "request_id": f"r23-{uuid.uuid4().hex[:8]}", **extra}
    assert_valid(APPLY, req, "/$defs/request")
    return await c.post(f"/api/projects/{pid}/procedure-delegations/apply", json=req)


async def test_generation_and_trim_responses_match_contracts(db):
    s = db
    await cw.ensure_lifecycle_table(s)
    w = await cw.world(s)
    pid = w.pid
    template_set = WpTemplateSet(set_name=f"【测试】程序链契约_{uuid.uuid4().hex[:6]}", template_codes=["D1", "D2", "H3"])
    s.add(template_set)
    await s.flush()
    request = {"wp_codes": ["D1", "H3"], "year": cw.YEAR}
    assert_valid(GEN, request, "/$defs/generateFromCodesRequest")
    entry = cw.h3_entry("not_applicable", "本期无投资性房地产")
    assert_valid(TRIM, {"entries": [entry]}, "/$defs/previewRequest")
    by_set = {"template_set_id": str(template_set.id), "year": cw.YEAR, "selected_templates": ["D1", "D2", "H3", "ZZ9"]}
    assert_valid(GEN, by_set, "/$defs/templateSetGenerateRequest")
    async with cw.client(s, w.manager) as c:
        raw = await c.post(f"/api/projects/{pid}/working-papers/generate-from-codes", json=request)
        preview, applied, request_id = await cw.trim(c, pid, entry)
        again = await cw.generate(c, pid, ["D1", "H3", "H3-1"])
        r = await c.post(f"/api/projects/{pid}/working-papers/generate", json=by_set)
        assert r.status_code == 200, r.text
        from_set = cw.data(r)
        invalid = await c.post(f"/api/projects/{pid}/working-papers/generate-from-codes",
                               json={**request, "dry_run": True})

    # 信封：成功 {code, message, data}；422 是 {code, message, detail}（不是 FastAPI 默认的 {detail}）
    assert raw.status_code == 200, raw.text
    assert_valid("common", raw.json(), "/$defs/responseEnvelope")
    assert (raw.json()["code"], raw.json()["message"]) == (200, "success")
    first = cw.data(raw)
    assert invalid.status_code == 422, invalid.text
    assert_valid("common", invalid.json(), "/$defs/validationErrorBody")
    assert invalid.json()["detail"][0]["loc"][-1] == "dry_run", invalid.json()

    assert_valid(GEN, first, "/$defs/generateFromCodesResponse")
    assert (first["created"], first["created_codes"]) == (2, ["D1", "H3"]), first

    assert_valid(TRIM, preview, "/$defs/previewResponse")
    assert preview["recycle_preview"]["to_recycle"] == ["H3"], preview["recycle_preview"]
    assert_valid(TRIM, {"entries": [entry], "preview_id": preview["preview_id"], "request_id": request_id},
                 "/$defs/applyRequest")
    assert_valid(TRIM, applied, "/$defs/applyResponse")
    assert (applied["applied"], applied["recycled_codes"]) == (1, ["H3"]) and applied["per_entry"], applied

    assert_valid(GEN, again, "/$defs/generateFromCodesResponse")
    assert (again["existing_codes"], again["skipped_trimmed_codes"]) == (["D1"], ["H3", "H3-1"]), again
    assert (again["skipped"], again["skipped_codes"]) == (1, ["D1"]), "原有字段：skipped = 已存在数"

    assert_valid(GEN, from_set, "/$defs/templateSetGenerateResponse")
    assert (from_set["created_codes"], from_set["existing_codes"]) == (["D2"], ["D1"]), from_set
    assert (from_set["skipped_trimmed_codes"], from_set["ignored_codes"]) == (["H3"], ["ZZ9"]), from_set
    assert from_set["count"] == from_set["created"] == 1, "原有字段：count = 新建份数"

    rows = (await s.execute(sa.text("SELECT * FROM workpaper_lifecycle_events WHERE project_id = :p"),
                            {"p": pid})).all()
    events = [mapping_row(r) for r in rows]
    assert [(e["wp_code"], e["event_type"], e["kind"], e["trim_codes"]) for e in events] == [
        ("H3", "recycled", "trim", ["H3"])], events
    for event in events:
        assert_valid("workpaper-lifecycle-event", event)


async def test_delegation_row_access_patch_and_rejections_match_contracts(db):
    s = db
    await cw.ensure_lifecycle_table(s)
    w = await cw.world(s)
    pid = w.pid
    async with cw.client(s, w.manager) as c:
        await cw.generate(c, pid, ["D1", "D2", "E1"])
    index = await cw.index_rows(s, pid)
    wp = {code: r.id for code, r in (await cw.papers(s, pid)).items()}

    # 1. 默认原子：经理把 D2 委派给审计员（D 循环）
    d2 = _delegation(index["D2"].id, w.a_staff.id)
    async with cw.client(s, w.manager) as c:
        preview = await _preview(c, pid, d2)
        r = await _apply(c, pid, d2, preview)
    assert r.status_code == 200, r.text
    applied = cw.data(r)
    assert_valid(APPLY, applied)
    assert preview["preparation_ready"] is True and preview["materialization"]["ready"] is True, preview
    assert preview["summary"]["would_assign"] > 0 and preview["scope_gaps"] == [], preview["summary"]
    assert (applied["applied"], applied["best_effort"], applied["per_task"]) == (
        preview["summary"]["would_assign"], False, None), applied

    # 2. 落库的行：任务定位、程序行定义、任务历史、outbox 载荷
    tasks = (await s.execute(sa.select(ProcedureRowTask).where(
        ProcedureRowTask.project_id == pid, ProcedureRowTask.wp_index_id == index["D2"].id,
        ProcedureRowTask.is_deleted == sa.false()))).scalars().all()
    mine = [t for t in tasks if t.assignee_staff_id == w.a_staff.id]
    mine_ids = sorted(str(t.id) for t in mine)  # 第 5 步的 409 会回滚保存点、让 ORM 对象过期 ⇒ 先取值
    assert len(mine) == applied["applied"]
    for task in tasks:
        assert_valid(IDENTITY, orm_row(task), "/$defs/taskIdentity")
    keys = {t.definition_key for t in tasks}
    definitions = (await s.execute(sa.select(ProcedureRowDefinition).where(
        ProcedureRowDefinition.definition_key.in_(keys)))).scalars().all()
    assert {d.definition_key for d in definitions} == keys
    for definition in definitions:
        row = orm_row(definition)
        assert_valid(IDENTITY, row, "/$defs/definition")
        # 身份四元组里的程序号是摘要输入：定义行存 null 的空程序号按空串参与摘要
        assert_valid(IDENTITY, {"definition_key": row["definition_key"], "template_code": row["template_code"],
                                "sheet_key": row["sheet_key"], "program_no": row["program_no"] or ""})
    history = (await s.execute(sa.select(ProcedureRowTaskHistory).where(
        ProcedureRowTaskHistory.project_id == pid))).scalars().all()
    assert {h.task_id for h in history if h.event_type == "assigned"} == {t.id for t in mine}
    for h in history:
        assert_valid(TASK_EVENT, orm_row(h), "/$defs/historyRow")
    outbox = (await s.execute(sa.select(TaskEvent).where(
        TaskEvent.project_id == pid, TaskEvent.aggregate_type == "procedure_row_task"))).scalars().all()
    assert {e.aggregate_id for e in outbox if e.event_type == "procedure_task.assigned"} == {t.id for t in mine}
    for event in outbox:
        assert_valid(TASK_EVENT, event.payload)

    # 3. 审计员看自己能改哪些行；批量写覆盖值：本人行的执行说明写上，「不适用」与别人的行逐条拒绝
    [sheet_key] = {t.sheet_key for t in mine}
    expected_own = {normalize_program_no(t.program_no) for t in mine if t.program_no}
    async with cw.client(s, w.auditor) as c:
        r = await c.get(f"/api/workpapers/{wp['D2']}/program-row-access", params={"sheet_name": sheet_key})
        assert r.status_code == 200, r.text
        access = cw.data(r)
        assert_valid(IDENTITY, access, "/$defs/rowAccess")
        assert (access["full_power"], access["can_trim"], access["template_code"]) == (False, False, sheet_key), access
        own = access["own_program_nos"]
        assert own and set(own) == expected_own, (own, expected_own)
        scope = f"procedure_table:{sheet_key}"
        items = [
            {"scope": scope, "item_key": own[0], "field": "execution_summary", "value": "已执行函证程序"},
            {"scope": scope, "item_key": own[0], "field": "status", "value": "not_applicable"},
            {"scope": scope, "item_key": "9999", "field": "execution_summary", "value": "不是我的行"},
        ]
        body = {"project_id": str(pid), "year": cw.YEAR, "items": items}
        assert_valid(PATCH, body, "/$defs/request")
        r = await c.post("/api/workpapers/field-overrides/batch", json=body)
    assert r.status_code == 200, r.text
    patch = cw.data(r)
    assert_valid(PATCH, patch)
    assert [(x["item_key"], x["field"]) for x in patch["saved"]] == [(own[0], "execution_summary")], patch
    assert [(x["item_key"], x["field"], x["status"]) for x in patch["failed"]] == [
        (own[0], "status", 403), ("9999", "execution_summary", 403)], patch

    # 4. best_effort：逐任务结果
    d1 = _delegation(index["D1"].id, w.a_staff.id, best_effort=True)
    async with cw.client(s, w.manager) as c:
        preview = await _preview(c, pid, d1)
        r = await _apply(c, pid, d1, preview)
    assert r.status_code == 200, r.text
    effort = cw.data(r)
    assert_valid(APPLY, effort)
    assert effort["best_effort"] is True and effort["per_task"], effort
    assert {(p["action"], p["status"]) for p in effort["per_task"]} == {("assign", "applied")}, effort["per_task"]

    # 5. 默认原子遇冲突：D2 已派给审计员，再派给经理 ⇒ 409 delegation_conflict
    to_manager = _delegation(index["D2"].id, w.m_staff.id)
    async with cw.client(s, w.manager) as c:
        preview = await _preview(c, pid, to_manager)
        r = await _apply(c, pid, to_manager, preview)
    assert preview["summary"]["conflict"] == len(mine_ids) and preview["conflict_task_ids"], preview["summary"]
    assert r.status_code == 409, r.text
    conflict = cw.wire_detail(r)
    assert_valid(APPLY, conflict, "/$defs/conflictError")
    assert sorted(conflict["conflict_task_ids"]) == mine_ids, conflict

    # 6. 跨循环：E1 派给只有 D 循环的审计员 ⇒ 预览列出缺口；不带理由应用 400 out_of_scope（凭证不消费），
    #    同一凭证带理由重试 ⇒ 扩大范围并应用
    e1 = _delegation(index["E1"].id, w.a_staff.id)
    async with cw.client(s, w.manager) as c:
        preview = await _preview(c, pid, e1)
        rejected = await _apply(c, pid, e1, preview)
        retried = await _apply(c, pid, e1, preview, expand_scope=True, scope_reason="E 循环人手不足，临时协助")
    assert preview["summary"]["would_assign"] > 0, preview["summary"]
    assert [(g["role"], g["staff_id"], g["cycles"], g["is_member"]) for g in preview["scope_gaps"]] == [
        ("assignee", str(w.a_staff.id), ["E"], True)], preview["scope_gaps"]
    assert rejected.status_code == 400, rejected.text
    assert_valid("common", rejected.json(), "/$defs/responseEnvelope")
    assert sorted(rejected.json()) == ["code", "message"], "错误体是 {code, message}，message 即错误详情"
    rejection = rejected.json()["message"]
    assert_valid(APPLY, rejection, "/$defs/rejection")
    assert (rejection["error"], rejection["reason"], rejection["cycles"]) == (
        "row_delegation_rejected", "out_of_scope", ["E"]), rejection
    assert retried.status_code == 200, retried.text
    expanded = cw.data(retried)
    assert_valid(APPLY, expanded)
    assert expanded["scope_expanded"] == [{"role": "assignee", "staff_id": str(w.a_staff.id), "cycles": ["E"]}], expanded
    assert expanded["applied"] == preview["summary"]["would_assign"], expanded
