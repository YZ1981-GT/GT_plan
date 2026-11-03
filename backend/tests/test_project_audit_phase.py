"""项目当前审计阶段与预审截止日（spec voucher-identity-writeback-and-audit-phase 任务 8，需求 6.1 / 6.2 / 6.5）。

SQLite 真 ORM 行 + 端点级请求（只挂 project_audit_phase 与 voucher_links 两个路由；覆盖内层 get_db /
get_current_user，让真实的项目成员判定与委派人判定跑）：

- 表驱动：admin、项目经理、签字合伙人可改；审计员、EQCR（partner + review）、只读成员 403；非成员读也 403；
- 只收 preliminary / final（其他 422）；预审截止日须在审计期间内且早于期末（422）；没变化不记改动；
- 归档项目只读（423）；项目详情返回两个字段；
- 挂凭与抽凭没给阶段时按项目当前阶段（需求 6.2），抽凭给非法阶段 422（需求 6.5）。
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_models import TbLedger
from app.models.base import Base, ProjectStatus, ProjectType
from app.models.core import Project, ProjectUser, User
from app.models.staff_models import ProjectAssignment, StaffMember
from app.models.workpaper_models import SampledVoucher

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

PROJECT, ARCHIVED, YEAR_ONLY, YEAR = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), 2025
#: 用户名 → (系统角色, 项目职责 assignment.role, project_users.role, project_users.permission_level)
#: 系统角色一律给 auditor（只有 admin 有全局放行），项目里的身份全看委派与成员行
MEMBERS = {
    "admin": ("admin", None, None, None),
    "manager": ("auditor", "manager", "manager", "edit"),
    "signing_partner": ("auditor", "signing_partner", "partner", "edit"),
    "auditor": ("auditor", "auditor", "auditor", "edit"),
    "eqcr": ("auditor", "eqcr", "partner", "review"),
    "reader": ("auditor", None, "readonly", "readonly"),
    "stranger": ("auditor", None, None, None),
}
UID = {name: uuid.uuid4() for name in MEMBERS}


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        for name, (sys_role, assign_role, pu_role, level) in MEMBERS.items():
            session.add(User(id=UID[name], username=name, email=f"{name}@test.com", hashed_password="x",
                             role=sys_role))
        for pid, status in ((PROJECT, ProjectStatus.execution), (ARCHIVED, ProjectStatus.archived)):
            session.add(Project(id=pid, name=f"阶段测试 {pid.hex[:4]}", client_name="测试", status=status,
                                project_type=ProjectType.annual, created_by=UID["admin"],
                                audit_period_start=date(2025, 1, 1), audit_period_end=date(2025, 12, 31)))
        # 向导只填了审计年度、没填期间（真实新建项目即如此）
        session.add(Project(id=YEAR_ONLY, name="只有年度", client_name="测试", status=ProjectStatus.created,
                            project_type=ProjectType.annual, created_by=UID["admin"], audit_year=2025))
        await session.flush()
        for name, (_, assign_role, pu_role, level) in MEMBERS.items():
            if pu_role:
                for pid in (PROJECT, ARCHIVED):
                    session.add(ProjectUser(project_id=pid, user_id=UID[name], role=pu_role,
                                            permission_level=level, is_deleted=False))
            if assign_role:
                staff = StaffMember(id=uuid.uuid4(), user_id=UID[name], name=name)
                session.add(staff)
                await session.flush()
                for pid in (PROJECT, ARCHIVED):
                    session.add(ProjectAssignment(project_id=pid, staff_id=staff.id, role=assign_role))
        session.add(TbLedger(id=uuid.uuid4(), project_id=PROJECT, year=YEAR, company_code="001",
                             voucher_date=date(2025, 3, 5), voucher_type="记", voucher_no="0007",
                             account_code="1002", debit_amount=100, credit_amount=None))
        await session.commit()
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.deps import get_current_user
    from app.routers import project_audit_phase, voucher_links

    app = FastAPI()
    app.include_router(project_audit_phase.router)
    app.include_router(voucher_links.router)
    state = {"user": "manager"}

    async def _db():
        yield db

    async def _user():
        return (await db.execute(sa.select(User).where(User.id == UID[state["user"]]))).scalar_one()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.as_user = lambda name: state.update(user=name)  # type: ignore[attr-defined]
        yield c


def _url(pid: uuid.UUID = PROJECT) -> str:
    return f"/api/projects/{pid}/audit-phase"


async def _stored(db, pid: uuid.UUID = PROJECT) -> tuple[str, date | None]:
    db.expire_all()
    p = await db.get(Project, pid)
    return p.current_audit_phase, p.interim_cutoff_date


@pytest.mark.parametrize(("who", "can_edit"), [
    ("admin", True), ("manager", True), ("signing_partner", True),
    ("auditor", False), ("eqcr", False), ("reader", False),
])
async def test_members_read_phase_and_learn_whether_they_can_edit(client, who, can_edit):
    client.as_user(who)
    resp = await client.get(_url())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["current_audit_phase"], body["interim_cutoff_date"], body["can_edit"]) == ("final", None, can_edit)
    assert (body["audit_period_start"], body["audit_period_end"]) == ("2025-01-01", "2025-12-31")


async def test_non_member_cannot_read(client):
    client.as_user("stranger")
    assert (await client.get(_url())).status_code == 403


@pytest.mark.parametrize(("who", "status"), [
    ("admin", 200), ("manager", 200), ("signing_partner", 200),
    ("auditor", 403), ("eqcr", 403), ("reader", 403), ("stranger", 403),
])
async def test_only_manager_partner_admin_can_change(client, db, who, status):
    client.as_user(who)
    resp = await client.put(_url(), json={"current_audit_phase": "preliminary", "interim_cutoff_date": "2025-09-30"})
    assert resp.status_code == status, resp.text
    expected = ("preliminary", date(2025, 9, 30)) if status == 200 else ("final", None)
    assert await _stored(db) == expected
    if status == 200:
        assert resp.json()["changed"] is True and resp.json()["interim_cutoff_date"] == "2025-09-30"


@pytest.mark.parametrize("body", [
    {"current_audit_phase": "interim"},
    {"current_audit_phase": "current"},
    {"current_audit_phase": "FINAL"},
    {},
])
async def test_only_two_phase_values_accepted(client, db, body):
    resp = await client.put(_url(), json=body)
    assert resp.status_code == 422, resp.text
    assert await _stored(db) == ("final", None)


@pytest.mark.parametrize("cutoff", ["2024-12-31", "2025-12-31", "2026-01-15"])
async def test_cutoff_must_be_inside_period_and_before_period_end(client, db, cutoff):
    resp = await client.put(_url(), json={"current_audit_phase": "preliminary", "interim_cutoff_date": cutoff})
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["error_code"] == "INTERIM_CUTOFF_OUT_OF_PERIOD"
    assert await _stored(db) == ("final", None)


async def test_project_without_period_uses_audit_year_bounds(client, db):
    client.as_user("admin")
    got = (await client.get(_url(YEAR_ONLY))).json()
    assert (got["audit_period_start"], got["audit_period_end"]) == ("2025-01-01", "2025-12-31")
    bad = await client.put(_url(YEAR_ONLY), json={"current_audit_phase": "preliminary",
                                                  "interim_cutoff_date": "2026-01-15"})
    assert bad.status_code == 422 and bad.json()["detail"]["error_code"] == "INTERIM_CUTOFF_OUT_OF_PERIOD"
    ok = await client.put(_url(YEAR_ONLY), json={"current_audit_phase": "preliminary",
                                                 "interim_cutoff_date": "2025-06-30"})
    assert ok.status_code == 200, ok.text
    assert await _stored(db, YEAR_ONLY) == ("preliminary", date(2025, 6, 30))


async def test_unchanged_values_are_not_a_change(client):
    first = await client.put(_url(), json={"current_audit_phase": "preliminary", "interim_cutoff_date": "2025-06-30"})
    again = await client.put(_url(), json={"current_audit_phase": "preliminary", "interim_cutoff_date": "2025-06-30"})
    back = await client.put(_url(), json={"current_audit_phase": "final", "interim_cutoff_date": "2025-06-30"})
    assert (first.json()["changed"], again.json()["changed"], back.json()["changed"]) == (True, False, True)
    assert back.json()["current_audit_phase"] == "final" and back.json()["interim_cutoff_date"] == "2025-06-30"


async def test_archived_project_is_read_only(client, db):
    resp = await client.put(_url(ARCHIVED), json={"current_audit_phase": "preliminary"})
    assert resp.status_code == 423, resp.text
    assert (await client.get(_url(ARCHIVED))).json()["can_edit"] is False
    assert await _stored(db, ARCHIVED) == ("final", None)


async def test_project_detail_carries_phase_fields(db):
    from app.routers.project_wizard import _to_project_response

    project = await db.get(Project, PROJECT)
    project.current_audit_phase, project.interim_cutoff_date = "preliminary", date(2025, 8, 31)
    out = _to_project_response(project)
    assert (out.current_audit_phase, out.interim_cutoff_date) == ("preliminary", date(2025, 8, 31))


async def test_attach_without_phase_takes_project_phase(client, db):
    await client.put(_url(), json={"current_audit_phase": "preliminary"})
    resp = await client.post(f"/api/projects/{PROJECT}/ledger/sample-voucher",
                             json={"year": YEAR, "voucher_no": "0007"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["phase"] == "preliminary"
    explicit = await client.post(f"/api/projects/{PROJECT}/ledger/sample-voucher",
                                 json={"year": YEAR, "voucher_no": "0007", "working_paper_id": str(uuid.uuid4()),
                                       "phase": "final"})
    assert explicit.json()["phase"] == "final"
    db.expire_all()
    rows = (await db.execute(sa.select(SampledVoucher.phase).order_by(SampledVoucher.created_at))).scalars().all()
    assert sorted(rows) == ["final", "preliminary"]


class TestVoucherExtractPhase:
    """抽凭请求没给阶段 → 按项目阶段（收集器与快照都用它）；给非法阶段 → 422。"""

    async def _post(self, body: dict, project_phase: str = "preliminary"):
        from unittest.mock import AsyncMock, MagicMock, patch

        from httpx import ASGITransport, AsyncClient

        from app.services.sampling_population_reconcile import PopulationReconcileFacts
        from app.services.voucher_sampling_exclusion import SamplingExclusions
        from tests.test_voucher_sampling_integration import _make_app, _make_ledger_rows, _make_stats

        app, _ = _make_app()
        population = _make_ledger_rows(5)
        with patch("app.routers.voucher_sampling._authorize_and_validate_extract", new=AsyncMock(return_value=None)), \
                patch("app.routers.voucher_sampling.resolve_population_reconcile",
                      new=AsyncMock(return_value=PopulationReconcileFacts(available=False))), \
                patch("app.routers.voucher_sampling.project_phase",
                      new=AsyncMock(return_value=project_phase)) as phase_of, \
                patch("app.routers.voucher_sampling.resolve_final_population", new=AsyncMock(return_value=None)), \
                patch("app.routers.voucher_sampling.collect_exclusions",
                      new=AsyncMock(return_value=SamplingExclusions())) as collect, \
                patch("app.routers.voucher_sampling.LedgerSamplingService") as svc:
            svc.build_ledger_query = AsyncMock(return_value=MagicMock())
            svc.execute_with_stats = AsyncMock(return_value=(population, _make_stats(population)))
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(f"/api/projects/{uuid.uuid4()}/sampling/voucher-extract", json=body)
        return resp, phase_of, collect

    @staticmethod
    def _body(**over) -> dict:
        from tests.test_voucher_sampling_integration import _make_extract_request

        body = _make_extract_request()
        body.pop("phase", None)
        body.update(over)
        return body

    async def test_missing_phase_uses_project_phase(self):
        resp, phase_of, collect = await self._post(self._body(), project_phase="preliminary")
        assert resp.status_code == 200, resp.text
        assert phase_of.await_count == 1 and collect.await_args.kwargs["phase"] == "preliminary"

    async def test_explicit_phase_wins(self):
        resp, phase_of, collect = await self._post(self._body(phase="final"), project_phase="preliminary")
        assert resp.status_code == 200, resp.text
        assert phase_of.await_count == 0 and collect.await_args.kwargs["phase"] == "final"

    @pytest.mark.parametrize("bad", ["current", "post", "interim", ""])
    async def test_illegal_phase_is_422(self, bad):
        resp, _, collect = await self._post(self._body(phase=bad))
        assert resp.status_code == 422, resp.text
        assert collect.await_count == 0
