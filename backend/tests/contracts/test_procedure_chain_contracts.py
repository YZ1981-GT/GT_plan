"""程序链契约测试（spec procedure-chain-hardening-and-java-contracts R22 / R23）—— 不连 PostgreSQL。

docs/contracts/procedure-chain/ 下的 schema 与 cases/ 共享用例是 Python 与 Java 两边共同的口径：
1. schema 自检：发布集合固定、每个都是合法的 2020-12 schema、``$id`` 带版本且与文件名一致、``$ref`` 全部可解析、不写 ``$schema``；
2. 共享用例逐条跑 Python 参考实现：粗裁判定、生成分流、程序行身份、成员有效范围、任务状态机、存量文件分类；
3. 服务层真实产物按 schema 校验：生成回执、生命周期事件与旧去向记录、任务 outbox 与历史、存量分类与报告汇总。

真实路由的响应（粗裁 / 生成 / 委派预览与应用 / 程序行归属 / 覆盖值批量 / 委派拒绝体）在
tests/procedure_chain_e2e/test_procedure_chain_contracts_pg.py（真库回滚事务）。
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from jsonschema import Draft202012Validator
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

import app.models  # noqa: E402, F401
from app.models.base import Base, PermissionLevel, ProjectStatus, ProjectUserRole, UserRole  # noqa: E402
from app.models.core import Project, ProjectUser, User  # noqa: E402
from app.models.phase15_models import TaskEvent  # noqa: E402
from app.models.procedure_models import (  # noqa: E402
    ProcedureInstance,
    ProcedureRowDefinition,
    ProcedureRowTask,
    ProcedureRowTaskHistory,
)
from app.models.staff_models import ProjectAssignment, StaffMember  # noqa: E402
from app.models.workpaper_lifecycle_models import WorkpaperLifecycleEvent  # noqa: E402
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType, WpStatus  # noqa: E402
from tests.contracts._contract_schemas import (  # noqa: E402
    BASE_ID,
    CASES,
    CONTRACTS,
    assert_valid,
    errors_of,
    iter_refs,
    load_cases,
    load_schema,
    orm_row,
    registry,
)

PUBLISHED = {
    "common", "trimmed-scope", "generation-plan", "generation-plan-view", "generation-receipt", "workpaper-lifecycle-event",
    "program-row-identity", "delegation-preview", "delegation-apply", "member-scope", "program-row-patch",
    "workpaper-file-materialization", "procedure-task-event",
}
CASE_FILES = {
    "trimmed-scope", "generation-plan", "program-row-identity", "member-scope", "task-state-machine",
    "workpaper-file-materialization",
}


async def _sqlite():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _project(name: str = "【测试】程序链契约") -> Project:
    return Project(id=uuid.uuid4(), name=name, client_name=name, status=ProjectStatus.execution, audit_year=2025)


# ─── 1. schema 自检 ─────────────────────────────────────────────────────────


def test_published_schema_and_case_sets_are_fixed():
    assert {p.name.removesuffix(".schema.json") for p in CONTRACTS.glob("*.schema.json")} == PUBLISHED
    assert {p.name.removesuffix(".cases.json") for p in CASES.glob("*.cases.json")} == CASE_FILES
    for name in CASE_FILES:
        assert load_cases(name)["contract"].removesuffix(".schema.json") in PUBLISHED, name


@pytest.mark.parametrize("name", sorted(PUBLISHED))
def test_schema_is_valid_2020_12_self_identified_and_refs_resolve(name):
    schema = load_schema(name)
    assert "$schema" not in schema, "不写 $schema：IDE 会去下载远程元模式；方言由校验器固定为 2020-12"
    assert schema["$id"] == f"{BASE_ID}{name}.schema.json"
    assert schema.get("title"), "每个契约要有标题"
    Draft202012Validator.check_schema(schema)
    resolver = registry().resolver(base_uri=schema["$id"])
    refs = list(iter_refs(schema))
    for ref in refs:
        resolver.lookup(ref)  # 解析不到即抛
    if name != "common":
        assert any(r.startswith("common.schema.json#") for r in refs), "公共类型统一从 common 引用"


# ─── 2. 共享用例 ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("group", load_cases("trimmed-scope")["groups"], ids=lambda g: g["name"])
def test_trimmed_scope_cases(group):
    from app.services.procedure_scope_retention import TrimmedScope

    scope = TrimmedScope.from_rows(tuple(r) for r in group["rows"])
    payload = scope.to_payload()
    assert payload == group["payload"]
    assert_valid("trimmed-scope", payload)
    for expected in group["decisions"]:
        got = scope.decide(expected["wp_code"])
        assert got == expected, expected["wp_code"]
        assert_valid("trimmed-scope", got, "/$defs/decision")


@pytest.mark.parametrize("case", load_cases("generation-plan")["cases"], ids=lambda c: c["name"])
async def test_generation_plan_cases(case):
    from app.services.procedure_scope_retention import plan_generation

    engine, factory = await _sqlite()
    try:
        async with factory() as s:
            project = _project()
            s.add(project)
            await s.flush()
            for code, status in case["scope_rows"]:
                s.add(ProcedureInstance(project_id=project.id, audit_cycle=code[0], procedure_code=code,
                                        procedure_name=code, status=status, wp_code=code))
            for code, deleted in case["index"].items():
                s.add(WpIndex(project_id=project.id, wp_code=code, wp_name=code, audit_cycle=code[0],
                              status=WpStatus.not_started, is_deleted=deleted))
            await s.flush()
            payload = (await plan_generation(s, project.id, case["codes"])).to_payload()
    finally:
        await engine.dispose()
    assert payload == case["expected"]
    assert_valid("generation-plan", payload)
    flat = [c for lst in payload.values() for c in lst]
    assert sorted(flat) == sorted(case["codes"]), "四类两两不相交、并集等于输入"


def test_program_row_identity_cases():
    from app.services.procedure_definition_importer import (
        _RawRow,
        _build_ref_snapshot,
        _normalize_program_no,
        compute_definition_key,
        normalize_text,
    )
    from app.services.procedure_row_trim_service import normalize_program_no

    cases = load_cases("program-row-identity")
    for item in cases["definition_keys"]:
        raw = _RawRow(program_no=item["program_no"], procedure_text=item["procedure_text"],
                      ref_snapshot=list(item["ref_snapshot"]), array_index=0)
        key = compute_definition_key(item["template_code"], item["sheet_key"], raw)
        assert key == item["definition_key"], item
        identity = {k: item[k] for k in ("template_code", "sheet_key", "program_no")} | {"definition_key": key}
        assert_valid("program-row-identity", identity)
    for raw_text, expected in cases["normalize_text"]:
        assert normalize_text(raw_text) == expected, raw_text
    for item in cases["ref_snapshot"]:
        assert _build_ref_snapshot(item["ref_index"], item["auto_data_source"]) == item["expected"], item
    for value, expected in cases["task_program_no"]:
        assert normalize_program_no(value) == expected, value
    for value, expected in cases["definition_program_no"]:
        assert _normalize_program_no(value) == expected, value


def test_member_scope_constants_match_cases():
    from app.services.wp_visibility.effective_scope import STANDARD_CYCLES, SUPERVISOR_ROLES

    cases = load_cases("member-scope")
    assert sorted(SUPERVISOR_ROLES) == cases["supervisor_roles"]
    assert sorted(STANDARD_CYCLES) == cases["standard_cycles"]


@pytest.mark.parametrize("case", load_cases("member-scope")["cases"], ids=lambda c: c["name"])
async def test_member_scope_cases(case):
    from app.services.wp_visibility.effective_scope import resolve_member_scope

    inp = case["input"]
    engine, factory = await _sqlite()
    try:
        async with factory() as s:
            project = _project()
            user = User(id=uuid.uuid4(), username=f"ms_{uuid.uuid4().hex[:8]}", email=f"{uuid.uuid4().hex[:8]}@t.example",
                        hashed_password="x", role=UserRole(inp["system_role"]), is_active=True)
            s.add_all([project, user])
            await s.flush()
            if inp.get("is_creator"):
                project.created_by = user.id
            staff = [StaffMember(name=f"【测试】人员{i}", user_id=user.id) for i in range(inp["staff_count"])]
            s.add_all(staff)
            await s.flush()
            for a in inp["assignments"]:
                pa = ProjectAssignment(project_id=project.id, staff_id=staff[0].id, role=a["role"])
                pa.assigned_cycles = a["assigned_cycles"]
                pa.is_deleted = bool(a.get("deleted"))
                s.add(pa)
            for scope_cycles in inp["member_rows"]:
                s.add(ProjectUser(project_id=project.id, user_id=user.id, role=ProjectUserRole.auditor,
                                  permission_level=PermissionLevel.edit, scope_cycles=scope_cycles))
            for cycle in inp["index_cycles"]:
                s.add(WpIndex(project_id=project.id, wp_code=f"{cycle}-1", wp_name=cycle, audit_cycle=cycle,
                              status=WpStatus.not_started))
            await s.flush()
            payload = (await resolve_member_scope(s, project.id, user.id)).to_payload()
    finally:
        await engine.dispose()
    assert payload == case["expected"]
    assert_valid("member-scope", payload)


def test_workpaper_file_classification_cases():
    from app.services.workpaper_file_backlog import FIXABLE, classify

    cases = load_cases("workpaper-file-materialization")
    assert sorted(FIXABLE) == sorted(cases["fixable"])
    for raw, expected in cases["classify"]:
        assert classify(raw)[0] == expected, raw


# ─── 任务状态机（真实 ProcedureTaskTransitionService，SQLite）─────────────────

_STAFF = {k: uuid.UUID(int=i) for i, k in enumerate(("A", "B", "R", "R2"), start=1)}
_START_LOCK, _START_ASSIGNMENT = 3, 1


async def _transition(svc, task, action: str, role: str, args: dict, actor: uuid.UUID):
    if action == "assign":
        return await svc.assign(task, new_assignee_staff_id=_STAFF["B"], actor_user_id=actor, actor_role=role)
    if action == "reassign":
        return await svc.reassign(task, new_assignee_staff_id=_STAFF["B"], actor_user_id=actor, actor_role=role,
                                  reason=args.get("reason", "原执行人请假，转派他人"))
    if action == "set_reviewer":
        return await svc.set_reviewer(task, new_reviewer_staff_id=_STAFF["R2"], actor_user_id=actor, actor_role=role)
    if action in ("acknowledge", "start", "review"):
        return await getattr(svc, action)(task, actor_user_id=actor, actor_role=role)
    if action == "submit":
        return await svc.submit(task, actor_user_id=actor, actor_role=role,
                                execution_summary=args.get("execution_summary", "已执行函证程序"),
                                evidence_snapshot=[{"kind": "cell", "ref": "D2A!B5"}])
    if action == "request_changes":
        return await svc.request_changes(task, actor_user_id=actor, actor_role=role, reason="请补充回函附件")
    if action == "cancel":
        return await svc.cancel(task, actor_user_id=actor, reason=args.get("reason", "本期无此业务"),
                                set_applicability=args.get("set_applicability"))
    if action == "reopen":
        return await svc.reopen(task, actor_user_id=actor, set_applicability=args.get("set_applicability"))
    raise AssertionError(f"未知动作 {action}")


@pytest.mark.parametrize("case", load_cases("task-state-machine")["cases"], ids=lambda c: c["name"])
async def test_task_state_machine_cases(case):
    from app.services.procedure_task_transition_service import ProcedureTaskTransitionService

    frm, expect = case["from"], case["expect"]
    engine, factory = await _sqlite()
    try:
        async with factory() as s:
            project = _project()
            s.add(project)
            await s.flush()
            wi = WpIndex(project_id=project.id, wp_code="D2", wp_name="应收账款", audit_cycle="D",
                         status=WpStatus.not_started)
            s.add(wi)
            await s.flush()
            wp = WorkingPaper(project_id=project.id, wp_index_id=wi.id, file_path="", file_version=1,
                              source_type=WpSourceType.template, parsed_data={})
            s.add(wp)
            dk = f"D2A::D2A::{uuid.uuid4().hex[:16]}"
            s.add(ProcedureRowDefinition(definition_key=dk, template_code="D2A", template_revision_hash="a" * 64,
                                         sheet_key="D2A", source_locator={}, program_no="1", procedure_text="程序",
                                         ref_snapshot=[], legacy_aliases=[], normalized_content={}))
            await s.flush()
            task = ProcedureRowTask(
                project_id=project.id, wp_index_id=wi.id, wp_id=wp.id if frm.get("wp") else None, definition_key=dk,
                sheet_key="D2A", wp_code="D2", program_no="1", definition_revision_hash="a" * 64,
                audit_cycle_snapshot="D", workflow_status=frm["workflow"], applicability_status=frm["applicability"],
                assignee_staff_id=_STAFF.get(frm.get("assignee")), reviewer_staff_id=_STAFF.get(frm.get("reviewer")),
                lock_version=_START_LOCK, assignment_version=_START_ASSIGNMENT,
            )
            s.add(task)
            await s.commit()
            task_id = task.id
        actor = uuid.uuid4()
        async with factory() as s:
            task = await s.get(ProcedureRowTask, task_id)
            try:
                result = await _transition(ProcedureTaskTransitionService(s), task, case["action"],
                                           case["actor_role"], case.get("args", {}), actor)
            except HTTPException as exc:
                await s.rollback()
                assert "error" in expect, f"意外失败 {exc.status_code}: {exc.detail}"
                assert exc.status_code == expect["error"], exc.detail
                result = None
            else:
                assert "error" not in expect, f"应失败 {expect['error']}，实际成功：{result}"
                await s.commit()
        async with factory() as s:
            after = await s.get(ProcedureRowTask, task_id)
            history = (await s.execute(sa.select(ProcedureRowTaskHistory).where(
                ProcedureRowTaskHistory.task_id == task_id))).scalars().all()
            outbox = (await s.execute(sa.select(TaskEvent).where(TaskEvent.aggregate_id == task_id))).scalars().all()
    finally:
        await engine.dispose()

    if "error" in expect:
        assert (after.workflow_status, after.applicability_status, after.lock_version) == (
            frm["workflow"], frm["applicability"], _START_LOCK), "失败零副作用"
        assert history == [] and outbox == []
        return
    changed = result["changed"] if isinstance(result, dict) else bool(result)
    assert changed is expect["changed"]
    assert (after.workflow_status, after.applicability_status) == (expect["workflow"], expect["applicability"])
    assert after.assignment_version - _START_ASSIGNMENT == expect["assignment_version_delta"]
    assert after.lock_version - _START_LOCK == expect["lock_version_delta"]
    if expect.get("assignee_cleared"):
        assert after.assignee_staff_id is None
    if expect["history"] is None:
        assert history == [] and outbox == [], "no-op 不写历史与 outbox"
        return
    [row] = history
    assert (row.event_type, row.from_status, row.to_status) == (
        expect["history"]["event_type"], expect["history"]["from_status"], expect["history"]["to_status"])
    assert_valid("procedure-task-event", orm_row(row), "/$defs/historyRow")
    [event] = outbox
    assert event.event_type == f"procedure_task.{row.event_type}"
    assert (event.aggregate_type, event.aggregate_version) == ("procedure_row_task", after.lock_version)
    assert event.idempotency_key == f"{task_id}:{row.event_type}:{after.lock_version}"
    assert_valid("procedure-task-event", event.payload)
    assert (event.payload["from_status"], event.payload["to_status"]) == (row.from_status, row.to_status)


# ─── 3. 服务层真实产物 ───────────────────────────────────────────────────────


def test_generation_receipt_payload_matches_contract(tmp_path):
    from app.services.procedure_scope_retention import GenerationPlan, TrimmedScope
    from app.services.wp_generate_file import GeneratedWorkpaperFile
    from app.services.wp_generation_receipt import GenerationReceipt

    plan = GenerationPlan(["D1", "D2", "X9"], ["H3", "H3-1"], ["E2"], ["E1"], TrimmedScope())
    assert_valid("generation-plan", plan.to_payload())
    receipt = GenerationReceipt.from_plan(plan)
    receipt.add_created("D1", GeneratedWorkpaperFile(path=tmp_path / "a.xlsx", from_template=True), header_filled=False)
    receipt.add_created("X9", GeneratedWorkpaperFile(path=tmp_path / "b.xlsx", from_template=False),
                        header_issue="打开底稿文件失败")
    receipt.add_failure("D2", OSError("模板文件被占用"))
    receipt.ignored_codes.append("Q1")
    payload = receipt.to_payload()
    assert_valid("generation-receipt", payload)
    assert payload["created"] == len(payload["created_codes"]) == 2 and payload["blank_codes"] == ["X9"]
    assert payload["header_unfilled"] == 1 and payload["failures"] == [{"wp_code": "D2", "error": "模板文件被占用"}]
    assert_valid("generation-receipt", {**payload, "skipped": 1, "skipped_codes": ["E1"]},
                 "/$defs/generateFromCodesResponse")
    operation_status = {
        "operation_id": str(uuid.uuid4()), "status": "materializing",
        "progress_total": 2, "progress_done": 1, "attempt": 1,
        "terminal": False, "resumable": False,
        "resumable_after": "2026-10-29T03:00:00+00:00", "public_error": None,
    }
    assert_valid("generation-receipt", operation_status, "/$defs/operationStatus")
    assert_valid("generation-receipt", {
        **operation_status, "status": "succeeded", "terminal": True,
        "resumable_after": None, "receipt": {**payload, "operation_id": operation_status["operation_id"],
                                                  "status": "succeeded"},
    }, "/$defs/operationStatus")
    assert errors_of("generation-receipt", {**operation_status, "status": "queued"}, "/$defs/operationStatus")
    assert errors_of("generation-receipt", {k: v for k, v in operation_status.items() if k != "attempt"},
                     "/$defs/operationStatus")
    assert errors_of("generation-receipt", {**payload, "skipped": 1}, "/$defs/generateFromCodesResponse"), \
        "按编码生成的响应少了原有字段 skipped_codes 要判不合规"
    for key in ("blank_codes", "message", "header_unfilled"):
        assert errors_of("generation-receipt", {k: v for k, v in payload.items() if k != key}), f"少了 {key} 要判不合规"


async def test_lifecycle_events_and_legacy_lineage_match_contract(monkeypatch):
    from app.services import workpaper_recycle_service as svc

    async def _no_epoch(*args, **kwargs):  # 可见性策略版本的写法是 PG 口径，不是本契约的对象
        return None

    monkeypatch.setattr(svc, "_bump_epoch", _no_epoch)
    engine, factory = await _sqlite()
    try:
        async with factory() as s:
            project = _project()
            actor = User(id=uuid.uuid4(), username=f"lc_{uuid.uuid4().hex[:8]}", email=f"{uuid.uuid4().hex[:8]}@t.example",
                         hashed_password="x", role=UserRole.auditor, is_active=True)
            s.add_all([project, actor])
            await s.flush()
            for code in ("H3", "H3-1"):
                idx = WpIndex(project_id=project.id, wp_code=code, wp_name=f"底稿{code}", audit_cycle="H",
                              status=WpStatus.not_started)
                s.add(idx)
                await s.flush()
                s.add(WorkingPaper(project_id=project.id, wp_index_id=idx.id, file_path="", file_version=1,
                                   source_type=WpSourceType.template))
            await s.flush()
            await svc.move_to_recycle_bin(s, project.id, ["H3", "H3-1"], kind=svc.KIND_TRIM, reason="程序裁剪：H3",
                                          actor_user_id=actor.id, trim_codes={"H3": ["H3"], "H3-1": ["H3"]},
                                          request_id="contract-1")
            await svc.restore_from_recycle_bin(s, project.id, ["H3-1"], kind=svc.KIND_TRIM, reason="恢复执行",
                                               actor_user_id=actor.id, request_id="contract-2")
            await s.commit()
            events = (await s.execute(sa.select(WorkpaperLifecycleEvent).order_by(
                WorkpaperLifecycleEvent.created_at, WorkpaperLifecycleEvent.wp_code))).scalars().all()
            lineage = [entry for idx in (await s.execute(sa.select(WpIndex))).scalars()
                       for entry in svc.read_lineage(idx)]
    finally:
        await engine.dispose()
    assert [(e.wp_code, e.event_type) for e in events] == [("H3", "recycled"), ("H3-1", "recycled"), ("H3-1", "restored")]
    for event in events:
        assert_valid("workpaper-lifecycle-event", orm_row(event))
    assert len(lineage) == 3
    for entry in lineage:
        assert_valid("workpaper-lifecycle-event", entry, "/$defs/legacyLineageEntry")


def test_backlog_rows_and_summary_match_contract():
    from app.services.workpaper_file_backlog import BacklogRow, summarize

    pid = uuid.uuid4()
    rows = [BacklogRow(uuid.uuid4(), pid, code, code, raw, category, None, None) for code, raw, category in (
        ("D1", "", "empty"), ("D2", f"storage/projects/{pid}/workpapers/D2.xlsx", "placeholder"),
        ("D3", "/tmp/x.xlsx", "missing"), ("E1", None, "empty"))]
    for row in rows:
        assert_valid("workpaper-file-materialization", row.to_payload())
    summary = summarize(rows, skip_codes=frozenset({"D3"}))
    assert_valid("workpaper-file-materialization", summary, "/$defs/backlogSummary")
    assert summary["totals"]["empty"] == 2 and summary["fixable"] == 3
