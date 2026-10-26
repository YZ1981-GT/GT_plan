"""拖拽改上级下沉服务 ``group_links.reparent_project`` 与路由鉴权（spec consol-autotree-linkage-closure R3）。

真 SQLite + 真 ORM 行 + 真 service；端点真发请求（ASGITransport），鉴权走真实实现（只替换当前用户与会话）。

- 同企业同年度合并 / 单户两口径同写：上级代码、上级名称（新上级本年度项目的企业名称，单户优先；
  未建项用请求里的名称）、与上级关系、控制方为空时按新上级补齐，向导回填数据一起写；
- 返回同步了哪些项目与字段；
- 🔴 旧路由只要求登录（任意登录用户可改任意项目的上级）且从不写上级名称：改为本项目 edit 级成员或管理员；
  层级变更历史同步收紧为本项目成员（只读即可）。
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401  注册全部模型 + SQLite 方言补丁
from app.core.database import get_db
from app.deps import get_current_user
from app.models.audit_platform_schemas import BasicInfoSchema
from app.models.base import Base, PermissionLevel, UserRole
from app.models.core import Project, ProjectUser, User
from app.services import project_wizard_service as svc

G = "91110000100000000R"   # 集团（最终控制方）
P = "911100002000000005"   # 新上级（乙控股）
A = "91110000300000000G"   # 被拖动的子公司
X = "911100005000000007"   # 本年度未建项的企业
Y = 2025

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


def _info(code: str, name: str, scope: str = "standalone", **kw) -> BasicInfoSchema:
    return BasicInfoSchema(
        client_name=name, audit_year=Y, project_type="annual", accounting_standard="enterprise",
        company_code=code, short_name=name[:20], report_scope=scope, **kw,
    )


async def _fresh(db: AsyncSession, pid: uuid.UUID) -> Project:
    db.expire_all()
    return await db.get(Project, pid)


async def _seed(db: AsyncSession) -> dict[str, uuid.UUID]:
    """G 合并（控制方 G）；P 合并 + 单户（上级 G、控制方 G，单户名称与合并项目不同）；A 合并 + 单户（上级 X 未建项，控制方空）。"""
    ids = {"G": (await svc.create_project(_info(G, "某集团", "consolidated", ultimate_company_code=G), db)).id}
    ids["P_c"] = (await svc.create_project(_info(
        P, "乙控股集团", "consolidated", parent_company_code=G, ultimate_company_code=G,
        ultimate_company_name="某集团"), db)).id
    ids["P_s"] = (await svc.create_project(_info(
        P, "乙控股", parent_company_code=G, ultimate_company_code=G, ultimate_company_name="某集团"), db)).id
    ids["A_c"] = (await svc.create_project(_info(A, "甲公司", "consolidated", parent_company_code=X), db)).id
    ids["A_s"] = (await svc.create_project(_info(A, "甲公司", parent_company_code=X), db)).id
    await db.commit()
    for key in ("P_c", "P_s"):  # 建项时同企业两口径名称会被对齐：这里刻意改开，验证「单户优先」
        row = await db.get(Project, ids[key])
        row.client_name = "乙控股集团" if key == "P_c" else "乙控股"
    await db.commit()
    a_s = await _fresh(db, ids["A_s"])
    assert a_s.ultimate_company_code is None, "前提：被拖动企业的控制方为空"
    return ids


class TestReparentService:
    @pytest.mark.asyncio
    async def test_both_scopes_name_relation_ultimate_and_wizard(self, db):
        from app.services.group_links import reparent_project

        ids = await _seed(db)
        a_s = await db.get(Project, ids["A_s"])
        result = await reparent_project(db, a_s, P)
        await db.commit()
        assert result["parent_company_name"] == "乙控股", "上级名称取新上级本年度单户项目的企业名称"
        assert {s["id"] for s in result["synced"]} == {str(ids["A_s"]), str(ids["A_c"])}
        for s in result["synced"]:
            assert {"上级企业代码", "上级企业名称", "最终控制方代码"} <= set(s["fields"]), s
        assert any("最终控制方已按上级企业补齐" in n for n in result["notices"])
        for key in ("A_s", "A_c"):
            row = await _fresh(db, ids[key])
            assert (row.parent_company_code, row.parent_company_name, row.relation_to_parent) == (P, "乙控股", "subsidiary")
            assert (row.ultimate_company_code, row.ultimate_company_name) == (G, "某集团")
            data = row.wizard_state["steps"]["basic_info"]["data"]
            assert (data["parent_company_code"], data["parent_company_name"], data["ultimate_company_code"]) == (P, "乙控股", G)

    @pytest.mark.asyncio
    async def test_parent_not_created_uses_hint_or_explains(self, db):
        from app.services.group_links import reparent_project

        ids = await _seed(db)
        a_s = await db.get(Project, ids["A_s"])
        hinted = await reparent_project(db, a_s, X, name_hint="丙公司")
        assert hinted["parent_company_name"] == "丙公司" and not any("尚未建项" in n for n in hinted["notices"])
        bare = await reparent_project(db, a_s, X)
        assert bare["parent_company_name"] is None and any("本年度尚未建项" in n for n in bare["notices"])
        top = await reparent_project(db, a_s, None)
        assert top["parent_company_name"] is None and (await db.get(Project, ids["A_c"])).relation_to_parent is None


class _U:
    def __init__(self, role: UserRole):
        self.id = uuid.uuid4()
        self.username = f"u_{self.id.hex[:6]}"
        self.role = role
        self.is_active = True
        self.is_deleted = False


async def _member(db, project_id, level: PermissionLevel | None) -> _U:
    user = _U(UserRole.auditor)
    db.add(User(id=user.id, username=user.username, email=f"{user.id.hex[:8]}@t.local", hashed_password="x",
                role=user.role))
    if level is not None:
        db.add(ProjectUser(project_id=project_id, user_id=user.id, role="auditor", permission_level=level))
    await db.commit()
    return user


class TestEndpointAuth:
    @pytest.mark.asyncio
    async def test_edit_member_only_and_history_members(self, db):
        from app.routers.project_wizard import router

        ids = await _seed(db)
        app = FastAPI()
        app.include_router(router)
        current: dict[str, _U] = {}

        async def _db():
            yield db

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = lambda: current["u"]
        outsider = await _member(db, ids["A_s"], None)
        reader = await _member(db, ids["A_s"], PermissionLevel.readonly)
        editor = await _member(db, ids["A_s"], PermissionLevel.edit)
        url = f"/api/projects/{ids['A_s']}/parent-code"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            for user in (outsider, reader):
                current["u"] = user
                resp = await c.patch(url, json={"parent_company_code": P})
                assert resp.status_code == 403, f"🔴 旧路由只要求登录：{resp.status_code}"
            current["u"] = outsider
            assert (await c.get(f"/api/projects/{ids['A_s']}/parent-code-history")).status_code == 403
            current["u"] = reader
            assert (await c.get(f"/api/projects/{ids['A_s']}/parent-code-history")).status_code == 200
            current["u"] = editor
            ok = await c.patch(url, json={"parent_company_code": P})
            assert ok.status_code == 200, ok.text
            body = ok.json()
            assert body["parent_company_name"] == "乙控股" and len(body["synced"]) == 2
            current["u"] = _U(UserRole.admin)
            cycle = await c.patch(f"/api/projects/{ids['P_s']}/parent-code", json={"parent_company_code": A})
            assert cycle.status_code == 400 and "循环" in cycle.json()["detail"]
        assert (await _fresh(db, ids["A_c"])).parent_company_name == "乙控股", "两口径同写"
