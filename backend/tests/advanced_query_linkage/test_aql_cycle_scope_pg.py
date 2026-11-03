"""循环级可见性（advanced-query-linkage-closure 任务 23，ADR-AQL-19，design §3.10 / §10.2「循环范围」行；R3.8）。

改造前（AQ-19 循环范围部分）：团队分配只勾 D 循环的审计员，在试算表页只见 D 循环科目、在调整分录页只见含 D 科目的分录组、
在附注页只见 D 循环章节；在高级查询里全部可见，构建器还能跨项目按表查。现在业务视图的试算表、调整分录、附注目录 / 章节 /
指标树附注分支与这三个页面同口径（平台唯一入口 ``deps.get_user_scope_cycles``），构建器把本人受限的项目排除出作用域。

全部写入在回滚事务里：新建【测试】项目，复制华氏（只读）的试算表与附注、造两组调整分录，再建临时用户（系统经理）、
一条人员记录、项目成员行（``scope_cycles`` 为空）与委派（角色 auditor、``assigned_cycles=['D']``）。金标准 = 平台入口的
返回值经 ``mapping_service`` 映射出的科目 / 章节集合，按独立 SQL 现算。
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import fakeredis
import fakeredis.aioredis
import pytest
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event

import app.core.redis as core_redis
from app import deps
from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import UserRole
from app.models.core import PermissionLevel, Project, ProjectUser, ProjectUserRole, User
from app.models.report_models import DisclosureNote
from app.models.staff_models import ProjectAssignment, StaffMember
from app.routers import custom_query
from app.services.custom_query import audit_helper, cycle_scope
from app.services.custom_query.builder_access import CYCLE_SCOPED_REASON
from app.services.disclosure_engine import DisclosureEngine
from app.services.mapping_service import get_codes_by_cycles, get_sections_by_cycles
from tests.advanced_query_linkage.gold import AUDIT_YEAR, HS
from tests.authz_world import build_app

pytestmark = pytest.mark.pg_only
EXEC = "/api/custom-query/execute"
IND = "/api/custom-query/indicators"


async def _columns(session, table: str) -> list[str]:
    return [r[0] for r in (await session.execute(sa.text(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = :t "
        "AND is_generated = 'NEVER' ORDER BY ordinal_position"), {"t": table})).all()]


async def _copy_from_hs(session, table: str, pid: uuid.UUID) -> int:
    """把华氏该年度的行复制到【测试】项目（新 id、新项目，其余列原值；华氏行只读）。"""
    cols = await _columns(session, table)
    exprs = ["gen_random_uuid()" if c == "id" else ":pid" if c == "project_id" else c for c in cols]
    result = await session.execute(sa.text(
        f"INSERT INTO {table} ({', '.join(cols)}) SELECT {', '.join(exprs)} FROM {table} "
        f"WHERE project_id = :hs AND year = :year AND NOT is_deleted"), {"pid": pid, "hs": HS, "year": AUDIT_YEAR})
    return result.rowcount


async def _seed_adjustments(session, pid: uuid.UUID, d_code: str, other_code: str) -> dict[str, uuid.UUID]:
    """两组分录：IN 组一行 D 循环科目 + 一行非 D 科目（整组可见）；OUT 组两行都是非 D 科目（不可见）。"""
    creator = (await session.execute(sa.text("SELECT id FROM users WHERE username = 'admin'"))).scalar_one()
    groups = {"IN": uuid.uuid4(), "OUT": uuid.uuid4()}
    for number, account, debit, credit in (("AQLB6-IN", d_code, "10.00", "0.00"), ("AQLB6-IN", other_code, "0.00", "10.00"),
                                           ("AQLB6-OUT", other_code, "3.00", "0.00"), ("AQLB6-OUT", "1002", "0.00", "3.00")):
        await session.execute(sa.text(
            "INSERT INTO adjustments (id, project_id, year, company_code, adjustment_no, adjustment_type, description, account_code, "
            "account_name, debit_amount, credit_amount, entry_group_id, created_by) VALUES (:id, :pid, :year, 'AQLB6', :no, "
            "CAST('aje' AS adjustment_type), '【测试】B6 回滚事务造行', :acct, :acct, :dr, :cr, :grp, :creator)"),
            {"id": uuid.uuid4(), "pid": pid, "year": AUDIT_YEAR, "no": number, "acct": account, "dr": Decimal(debit),
             "cr": Decimal(credit), "grp": groups["IN" if number.endswith("IN") else "OUT"], "creator": creator})
    return groups


@pytest.fixture
async def world(pg_rollback_session):
    session = pg_rollback_session
    pid = uuid.uuid4()
    hs = await session.get(Project, HS)
    session.add(Project(id=pid, name="【测试】B6 循环范围", client_name="【测试】B6 循环范围",
                        template_type=hs.template_type, report_scope="standalone"))
    await session.flush()
    tb = await _copy_from_hs(session, "trial_balance", pid)
    notes = await _copy_from_hs(session, "disclosure_notes", pid)
    user = User(id=uuid.uuid4(), username=f"aql-b6-{uuid.uuid4().hex[:8]}", email=f"aql-b6-{uuid.uuid4().hex[:8]}@test.invalid",
                hashed_password="x", role=UserRole.manager, is_active=True)
    session.add(user)
    await session.flush()
    staff = StaffMember(user_id=user.id, name="【测试】B6 人员")
    session.add(staff)
    await session.flush()
    session.add(ProjectUser(project_id=pid, user_id=user.id, role=ProjectUserRole.auditor,
                            permission_level=PermissionLevel.edit))
    assignment = ProjectAssignment(project_id=pid, staff_id=staff.id, role="auditor", assigned_cycles=["D"],
                                   assigned_at=datetime.now(timezone.utc))
    session.add(assignment)
    await session.flush()
    d_codes = await get_codes_by_cycles(pid, ["D"])
    d_sections = await get_sections_by_cycles(pid, ["D"])
    assert tb > 0 and notes > 0 and d_codes and d_sections, "前置：华氏有试算表与附注、D 循环有科目与章节"
    assert "1001" not in d_codes and "1002" not in d_codes, "前置：库存现金 / 银行存款不是 D 循环科目"
    # 让 D 循环的一个章节在本项目存在（华氏是国企编号，D 循环章节是映射表登记的编号，原本交集可能为空）
    d_section = sorted(d_sections)[0]
    if not (await session.execute(sa.select(DisclosureNote.id).where(
            DisclosureNote.project_id == pid, DisclosureNote.note_section == d_section))).first():
        session.add(DisclosureNote(project_id=pid, year=AUDIT_YEAR, note_section=d_section, section_title="【测试】B6 D 循环章节",
                                   sort_order=0, table_data={"_tables": [{"name": "明细", "headers": ["项目", "期末余额"],
                                                                          "rows": [{"label": "甲", "values": [1]}]}]}))
        await session.flush()
    groups = await _seed_adjustments(session, pid, sorted(d_codes)[0], "1001")
    yield type("W", (), {"session": session, "pid": pid, "user": user, "assignment": assignment, "d_codes": d_codes,
                         "d_sections": d_sections, "d_section": d_section, "groups": groups})


@asynccontextmanager
async def _client(session, user: User, monkeypatch, *routers: Any) -> AsyncIterator[AsyncClient]:
    redis = fakeredis.aioredis.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)
    monkeypatch.setattr(core_redis, "redis_client", redis)
    monkeypatch.setattr(core_redis, "_redis_client", redis)

    async def _no_audit(**_kwargs):
        return True

    monkeypatch.setattr(audit_helper, "_log_unthrottled", _no_audit)
    api = build_app(*(routers or (custom_query.router,)))

    async def _db():
        yield session

    async def _user() -> User:
        return user

    api.dependency_overrides[get_db] = _db
    api.dependency_overrides[get_current_user] = _user
    try:
        async with AsyncClient(transport=ASGITransport(app=api), base_url="http://aql-b6") as http:
            yield http
    finally:
        await redis.aclose()


async def _rows(http: AsyncClient, pid: uuid.UUID, source: str, **body: Any) -> dict:
    response = await http.post(EXEC, json={"project_id": str(pid), "year": AUDIT_YEAR, "source": source,
                                           "limit": 2000, **body})
    assert response.status_code == 200, response.text[:800]
    return response.json()


async def _tb_gold(session, pid: uuid.UUID, codes: frozenset[str] | set[str] | None) -> int:
    where = "" if codes is None else "AND standard_account_code = ANY(:codes)"
    params: dict[str, Any] = {"pid": pid, "year": AUDIT_YEAR}
    if codes is not None:
        params["codes"] = sorted(codes)
    return (await session.execute(sa.text(
        f"SELECT count(*) FROM trial_balance WHERE project_id = :pid AND year = :year AND NOT is_deleted {where}"),
        params)).scalar_one()


async def _tree_sections(http: AsyncClient, pid: uuid.UUID) -> tuple[list[str], str]:
    response = await http.get(IND, params={"project_id": str(pid), "year": AUDIT_YEAR, "branch": "disclosure"})
    assert response.status_code == 200, response.text[:800]
    leaves = [leaf for node in response.json() for leaf in ([node] if "children" not in node else node["children"])]
    assert leaves[0]["key"] == "disclosure", "附注分支首个叶子应为「附注目录」"
    return [leaf["key"].split(":", 1)[1] for leaf in leaves[1:]], response.headers["X-Notes-Version"]


async def test_platform_entry_is_the_only_source(world) -> None:
    """金标准：平台入口返回团队分配勾选的 D；本模块的范围 = 它经 mapping_service 映射的集合，带缓存与不带结果相同。"""
    assert await deps.get_user_scope_cycles(world.user, world.pid, world.session) == ["D"]
    plain = await cycle_scope.resolve_cycle_scope(world.user, world.pid, world.session)
    cache = cycle_scope.CycleScopeCache(world.user, world.session)
    cached = [await cycle_scope.resolve_cycle_scope(world.user, world.pid, world.session, cache) for _ in range(2)]
    assert plain == cached[0] == cached[1] == cycle_scope.CycleScope(frozenset(world.d_codes), frozenset(world.d_sections))
    assert cycle_scope.deps.get_user_scope_cycles is deps.get_user_scope_cycles


async def test_restricted_member_sees_only_cycle_rows(world, monkeypatch, builder) -> None:
    """团队分配勾选 D、成员行范围为空：试算表 / 调整分录 / 附注都只见 D；构建器排除该项目（变异 #19 / #19b / #36）。"""
    # 构建器：系统经理凭系统角色准入，唯一可访问的项目对其设有循环范围 ⇒ 排除（0 行 + 排除提示），显式指定 403
    executed = await builder.request(world.user, "POST", "/execute",
                                     {"table": "trial_balance", "fields": ["project_id"], "limit": 100})
    assert executed.status_code == 200, executed.text[:500]
    assert executed.json()["total"] == 0 and any("已排除 1 个" in w for w in executed.json()["warnings"])
    explicit = await builder.request(world.user, "POST", "/execute",
                                     {"table": "trial_balance", "fields": ["project_id"], "project_id": str(world.pid)})
    assert explicit.status_code == 403 and explicit.json()["detail"]["error_code"] == "CYCLE_SCOPED_PROJECT"
    access = (await builder.request(world.user, "GET", "/access")).json()
    assert (access["accessible_project_count"], access["reason"]) == (0, CYCLE_SCOPED_REASON)
    async with _client(world.session, world.user, monkeypatch) as http:
        tb = await _rows(http, world.pid, "trial_balance")
        assert tb["total"] == await _tb_gold(world.session, world.pid, world.d_codes) > 0
        assert {r["standard_account_code"] for r in tb["rows"]} <= set(world.d_codes)
        adj = await _rows(http, world.pid, "adjustment")
        assert {r["entry_group_id"] for r in adj["rows"]} == {str(world.groups["IN"])}, "只见含 D 科目的分录组（整组）"
        assert adj["total"] == 2
        sections, _version = await _tree_sections(http, world.pid)
        tree = await DisclosureEngine(world.session).get_notes_tree(world.pid, AUDIT_YEAR)
        assert sections == [n["note_section"] for n in tree if n["note_section"] in world.d_sections]
        assert world.d_section in sections
        catalog = await _rows(http, world.pid, "disclosure")
        assert {r["note_section"] for r in catalog["rows"]} <= set(world.d_sections) and catalog["total"] > 0
        outside = next(n["note_section"] for n in tree if n["note_section"] not in world.d_sections)
        denied = await http.post(EXEC, json={"project_id": str(world.pid), "year": AUDIT_YEAR,
                                             "source": f"disclosure_note:{outside}"})
        assert denied.status_code == 403, denied.text[:500]
        assert denied.json()["detail"]["error_code"] == "SECTION_OUT_OF_SCOPE"


