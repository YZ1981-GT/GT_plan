"""调整分录复核 / 撤回复核端点权限守卫 — TestClient 真请求

spec: chain-closure-phase3-push-rollout / Task 4（需求 3.3 / ADR-P3-007）

验证：
  - ``/review`` 和 ``/revoke-review`` 端点使用 ``require_project_permission("adjustment:review")``
  - 经理 / 合伙人（含 admin）→ 200 或业务级错误（非 403）
  - 审计助理 / 质控 / 只读成员 / 非成员 → 403
  - ``/my-permissions`` 返回的权限与端点鉴权一致（同源）

实现方式：
  - 不 override 依赖工厂 ``require_project_permission`` 本身（每次返回新函数，
    ``dependency_overrides`` 的 key 匹配不上会静默失效）
  - override 其**内层**依赖 ``get_current_user`` 和 ``get_db``，让真实鉴权跑起来
  - 用 SQLite 内存库种入 User / Project / ProjectUser / StaffMember / ProjectAssignment
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import (
    Base,
    PermissionLevel,
    ProjectUserRole,
    UserRole,
)
from app.models.core import (
    Project,
    ProjectStatus,
    ProjectType,
    ProjectUser,
    User,
)
from app.models.staff_models import ProjectAssignment, StaffMember
from app.routers.adjustments import router as adj_router

# SQLite 不认 JSONB — 降级
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

# ── 常量 ────────────────────────────────────────────────────────────────

_PROJECT_ID = uuid.uuid4()
_ENTRY_GROUP_ID = uuid.uuid4()
_REVIEW_URL = f"/api/projects/{_PROJECT_ID}/adjustments/{_ENTRY_GROUP_ID}/review"
_REVOKE_URL = f"/api/projects/{_PROJECT_ID}/adjustments/{_ENTRY_GROUP_ID}/revoke-review"
_REVIEW_BODY = {"status": "approved"}


# ── 引擎与 fixture ──────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db() -> AsyncSession:
    """每个测试独立的 SQLite 内存库，避免跨测试 FK 冲突。"""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    @event.listens_for(eng.sync_engine, "connect")
    def _enable_fk(dbapi_conn, _rec):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await eng.dispose()


async def _seed_project(db: AsyncSession) -> Project:
    """种入项目。"""
    project = Project(
        id=_PROJECT_ID,
        name="权限测试_2025",
        client_name="权限测试",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
    )
    db.add(project)
    await db.flush()
    return project


async def _seed_user(
    db: AsyncSession,
    *,
    username: str,
    system_role: UserRole,
) -> User:
    """种入用户。"""
    user = User(
        id=uuid.uuid4(),
        username=username,
        email=f"{username}@test.com",
        hashed_password="x",
        role=system_role,
    )
    db.add(user)
    await db.flush()
    return user


async def _assign_to_project(
    db: AsyncSession,
    user: User,
    project: Project,
    *,
    project_user_role: ProjectUserRole,
    permission_level: PermissionLevel,
    assignment_role: str,
) -> None:
    """给用户在项目中分配 ProjectUser + StaffMember + ProjectAssignment。

    三层都要种才能让 ``require_project_permission`` 完整走通：
      1) ``ProjectUser`` —— ``assert_project_permission`` 查 permission_level
      2) ``StaffMember`` + ``ProjectAssignment`` —— ``resolve_project_permissions`` 查角色合并权限
    """
    db.add(ProjectUser(
        id=uuid.uuid4(),
        project_id=project.id,
        user_id=user.id,
        role=project_user_role,
        permission_level=permission_level,
    ))
    staff = StaffMember(
        id=uuid.uuid4(),
        user_id=user.id,
        name=user.username,
    )
    db.add(staff)
    await db.flush()
    db.add(ProjectAssignment(
        id=uuid.uuid4(),
        project_id=project.id,
        staff_id=staff.id,
        role=assignment_role,
        assigned_at=date.today(),
    ))
    await db.flush()


def _make_app(db: AsyncSession, user: User) -> FastAPI:
    """挂载 adjustment router 并覆写内层依赖。"""
    app = FastAPI()
    app.include_router(adj_router)

    async def _override_db():
        yield db

    async def _override_user():
        return user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    return app


# ══════════════════════════════════════════════════════════════════════════
# 权限 200 — 有 adjustment:review 权限
# ══════════════════════════════════════════════════════════════════════════


class TestReviewPermissionAllowed:
    """经理 / 合伙人 / admin 调 /review 和 /revoke-review 不被 403。

    注意：真正的 200 需要库里有分录数据（本测试不种分录），所以期望
    「非 403」即可（可能是 400 / 500 业务级错误）—— 重点是权限层放行。
    """

    @pytest.mark.asyncio
    async def test_manager_can_review(self, db: AsyncSession):
        """现场经理（project_role=manager）→ 有 adjustment:review → 非 403"""
        project = await _seed_project(db)
        user = await _seed_user(db, username="mgr", system_role=UserRole.auditor)
        await _assign_to_project(
            db, user, project,
            project_user_role=ProjectUserRole.manager,
            permission_level=PermissionLevel.review,
            assignment_role="manager",
        )
        await db.commit()

        app = _make_app(db, user)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(_REVIEW_URL, json=_REVIEW_BODY)
        assert resp.status_code != 403, f"经理应有 adjustment:review 权限，却被 403: {resp.text[:300]}"

    @pytest.mark.asyncio
    async def test_manager_can_revoke(self, db: AsyncSession):
        """现场经理 → /revoke-review → 非 403"""
        project = await _seed_project(db)
        user = await _seed_user(db, username="mgr2", system_role=UserRole.auditor)
        await _assign_to_project(
            db, user, project,
            project_user_role=ProjectUserRole.manager,
            permission_level=PermissionLevel.review,
            assignment_role="manager",
        )
        await db.commit()

        app = _make_app(db, user)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(_REVOKE_URL)
        assert resp.status_code != 403, f"经理应有 adjustment:review 权限，却被 403: {resp.text[:300]}"

    @pytest.mark.asyncio
    async def test_signing_partner_can_review(self, db: AsyncSession):
        """签字合伙人（project_role=signing_partner）→ 有 adjustment:review → 非 403"""
        project = await _seed_project(db)
        user = await _seed_user(db, username="partner", system_role=UserRole.partner)
        await _assign_to_project(
            db, user, project,
            project_user_role=ProjectUserRole.partner,
            permission_level=PermissionLevel.review,
            assignment_role="signing_partner",
        )
        await db.commit()

        app = _make_app(db, user)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(_REVIEW_URL, json=_REVIEW_BODY)
        assert resp.status_code != 403, f"签字合伙人应有 adjustment:review 权限，却被 403: {resp.text[:300]}"

    @pytest.mark.asyncio
    async def test_admin_can_review(self, db: AsyncSession):
        """admin 跳过所有权限检查 → 非 403"""
        await _seed_project(db)
        user = await _seed_user(db, username="admin", system_role=UserRole.admin)
        # admin 不需要 ProjectUser/StaffMember/ProjectAssignment
        await db.commit()

        app = _make_app(db, user)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(_REVIEW_URL, json=_REVIEW_BODY)
        assert resp.status_code != 403, f"admin 应跳过权限检查，却被 403: {resp.text[:300]}"

    @pytest.mark.asyncio
    async def test_admin_can_revoke(self, db: AsyncSession):
        """admin → /revoke-review → 非 403"""
        await _seed_project(db)
        user = await _seed_user(db, username="admin2", system_role=UserRole.admin)
        await db.commit()

        app = _make_app(db, user)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(_REVOKE_URL)
        assert resp.status_code != 403, f"admin 应跳过权限检查，却被 403: {resp.text[:300]}"


# ══════════════════════════════════════════════════════════════════════════
# 权限 403 — 无 adjustment:review 权限
# ══════════════════════════════════════════════════════════════════════════


class TestReviewPermissionDenied:
    """审计助理 / 质控 / 只读成员 / 非成员 → 403。"""

    @pytest.mark.asyncio
    async def test_auditor_cannot_review(self, db: AsyncSession):
        """审计助理（project_role=auditor）→ 无 adjustment:review → 403

        S10 修复验证：旧代码用 ``require_project_access("review")``，
        审计助理的 ``permission_level=edit(3)`` > ``review(2)`` 所以能通过；
        改用 ``require_project_permission("adjustment:review")`` 后正确拒绝。
        """
        project = await _seed_project(db)
        user = await _seed_user(db, username="auditor", system_role=UserRole.auditor)
        await _assign_to_project(
            db, user, project,
            project_user_role=ProjectUserRole.auditor,
            permission_level=PermissionLevel.edit,  # 比 review 高，但无 adjustment:review
            assignment_role="auditor",
        )
        await db.commit()

        app = _make_app(db, user)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(_REVIEW_URL, json=_REVIEW_BODY)
        assert resp.status_code == 403, (
            f"审计助理不应有 adjustment:review 权限（S10 修复），"
            f"实得 {resp.status_code}: {resp.text[:300]}"
        )

    @pytest.mark.asyncio
    async def test_auditor_cannot_revoke(self, db: AsyncSession):
        """审计助理 → /revoke-review → 403"""
        project = await _seed_project(db)
        user = await _seed_user(db, username="auditor2", system_role=UserRole.auditor)
        await _assign_to_project(
            db, user, project,
            project_user_role=ProjectUserRole.auditor,
            permission_level=PermissionLevel.edit,
            assignment_role="auditor",
        )
        await db.commit()

        app = _make_app(db, user)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(_REVOKE_URL)
        assert resp.status_code == 403, (
            f"审计助理不应有 adjustment:review 权限，实得 {resp.status_code}: {resp.text[:300]}"
        )

    @pytest.mark.asyncio
    async def test_qc_cannot_review(self, db: AsyncSession):
        """质控人员（project_role=qc）→ 无 adjustment:review → 403"""
        project = await _seed_project(db)
        user = await _seed_user(db, username="qc_user", system_role=UserRole.qc)
        await _assign_to_project(
            db, user, project,
            project_user_role=ProjectUserRole.qc,
            permission_level=PermissionLevel.review,
            assignment_role="qc",
        )
        await db.commit()

        app = _make_app(db, user)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(_REVIEW_URL, json=_REVIEW_BODY)
        assert resp.status_code == 403, (
            f"质控不应有 adjustment:review 权限，实得 {resp.status_code}: {resp.text[:300]}"
        )

    @pytest.mark.asyncio
    async def test_readonly_cannot_review(self, db: AsyncSession):
        """只读成员 → 第一层即拒（permission_level=readonly < review）→ 403"""
        project = await _seed_project(db)
        user = await _seed_user(db, username="reader", system_role=UserRole.readonly)
        await _assign_to_project(
            db, user, project,
            project_user_role=ProjectUserRole.readonly,
            permission_level=PermissionLevel.readonly,
            assignment_role="readonly",
        )
        await db.commit()

        app = _make_app(db, user)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(_REVIEW_URL, json=_REVIEW_BODY)
        assert resp.status_code == 403, (
            f"只读成员不应有 adjustment:review 权限，实得 {resp.status_code}: {resp.text[:300]}"
        )

    @pytest.mark.asyncio
    async def test_nonmember_cannot_review(self, db: AsyncSession):
        """非成员（无 ProjectUser 记录）→ 第一层即拒 → 403"""
        await _seed_project(db)
        user = await _seed_user(db, username="outsider", system_role=UserRole.auditor)
        # 不创建 ProjectUser / StaffMember / ProjectAssignment
        await db.commit()

        app = _make_app(db, user)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(_REVIEW_URL, json=_REVIEW_BODY)
        assert resp.status_code == 403, (
            f"非成员不应通过权限检查，实得 {resp.status_code}: {resp.text[:300]}"
        )

    @pytest.mark.asyncio
    async def test_nonmember_cannot_revoke(self, db: AsyncSession):
        """非成员 → /revoke-review → 403"""
        await _seed_project(db)
        user = await _seed_user(db, username="outsider2", system_role=UserRole.auditor)
        await db.commit()

        app = _make_app(db, user)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(_REVOKE_URL)
        assert resp.status_code == 403, (
            f"非成员不应通过权限检查，实得 {resp.status_code}: {resp.text[:300]}"
        )

    @pytest.mark.asyncio
    async def test_eqcr_cannot_review(self, db: AsyncSession):
        """EQCR 技术复核人 → 无 adjustment:review → 403"""
        project = await _seed_project(db)
        user = await _seed_user(db, username="eqcr_user", system_role=UserRole.eqcr)
        await _assign_to_project(
            db, user, project,
            project_user_role=ProjectUserRole.eqcr,
            permission_level=PermissionLevel.review,
            assignment_role="eqcr",
        )
        await db.commit()

        app = _make_app(db, user)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(_REVIEW_URL, json=_REVIEW_BODY)
        assert resp.status_code == 403, (
            f"EQCR 不应有 adjustment:review 权限，实得 {resp.status_code}: {resp.text[:300]}"
        )


# ══════════════════════════════════════════════════════════════════════════
# 同源验证：/my-permissions 与端点鉴权一致
# ══════════════════════════════════════════════════════════════════════════


class TestPermissionConsistency:
    """/my-permissions 返回的权限集与端点实际鉴权一致。"""

    @pytest.mark.asyncio
    async def test_manager_my_permissions_includes_adjustment_review(self, db: AsyncSession):
        """经理通过 resolve_project_permissions 获得 adjustment:review。"""
        from app.services.project_permissions import resolve_project_permissions

        project = await _seed_project(db)
        user = await _seed_user(db, username="mgr_perm", system_role=UserRole.auditor)
        await _assign_to_project(
            db, user, project,
            project_user_role=ProjectUserRole.manager,
            permission_level=PermissionLevel.review,
            assignment_role="manager",
        )
        await db.flush()

        perms = await resolve_project_permissions(db, user, project.id)
        assert "adjustment:review" in perms, (
            f"经理应有 adjustment:review；实际权限: {sorted(perms)}"
        )

    @pytest.mark.asyncio
    async def test_auditor_my_permissions_excludes_adjustment_review(self, db: AsyncSession):
        """审计助理不应在 resolve_project_permissions 中获得 adjustment:review。"""
        from app.services.project_permissions import resolve_project_permissions

        project = await _seed_project(db)
        user = await _seed_user(db, username="aud_perm", system_role=UserRole.auditor)
        await _assign_to_project(
            db, user, project,
            project_user_role=ProjectUserRole.auditor,
            permission_level=PermissionLevel.edit,
            assignment_role="auditor",
        )
        await db.flush()

        perms = await resolve_project_permissions(db, user, project.id)
        assert "adjustment:review" not in perms, (
            f"审计助理不应有 adjustment:review；实际权限: {sorted(perms)}"
        )

    @pytest.mark.asyncio
    async def test_qc_my_permissions_excludes_adjustment_review(self, db: AsyncSession):
        """质控不应有 adjustment:review。"""
        from app.services.project_permissions import resolve_project_permissions

        project = await _seed_project(db)
        user = await _seed_user(db, username="qc_perm", system_role=UserRole.qc)
        await _assign_to_project(
            db, user, project,
            project_user_role=ProjectUserRole.qc,
            permission_level=PermissionLevel.review,
            assignment_role="qc",
        )
        await db.flush()

        perms = await resolve_project_permissions(db, user, project.id)
        assert "adjustment:review" not in perms, (
            f"质控不应有 adjustment:review；实际权限: {sorted(perms)}"
        )

    @pytest.mark.asyncio
    async def test_admin_gets_all_permissions(self, db: AsyncSession):
        """admin 获得 ALL_PERMISSIONS（含 adjustment:review）。"""
        from app.services.project_permissions import resolve_project_permissions

        await _seed_project(db)
        user = await _seed_user(db, username="admin_perm", system_role=UserRole.admin)
        await db.flush()

        perms = await resolve_project_permissions(db, user, _PROJECT_ID)
        assert "adjustment:review" in perms, (
            f"admin 应有 adjustment:review；实际权限: {sorted(perms)}"
        )


# ══════════════════════════════════════════════════════════════════════════
# 变异守卫：去掉 require_project_permission 会降级
# ══════════════════════════════════════════════════════════════════════════


class TestPermissionGuardPresence:
    """静态守卫：端点依赖里必须有 require_project_permission。"""

    def test_review_endpoint_has_permission_dependency(self):
        """POST /{entry_group_id}/review 依赖链必须包含 require_project_permission。"""
        route = _find_route("/{entry_group_id}/review", "POST")
        dep_names = _extract_dependency_names(route)
        assert "require_project_permission" in dep_names, (
            f"/review 端点必须使用 require_project_permission，"
            f"当前依赖: {dep_names}"
        )

    def test_revoke_endpoint_has_permission_dependency(self):
        """POST /{entry_group_id}/revoke-review 依赖链必须包含 require_project_permission。"""
        route = _find_route("/{entry_group_id}/revoke-review", "POST")
        dep_names = _extract_dependency_names(route)
        assert "require_project_permission" in dep_names, (
            f"/revoke-review 端点必须使用 require_project_permission，"
            f"当前依赖: {dep_names}"
        )


# ── helpers ──────────────────────────────────────────────────────────────


def _find_route(path_suffix: str, method: str):
    """在 adj_router 中找到匹配的路由。"""
    for route in adj_router.routes:
        if hasattr(route, "path") and route.path.endswith(path_suffix):
            if method in getattr(route, "methods", set()):
                return route
    raise AssertionError(f"路由 {method} ...{path_suffix} 不存在")


def _extract_dependency_names(route) -> set[str]:
    """从路由的 dependant 树中提取所有依赖名。"""
    names: set[str] = set()
    if not hasattr(route, "dependant"):
        return names
    for dep in route.dependant.dependencies:
        call = dep.call
        # require_project_permission 是工厂的返回值（闭包），
        # 其 __qualname__ 包含 "require_project_permission"
        qualname = getattr(call, "__qualname__", "")
        if "require_project_permission" in qualname:
            names.add("require_project_permission")
        name = getattr(call, "__name__", "")
        if name:
            names.add(name)
    return names
