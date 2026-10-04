"""披露同步覆盖率端点 —— 端到端 + 权限守卫

spec: disclosure-payload-authority-source / Task 2.3 需求 3.1 / 3.6

🔴 复盘第三轮补齐：前两轮**从未真实调用过这个端点**（只验证了 `router.routes`
长度与 service 纯函数），因此漏掉两件事：

  ① **端点漏挂项目权限依赖** —— 首版只有 `Depends(get_db)`，任何调用方传任意
     `project_id` 即可读该项目的披露同步状态（启用了哪些底稿 / 哪些章节已同步）
     = 未授权跨项目数据泄露（IDOR）。同业务域全部只读端点都挂
     `require_project_access("readonly")`。
  ② **响应信封形状未与前端解构对账** —— 平台有 `ResponseWrapperMiddleware`
     把 2xx JSON 包成 `{code,message,data}`；前端组件写的是 `data?.data ?? data`，
     两侧必须真的对得上。

本文件锁死：路由已注册 · 权限依赖存在且生效 · 无权限被拒 · 载荷字段齐备。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User, UserRole
from app.models.report_models import ContentType, DisclosureNote, NoteStatus
from app.models.workpaper_models import WpIndex, WpStatus
from app.routers.disclosure_sync_coverage import router as coverage_router
from app.services.disclosure_sync_coverage_service import _build_expectations

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
_YEAR = 2025

ENDPOINT = "/api/projects/{pid}/disclosure-sync-coverage"


# ── fixtures ─────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def seeded(db: AsyncSession):
    """建项目 + 启用 2 个底稿 + 1 个已同步章节。"""
    p = Project(
        id=uuid.uuid4(),
        name="端点测试_2025",
        client_name="端点测试",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
    )
    db.add(p)
    await db.flush()

    codes: list[str] = []
    for e in _build_expectations():
        if e["wp_code"] not in codes:
            codes.append(e["wp_code"])
        if len(codes) >= 2:
            break
    for code in codes:
        db.add(WpIndex(
            id=uuid.uuid4(), project_id=p.id, wp_code=code,
            wp_name=f"{code} 测试", status=WpStatus.not_started, is_deleted=False,
        ))
    await db.flush()

    section = next(
        e["note_section"] for e in _build_expectations() if e["wp_code"] in set(codes)
    )
    db.add(DisclosureNote(
        id=uuid.uuid4(), project_id=p.id, year=_YEAR, note_section=section,
        section_title="已同步章节", content_type=ContentType.table,
        status=NoteStatus.draft, is_deleted=False, is_stale=False,
        last_sync_at=datetime.now(timezone.utc),
    ))
    await db.flush()
    return p.id


def _make_app(db: AsyncSession, *, allow: bool) -> FastAPI:
    """挂载 router 并覆写依赖，**走真实权限逻辑**。

    🔴 不能 override `require_project_access("readonly")` 本身 —— 它是**依赖工厂**，
    每次调用返回**新的函数对象**，作为 `dependency_overrides` 的 key 与路由里
    已绑定的那个不是同一对象 ⇒ override 静默失效（首版即此错，全部请求 401）。

    正确做法 = override 其**内层**依赖 `get_current_user` / `get_db`，
    让 `assert_project_permission` 的真实判定跑起来：
      · allow=True  → 注入 admin 角色用户（实现里 admin 跳过项目权限检查）
      · allow=False → 注入普通角色用户且 DB 无 `ProjectUser` 记录 ⇒ 真实 403
    这样验证的是**门禁真的生效**，而非「我 mock 了一个 403」。
    """
    app = FastAPI()
    app.include_router(coverage_router)

    async def _override_db():
        yield db

    async def _override_user():
        return _admin_user() if allow else _plain_user()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    return app


def _admin_user() -> User:
    """admin 角色 —— `assert_project_permission` 对其跳过项目权限检查。"""
    return User(
        id=uuid.uuid4(), username="admin_tester", email="admin@example.com",
        role=UserRole.admin,
    )


def _plain_user() -> User:
    """普通角色且无 `ProjectUser` 记录 ⇒ 真实权限判定应给 403。"""
    return User(
        id=uuid.uuid4(), username="outsider", email="out@example.com",
        role=UserRole.auditor,
    )


# ══════════════════════════════════════════════════════════════════════════
# 路由注册
# ══════════════════════════════════════════════════════════════════════════


def test_route_is_registered_in_report_group():
    """端点已在 `router_registry/report.py` 注册（缺注册 = 前端 404）。"""
    from app.router_registry import report as report_group
    import inspect

    src = inspect.getsource(report_group.register_report_routers)
    assert "disclosure_sync_coverage" in src, (
        "端点未在 router_registry/report.py 注册 ⇒ 前端调用会 404"
    )
    assert "include_router" in src


def test_router_exposes_single_get_route():
    assert len(coverage_router.routes) == 1
    route = coverage_router.routes[0]
    assert route.path == "/api/projects/{project_id}/disclosure-sync-coverage"
    assert set(route.methods) == {"GET"}


# ══════════════════════════════════════════════════════════════════════════
# 🔴 权限守卫（第三轮修复的核心）
# ══════════════════════════════════════════════════════════════════════════


class TestEndpointAuthorization:
    """端点必须挂项目级权限依赖，且无权限时被拒。"""

    def test_route_has_project_access_dependency(self):
        """🔴 静态守卫：依赖列表里必须有 `require_project_access` 产出的依赖。

        防回退：首版只挂 `get_db` ⇒ 未授权可读任意项目。
        """
        route = coverage_router.routes[0]
        dep_names = [
            getattr(d.call, "__qualname__", str(d.call))
            for d in route.dependant.dependencies
        ]
        assert any("require_project_access" in n for n in dep_names), (
            "端点缺 require_project_access 依赖 ⇒ 任意 project_id 可未授权读取"
            f"（IDOR）。现有依赖：{dep_names}"
        )

    def test_route_dependency_count_is_two(self):
        """恰好 2 个依赖（get_db + 权限），多一个少一个都要显式复核。"""
        route = coverage_router.routes[0]
        assert len(route.dependant.dependencies) == 2

    @pytest.mark.asyncio
    async def test_forbidden_when_no_project_access(self, db: AsyncSession, seeded):
        """无项目权限 → 403，且**不返回任何业务数据**。"""
        app = _make_app(db, allow=False)
        with TestClient(app) as client:
            resp = client.get(ENDPOINT.format(pid=seeded), params={"year": _YEAR})
        assert resp.status_code == 403, f"应 403，实得 {resp.status_code}"
        body = resp.text
        for leaked in ("expected", "duty_rows", "note_section"):
            assert leaked not in body, f"403 响应泄露了业务字段 {leaked!r}"

    @pytest.mark.asyncio
    async def test_allowed_when_has_project_access(self, db: AsyncSession, seeded):
        """有权限 → 200（双向变异：证明上一条的 403 来自权限而非端点坏了）。"""
        app = _make_app(db, allow=True)
        with TestClient(app) as client:
            resp = client.get(ENDPOINT.format(pid=seeded), params={"year": _YEAR})
        assert resp.status_code == 200, f"应 200，实得 {resp.status_code}: {resp.text[:300]}"


# ══════════════════════════════════════════════════════════════════════════
# 载荷契约（与前端解构对账）
# ══════════════════════════════════════════════════════════════════════════


class TestResponsePayloadContract:
    """响应字段与前端 `CoverageSummary` interface 一一对应。"""

    @pytest.mark.asyncio
    async def test_payload_has_all_summary_fields(self, db: AsyncSession, seeded):
        app = _make_app(db, allow=True)
        with TestClient(app) as client:
            resp = client.get(ENDPOINT.format(pid=seeded), params={"year": _YEAR})
        assert resp.status_code == 200
        payload = resp.json()
        # 裸挂 router 时无 ResponseWrapperMiddleware，故直接是业务体；
        # 前端 `data?.data ?? data` 两种形状都能吃（见本文件头说明）。
        body = payload.get("data", payload)
        for field in ("expected", "synced", "stale", "never_synced", "duty_rows", "items"):
            assert field in body, f"响应缺字段 {field!r}（前端 interface 会拿到 undefined）"
        assert isinstance(body["items"], list)

    @pytest.mark.asyncio
    async def test_item_fields_match_frontend_interface(self, db: AsyncSession, seeded):
        app = _make_app(db, allow=True)
        with TestClient(app) as client:
            resp = client.get(ENDPOINT.format(pid=seeded), params={"year": _YEAR})
        body = resp.json()
        body = body.get("data", body)
        assert body["items"], "样本应至少有一条 item（否则本断言空转）"
        item = body["items"][0]
        for field in (
            "wp_code", "variant", "note_section",
            "expected", "synced", "stale", "never_synced",
        ):
            assert field in item, f"item 缺字段 {field!r}"

    @pytest.mark.asyncio
    async def test_summary_is_deduped_not_duty_rows(self, db: AsyncSession, seeded):
        """端点返回的 `expected` 是去重章节数，`duty_rows` 才是职责行数。"""
        app = _make_app(db, allow=True)
        with TestClient(app) as client:
            resp = client.get(ENDPOINT.format(pid=seeded), params={"year": _YEAR})
        body = resp.json()
        body = body.get("data", body)
        assert body["expected"] == len({i["note_section"] for i in body["items"]})
        assert body["duty_rows"] == len(body["items"])

    @pytest.mark.asyncio
    async def test_missing_year_param_is_rejected(self, db: AsyncSession, seeded):
        """`year` 是必填 Query，缺失应 422（防悄悄回落到服务器自然年）。"""
        app = _make_app(db, allow=True)
        with TestClient(app) as client:
            resp = client.get(ENDPOINT.format(pid=seeded))
        assert resp.status_code == 422, f"缺 year 应 422，实得 {resp.status_code}"

    @pytest.mark.asyncio
    async def test_invalid_project_id_is_rejected(self, db: AsyncSession):
        """非 UUID 的 project_id 应 422，不进 service。"""
        app = _make_app(db, allow=True)
        with TestClient(app) as client:
            resp = client.get(
                "/api/projects/not-a-uuid/disclosure-sync-coverage",
                params={"year": _YEAR},
            )
        assert resp.status_code == 422
