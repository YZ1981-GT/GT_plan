"""生成计划与粗裁状态（spec trim-generation-plan-linkage R1）。

SQLite 真 ORM + 真实服务：五态优先级、循环三态、业务分类只用于未保存的循环、冲突标记、母码跟随标注、
模板集过滤与不存在、循环顺序、粗裁状态只认已消费的粗裁凭证、契约 schema。
端点（TestClient 真发请求，只覆盖 get_db / get_current_user）：未登录 401、非成员 403、成员 200、模板集不存在 404。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

import app.models  # noqa: E402, F401
from app.core.database import get_db  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.models.base import Base, PermissionLevel, ProjectStatus, ProjectUserRole, UserRole  # noqa: E402
from app.models.core import Project, ProjectUser, User  # noqa: E402
from app.models.procedure_models import ProcedureInstance, ProcedureOperationPreview  # noqa: E402
from app.models.staff_models import ProjectAssignment, StaffMember  # noqa: E402
from app.models.workpaper_models import WpIndex, WpStatus, WpTemplateSet  # noqa: E402
from app.services import procedure_generation_plan as gp  # noqa: E402
from app.services import procedure_authorization as procedure_authz  # noqa: E402
from app.services.procedure_trim_confirmation import record_confirmations  # noqa: E402
from app.services.procedure_authorization import ensure_project_delegator  # noqa: E402
from tests.contracts._contract_schemas import assert_valid  # noqa: E402

NA, EX = "not_applicable", "execute"
SET_CODES = ["B1", "B5-1", "D0", "D2", "D2-1", "D2-5", "D4", "A17", "A1", "A1-12", "A18", "ZZ9"]
T0 = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def world():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids = {"pid": uuid.uuid4(), "set": uuid.uuid4(), "manager": uuid.uuid4(), "member": uuid.uuid4(),
           "outsider": uuid.uuid4(), "nostaff": uuid.uuid4()}
    async with factory() as s:
        for key, role in (("manager", UserRole.manager), ("member", UserRole.auditor),
                          ("outsider", UserRole.auditor), ("nostaff", UserRole.manager)):
            s.add(User(id=ids[key], username=f"u_{key}", email=f"{key}@t.example", hashed_password="x", role=role))
        s.add(Project(id=ids["pid"], name="【测试】生成计划", client_name="【测试】生成计划",
                      status=ProjectStatus.execution, template_type="soe", report_scope="standalone", audit_year=2025))
        s.add(WpTemplateSet(id=ids["set"], set_name="【测试】计划模板集", template_codes=SET_CODES))
        await s.flush()
        s.add(StaffMember(user_id=ids["manager"], name="王经理"))
        s.add(ProjectUser(project_id=ids["pid"], user_id=ids["member"], role=ProjectUserRole.auditor,
                          permission_level=PermissionLevel.readonly))
        for n, (code, cycle, status) in enumerate((
            ("D0", "D", EX), ("D2-1至D2-4", "D", NA), ("D2-5", "D", NA), ("D2-6至D2-13", "D", NA),
            ("A17", "A", EX), ("A1", "A", EX),
        )):
            s.add(ProcedureInstance(project_id=ids["pid"], audit_cycle=cycle, procedure_code=code, procedure_name=f"程序{code}",
                                    status=status, wp_code=code, sort_order=n * 10,
                                    skip_reason="本期无应收账款" if status == NA else None))
        s.add(WpIndex(project_id=ids["pid"], wp_code="D0", wp_name="D0", audit_cycle="D", status=WpStatus.not_started))
        # 已生成又被裁掉（D2-5 行不执行）：状态按优先级报「已裁剪」，不报「已生成」
        s.add(WpIndex(project_id=ids["pid"], wp_code="D2-5", wp_name="D2-5", audit_cycle="D", status=WpStatus.not_started))
        s.add(WpIndex(project_id=ids["pid"], wp_code="B5-1", wp_name="B5-1", audit_cycle="B",
                      status=WpStatus.not_started, is_deleted=True))
        await s.commit()
    w = {"factory": factory, **ids}
    yield w
    await engine.dispose()


async def _preview(w, *, cycle: str, actor: str = "manager", consumed_at=T0, operation: str = "trim") -> None:
    async with w["factory"]() as s:
        preview = ProcedureOperationPreview(
            actor_user_id=w[actor], project_id=w["pid"], operation=operation, request_hash="a" * 64,
            request_payload_snapshot={"entries": [{"kind": "scope", "cycle": cycle, "wp_index_code": f"{cycle}1",
                                                   "target_status": "execute"}], "operation": operation},
            target_versions={}, membership_snapshot={}, membership_snapshot_hash="b" * 64,
            expires_at=T0 + timedelta(minutes=10), consumed_at=consumed_at,
            consumed_request_id=f"req-{uuid.uuid4().hex}" if consumed_at else None,
        )
        s.add(preview)
        await s.flush()
        if consumed_at is not None and operation == "trim":
            # 生产上只有 consume_and_apply 消费粗裁凭证，并在同一事务写确认投影（follow-up R3）
            await record_confirmations(s, preview)
        await s.commit()


async def _plan(w, template_set_id="default"):
    async with w["factory"]() as s:
        return await gp.build_generation_plan(s, w["pid"], w["set"] if template_set_id == "default" else template_set_id)


def _items(plan) -> dict[str, dict]:
    return {it["wp_code"]: it for c in plan["cycles"] for it in c["items"]}


def _cycle(plan, code) -> dict:
    return next(c for c in plan["cycles"] if c["cycle"] == code)


# ── 服务 ─────────────────────────────────────────────────────────────────


async def test_states_priority_cycle_states_and_contract(world):
    await _preview(world, cycle="D")
    await _preview(world, cycle="A", consumed_at=None)               # 没消费的凭证不算保存
    await _preview(world, cycle="A", operation="delegate")            # 委派凭证不算粗裁保存
    plan = await _plan(world)
    assert_valid("generation-plan-view", plan, "/$defs/plan")
    assert [c["cycle"] for c in plan["cycles"]] == ["B", "D", "A", "Z"], "与裁剪页页签同序，其他循环排最后"
    assert plan["template_set"] == {"id": str(world["set"]), "set_name": "【测试】计划模板集", "code_count": 12}
    assert plan["business_category"] == {"code": "C", "defaulted": True}
    items = _items(plan)
    assert {c: items[c]["state"] for c in SET_CODES} == {
        "B1": "to_create", "B5-1": "in_recycle",
        "D0": "existing", "D2": "trimmed", "D2-1": "trimmed", "D2-5": "trimmed", "D4": "to_create",
        "A17": "category_excluded", "A1": "to_create", "A1-12": "category_excluded", "A18": "category_excluded",
        "ZZ9": "to_create",
    }
    assert (items["D2"]["decided_by"], items["D2"]["follows_children"]) == ("D2-1至D2-4", True), "审定表跟随科目程序"
    assert items["D2-1"]["follows_children"] is False and items["D4"]["decided_by"] is None
    assert items["A1-12"]["decided_by"] == "A1" and items["A1-12"]["category_reason"]
    assert items["A1"]["category_reason"] is None and items["A17"]["category_conflict"] is False
    d = _cycle(plan, "D")
    assert (d["trim_state"], d["confirmed_by"]) == ("confirmed", "王经理")
    assert d["confirmed_at"].startswith("2026-10-01T08:00:00")
    assert [(p["code"], p["status"], p["origin"]) for p in d["programs"]][:3] == [
        ("D0", EX, "catalog"), ("D2-1至D2-4", NA, "catalog"), ("D2-5", NA, "catalog")]
    assert d["counts"] == {"total": 5, "to_create": 1, "existing": 1, "in_recycle": 0, "trimmed": 3, "category_excluded": 0}
    assert (_cycle(plan, "A")["trim_state"], _cycle(plan, "B")["trim_state"]) == ("unconfirmed", "not_initialized")
    assert _cycle(plan, "B")["programs"] == []
    assert plan["totals"] == {"total": 12, "to_create": 4, "existing": 1, "in_recycle": 1, "trimmed": 3,
                              "category_excluded": 3}


async def test_category_default_only_for_unsaved_cycles_and_conflict_flag(world):
    await _preview(world, cycle="A", actor="nostaff")
    plan = await _plan(world)
    items = _items(plan)
    assert items["A17"]["state"] == "to_create" and items["A17"]["category_conflict"] is True, (
        "保存过粗裁的循环以程序行为准：业务分类不适用但程序行执行 ⇒ 生成并标冲突")
    assert items["A18"]["state"] == "to_create" and items["A18"]["category_conflict"] is True
    assert _cycle(plan, "A")["confirmed_by"] == "u_nostaff", "没有人员档案时用登录名"


async def test_latest_save_wins_and_unknown_or_missing_template_set(world):
    await _preview(world, cycle="D", consumed_at=T0)
    await _preview(world, cycle="D", actor="nostaff", consumed_at=T0 + timedelta(hours=2))
    plan = await _plan(world)
    assert _cycle(plan, "D")["confirmed_by"] == "u_nostaff" and _cycle(plan, "D")["confirmed_at"].startswith("2026-10-01T10")
    with pytest.raises(gp.TemplateSetNotFound):
        await _plan(world, uuid.uuid4())
    async with world["factory"]() as s:
        template_set = await s.get(WpTemplateSet, world["set"])
        template_set.is_deleted = True
        await s.commit()
    with pytest.raises(gp.TemplateSetNotFound):
        await _plan(world)
    async with world["factory"]() as s:
        template_set = await s.get(WpTemplateSet, world["set"])
        template_set.is_deleted = False
        await s.commit()
    everything = await _plan(world, None)
    assert everything["template_set"] is None and everything["totals"]["total"] == 1025
    assert_valid("generation-plan-view", everything, "/$defs/plan")


async def test_scope_confirmations(world):
    await _preview(world, cycle="D")
    async with world["factory"]() as s:
        out = await gp.build_scope_confirmations(s, world["pid"])
    assert_valid("generation-plan-view", out, "/$defs/confirmations")
    by = {c["cycle"]: c for c in out["cycles"]}
    assert list(by) == list("BCDEFGHIJKLMNAS")
    assert (by["D"]["trim_state"], by["D"]["program_count"], by["D"]["confirmed_by"]) == ("confirmed", 4, "王经理")
    assert (by["A"]["trim_state"], by["A"]["program_count"], by["A"]["confirmed_at"]) == ("unconfirmed", 2, None)
    assert by["B"]["trim_state"] == "not_initialized"


async def test_plan_reads_confirmation_projection_not_preview_history(world):
    """follow-up R3：生成计划只读确认投影，正常请求不扫描预览凭证 JSON 历史。"""
    from sqlalchemy import event

    await _preview(world, cycle="D")
    statements: list[str] = []
    sync_engine = world["factory"].kw["bind"].sync_engine

    def _capture(_conn, _cursor, statement, *_args):
        statements.append(statement)

    event.listen(sync_engine, "before_cursor_execute", _capture)
    try:
        plan = await _plan(world)
    finally:
        event.remove(sync_engine, "before_cursor_execute", _capture)
    assert _cycle(plan, "D")["trim_state"] == "confirmed"
    assert any("procedure_trim_cycle_confirmations" in st for st in statements)
    assert not [st for st in statements if "procedure_operation_previews" in st]


async def test_read_failure_is_fail_closed(world, monkeypatch):
    async def boom(*_a, **_k):
        from sqlalchemy.exc import OperationalError
        raise OperationalError("SELECT 1", {}, Exception("库不可用"))

    async with world["factory"]() as s:
        monkeypatch.setattr(s, "execute", boom)
        with pytest.raises(gp.TrimScopeUnavailable):
            await gp.load_cycle_confirmations(s, world["pid"])


async def test_delegator_guard_blocks_archived_deleted_and_missing_projects(world, monkeypatch):
    """初始化 / 粗裁共用的委派人门：任何身份都不能改归档或已删除项目，并设置项目上下文后才放行。"""
    async with world["factory"]() as s:
        project = await s.get(Project, world["pid"])
        manager = await s.get(User, world["manager"])
        staff = (await s.execute(sa.select(StaffMember).where(StaffMember.user_id == manager.id))).scalar_one()
        s.add(ProjectAssignment(project_id=project.id, staff_id=staff.id, role="manager"))
        await s.flush()
        rls_calls = []

        async def record_rls(_db, project_id):
            rls_calls.append(project_id)

        monkeypatch.setattr(procedure_authz, "set_rls_context", record_rls)
        passed = await ensure_project_delegator(s, manager, project.id)
        assert passed.project_id == project.id and rls_calls == [project.id]

        project.status = ProjectStatus.archived
        await s.flush()
        for actor in (manager, _Actor(world["manager"], UserRole.admin)):
            with pytest.raises(HTTPException) as ei:
                await ensure_project_delegator(s, actor, project.id)
            assert ei.value.status_code == 423 and ei.value.detail["error_code"] == "PROJECT_ARCHIVED"

        project.status = ProjectStatus.execution
        project.is_deleted = True
        await s.flush()
        admin = _Actor(world["manager"], UserRole.admin)
        for project_id in (project.id, uuid.uuid4()):
            with pytest.raises(HTTPException) as ei:
                await ensure_project_delegator(s, admin, project_id)
            assert ei.value.status_code == 404


# ── 端点 ─────────────────────────────────────────────────────────────────


def test_frontend_paths_match_backend_routes_verbatim():
    """前端 apiPaths 访问器 ↔ 后端注册路径逐字一致（拼错一个字母就是 404，单测 mock 掉接口发现不了）。"""
    import re
    from pathlib import Path

    from app.routers.procedures import router

    src = (Path(__file__).resolve().parents[2] / "audit-platform/frontend/src/services/apiPaths/workpaper.ts").read_text(
        encoding="utf-8")
    backend = {r.path for r in router.routes}
    for name, suffix in (("generationPlan", "generation-plan"), ("scopeConfirmations", "confirmations")):
        m = re.search(rf"\b{name}:\s*\(pid: string\)\s*=>\s*`([^`]+)`", src)
        assert m, f"apiPaths 未声明 {name}"
        assert m.group(1).replace("${pid}", "{project_id}") == f"/api/projects/{{project_id}}/procedure-scope/{suffix}"
        assert f"/api/projects/{{project_id}}/procedure-scope/{suffix}" in backend


class _Actor:
    def __init__(self, uid: uuid.UUID, role: UserRole) -> None:
        self.id, self.role, self.username, self.is_active = uid, role, f"u-{uid.hex[:4]}", True


@pytest_asyncio.fixture
async def client(world):
    from app.routers.procedures import router

    app = FastAPI()
    app.include_router(router)

    async def _db():
        async with world["factory"]() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    current: dict = {}

    def as_(who: str | None) -> None:
        if who is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            role = UserRole.auditor if who in ("member", "outsider") else UserRole.manager
            current["actor"] = _Actor(world[who], role)
            app.dependency_overrides[get_current_user] = lambda: current["actor"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, as_


async def test_endpoints_authz_and_shapes(world, client):
    http, as_ = client
    base = f"/api/projects/{world['pid']}/procedure-scope"
    as_(None)
    assert (await http.get(f"{base}/generation-plan")).status_code == 401
    as_("outsider")
    assert (await http.get(f"{base}/generation-plan")).status_code == 403
    assert (await http.get(f"{base}/confirmations")).status_code == 403
    as_("member")
    res = await http.get(f"{base}/generation-plan", params={"template_set_id": str(world["set"])})
    assert res.status_code == 200, res.text
    assert_valid("generation-plan-view", res.json(), "/$defs/plan")
    assert (await http.get(f"{base}/generation-plan", params={"template_set_id": str(uuid.uuid4())})).status_code == 404
    res = await http.get(f"{base}/confirmations")
    assert res.status_code == 200 and len(res.json()["cycles"]) == 15