async def test_supervisor_is_unrestricted_and_empty_selection_sees_nothing(world, monkeypatch) -> None:
    """委派角色改为经理（链路唯一 ⇒ 本项目主管）⇒ 不限；改回审计员且勾选为空 ⇒ 三源都无行。"""
    world.assignment.role = "manager"
    await world.session.flush()
    async with _client(world.session, world.user, monkeypatch) as http:
        tb = await _rows(http, world.pid, "trial_balance", limit=1999)
        assert tb["total"] == await _tb_gold(world.session, world.pid, None)
        assert (await _rows(http, world.pid, "adjustment", limit=1999))["total"] == 4
    world.assignment.role, world.assignment.assigned_cycles = "auditor", []
    await world.session.flush()
    async with _client(world.session, world.user, monkeypatch) as http:
        assert (await _rows(http, world.pid, "trial_balance", limit=1998))["total"] == 0
        assert (await _rows(http, world.pid, "adjustment", limit=1998))["total"] == 0
        assert (await _rows(http, world.pid, "disclosure", limit=1998))["total"] == 0
        sections, _version = await _tree_sections(http, world.pid)
        assert sections == []


async def test_platform_query_failure_does_not_abort_the_request(world, monkeypatch) -> None:
    """故障注入（注在平台入口的下一层）：入口里第一条查 staff_members 的语句改写为 ``SELECT 1/0``，真实制造一次 PG 语句失败
    （事务进入 aborted，平台函数吞掉并返回受限空集）⇒ 请求 200、0 行，同一请求随后的取数照常执行（变异 #39）。"""
    assert cycle_scope.deps.get_user_scope_cycles is deps.get_user_scope_cycles, "被测的平台入口不得被替换"
    fired: list[str] = []

    def _inject(_conn, _cursor, statement, parameters, _context, _executemany):
        if not fired and statement.lstrip().startswith("SELECT staff_members.id") and "JOIN" not in statement:
            fired.append(statement)
            return "SELECT 1/0", ()
        return statement, parameters

    sync_conn = (await world.session.connection()).sync_connection
    event.listen(sync_conn, "before_cursor_execute", _inject, retval=True)
    try:
        async with _client(world.session, world.user, monkeypatch) as http:
            response = await http.post(EXEC, json={"project_id": str(world.pid), "year": AUDIT_YEAR,
                                                   "source": "trial_balance", "limit": 1997})
    finally:
        event.remove(sync_conn, "before_cursor_execute", _inject)
    assert fired, "故障没有注入到平台入口的人员查询（判据空转）"
    assert response.status_code == 200, f"平台入口吞掉异常后事务应已回滚到保存点：{response.status_code} {response.text[:300]}"
    assert response.json()["total"] == 0, "读取失败按受限空集（fail-closed）"
    # 同一会话随后的查询照常（事务没有停在 aborted）
    assert await _tb_gold(world.session, world.pid, None) > 0
