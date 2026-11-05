"""报表相关端点补项目级鉴权（spec citar-cell-source-hover R7）：非成员 403、成员与 admin 放行。

只替换 ``get_current_user`` 与 ``get_db``；``require_project_access`` / ``assert_project_permission`` 真实执行。
「放行」只断言不是 403：报表未生成时穿透 / 导出按业务返回 404，生成报表按前置条件返回 400，都说明鉴权已通过。
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from app.core.database import get_db  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.models.base import Base, PermissionLevel  # noqa: E402
from app.models.core import Project, ProjectStatus, ProjectType, ProjectUser, ProjectUserRole, UserRole  # noqa: E402
from app.routers import report_export, report_related_workpapers, reports, wp_report_analysis  # noqa: E402

P = uuid.UUID("00000000-0000-0000-0000-00000000c801")
OTHER = uuid.UUID("00000000-0000-0000-0000-00000000c802")
MEMBER = uuid.UUID("00000000-0000-0000-0000-00000000c811")
STRANGER = uuid.UUID("00000000-0000-0000-0000-00000000c812")
YEAR = 2025


class _U:
    def __init__(self, uid: uuid.UUID, role: UserRole) -> None:
        self.id, self.role, self.username, self.is_active = uid, role, f"u{uid.hex[-3:]}", True


ACTORS = {"member": _U(MEMBER, UserRole.manager), "stranger": _U(STRANGER, UserRole.manager),
          "admin": _U(uuid.uuid4(), UserRole.admin)}


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        for pid in (P, OTHER):
            s.add(Project(id=pid, name=f"鉴权_{pid.hex[-3:]}", client_name="鉴权", project_type=ProjectType.annual,
                          status=ProjectStatus.execution, created_by=MEMBER))
        await s.flush()
        s.add(ProjectUser(project_id=P, user_id=MEMBER, role=ProjectUserRole.manager, permission_level=PermissionLevel.edit))
        await s.commit()
    current = {"actor": ACTORS["member"]}
    app = FastAPI()
    for r in (reports.router, reports.line_composition_router, report_export.router, report_related_workpapers.router,
              wp_report_analysis.router):
        app.include_router(r)

    async def _db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: current["actor"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c, lambda k: current.update(actor=ACTORS[k])
    await engine.dispose()


def _calls(pid: uuid.UUID):
    return [
        ("GET", f"/api/reports/{pid}/{YEAR}/balance_sheet", None),
        ("GET", f"/api/reports/{pid}/{YEAR}/balance_sheet/drilldown/BS-001", None),
        ("GET", f"/api/reports/{pid}/{YEAR}/balance_sheet/export-excel", None),
        ("GET", f"/api/reports/{pid}/{YEAR}/balance_sheet/BS-001/related-workpapers", None),
        ("POST", f"/api/projects/{pid}/reports/export-excel", {"year": YEAR}),
        ("POST", "/api/reports/generate", {"project_id": str(pid), "year": YEAR}),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("idx", range(6))
async def test_stranger_is_forbidden_member_and_admin_pass(client, idx):
    c, act = client
    method, url, body = _calls(P)[idx]
    act("stranger")
    r = await c.request(method, url, json=body)
    assert r.status_code == 403, (url, r.status_code, r.text)
    for who in ("member", "admin"):
        act(who)
        r = await c.request(method, url, json=body)
        assert r.status_code != 403, (who, url, r.status_code, r.text)


@pytest.mark.asyncio
async def test_generate_rejects_other_project_in_body(client):
    """经理系统角色本有 report:edit：原先只看系统角色，能给自己不在的项目生成报表并写库。"""
    c, act = client
    act("member")
    r = await c.post("/api/reports/generate", json={"project_id": str(OTHER), "year": YEAR})
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_opening_reconcile_checks_prior_project(client):
    c, act = client
    act("member")
    url = f"/api/workpapers/{P}/{YEAR}/opening-reconcile"
    r = await c.get(url, params={"prior_project_id": str(OTHER)})
    assert r.status_code == 403, r.text
    r = await c.get(url, params={"prior_project_id": str(P)})
    assert r.status_code != 403, r.text
