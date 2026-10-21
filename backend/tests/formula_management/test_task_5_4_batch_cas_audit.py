"""Task 5.4 · 批量单事务 + CAS + wp CRUD 写审计哈希链 —— formula-manager-closure

spec: formula-manager-closure / Task 5.4 / 需求 5.6·13.4 / design §5 步骤 5 · §8 错误处理

## 这个文件在干什么

Phase 5 的收尾加固。Task 5.1 坐实 IDOR、5.2/5.3 加固鉴权，本文件专测 5.4 的三件事：

  1. **批量保存**（`PUT /api/workpapers/{wp_id}/formulas/batch`）
     · 行数限额：空批 / 超 `_BATCH_MAX_ROWS` → 422（不写库）。
     · 单事务：批内任一行校验失败 → 整批 rollback、422，**不部分落库**。
  2. **CAS 乐观锁**（compare-and-swap 并发冲突检测）
     · 单条 / 批量带 `expected_version`，与库中既有行 `definition_version` 不一致
       → 409、**不覆盖**。
  3. **wp CRUD 审计哈希链**
     · 单条 save / delete、批量 save 后 `audit_log_entries` 有新条目，`user_id` =
       **真实操作人**（非写死全零）、`action_type='formula.changed'`、
       payload.module='workpaper'。

## 变异反证（memory 铁律㉒㉖：单向变异会把干净态判成缺陷，故每条配反向断言）

  · `TestMutationCASRemoved`：临时把 service 的 CAS 检查 no-op 掉（模拟「去掉 CAS」），
    断言并发冲突样本此时**不再 409**（坐实 409 确来自 CAS 而非他处）；反向断言未变异
    时版本一致的保存正常通过。

## 工装纪律（memory 教训㉕①）

🔴 禁覆盖 `require_project_access(...)` 工厂本身（返回新函数对象、key 对不上 → 静默
失效）。只 override 内层 `get_db` / `get_current_user`，让 `assert_project_permission`
的真实判定跑。ACNR 悬空引用校验（查多表）用 `validate_refs_via_acnr` patch 成 []
隔离——本文件测的是批量/CAS/审计机制，不是引用校验（引用校验另有专测）。
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.audit_log_models import AuditLogEntry
from app.models.base import Base, PermissionLevel, ProjectUserRole
from app.models.core import (
    Project,
    ProjectStatus,
    ProjectType,
    ProjectUser,
    User,
    UserRole,
)
from app.models.workpaper_models import (
    WorkingPaper,
    WpFileStatus,
    WpFormula,
    WpIndex,
    WpReviewStatus,
    WpSourceType,
    WpStatus,
)

# SQLite 无 JSONB / UUID 原生类型 —— 用 JSON / CHAR 渲染（与既有鉴权端点测试同款）。
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
_YEAR = 2025


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


class _Seed:
    def __init__(self) -> None:
        self.user_id: uuid.UUID
        self.project_id: uuid.UUID
        self.wp_id: uuid.UUID
        self.existing_formula_id: uuid.UUID


@pytest_asyncio.fixture
async def seed(db: AsyncSession) -> _Seed:
    s = _Seed()
    user = User(
        id=uuid.uuid4(), username="editor_u", email="e@example.com",
        hashed_password="x", role=UserRole.manager,
    )
    db.add(user)
    proj = Project(
        id=uuid.uuid4(), name="项目P_2025", client_name="客户P",
        project_type=ProjectType.annual, status=ProjectStatus.planning,
    )
    db.add(proj)
    await db.flush()
    # user 是项目 edit 成员 → assert_project_permission("edit") 真实放行。
    db.add(ProjectUser(
        id=uuid.uuid4(), project_id=proj.id, user_id=user.id,
        role=ProjectUserRole.manager, permission_level=PermissionLevel.edit,
    ))
    # 中性 wp_code "Z1"（非 E1 / 非 D-cycle）：surfaced/extraction 旁支短路，便于聚焦。
    wp_index = WpIndex(
        id=uuid.uuid4(), project_id=proj.id, wp_code="Z1", wp_name="Z1 中性底稿",
        status=WpStatus.not_started, is_deleted=False,
    )
    db.add(wp_index)
    await db.flush()
    wp = WorkingPaper(
        id=uuid.uuid4(), project_id=proj.id, wp_index_id=wp_index.id,
        file_path="/tmp/z1.xlsx", source_type=WpSourceType.template,
        status=WpFileStatus.draft, review_status=WpReviewStatus.not_submitted,
        is_deleted=False,
    )
    db.add(wp)
    await db.flush()
    # 一条既有公式（definition_version=1），供 CAS / update 审计对照。
    existing = WpFormula(
        id=uuid.uuid4(), project_id=proj.id, wp_id=wp.id,
        sheet_name="Z1-1", target_cell="B2", expression="1 + 1",
        category="auto_calc", description="既有公式", formula_type="auto_calc",
        definition_version=1, created_by=user.id,
    )
    db.add(existing)
    await db.flush()
    await db.commit()

    s.user_id, s.project_id, s.wp_id = user.id, proj.id, wp.id
    s.existing_formula_id = existing.id
    return s


def _make_app(db: AsyncSession, user: User) -> FastAPI:
    from app.routers import wp_formula as wp_formula_router

    app = FastAPI()
    app.include_router(wp_formula_router.router)

    async def _override_db():
        yield db

    async def _override_user():
        return user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    return app


async def _load_user(db: AsyncSession, uid: uuid.UUID) -> User:
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _audit_count(project_id: uuid.UUID) -> int:
    """统计该项目 wp_formula 审计条目数（独立 session，避免 expire 干扰）。"""
    async with async_sessionmaker(_engine, class_=AsyncSession,
                                  expire_on_commit=False)() as s:
        rows = (await s.execute(
            select(AuditLogEntry).where(
                AuditLogEntry.object_type == "wp_formula",
            )
        )).scalars().all()
        return len([r for r in rows
                    if (r.payload or {}).get("project_id") == str(project_id)])


# patch ACNR 悬空引用校验为通过（本文件不测引用校验）。
_NO_REF_ISSUES = patch(
    "app.services.wp_formula_service.validate_refs_via_acnr",
    new=AsyncMock(return_value=[]),
)


# ══════════════════════════════════════════════════════════════════════════
# 1. 批量：行数限额 + 单事务回滚一致
# ══════════════════════════════════════════════════════════════════════════


class TestBatchRowLimitAndSingleTransaction:

    @pytest.mark.asyncio
    async def test_batch_empty_rejected_422(self, db, seed):
        user = await _load_user(db, seed.user_id)
        app = _make_app(db, user)
        with _NO_REF_ISSUES, TestClient(app, raise_server_exceptions=False) as c:
            resp = c.put(f"/api/workpapers/{seed.wp_id}/formulas/batch",
                         json={"year": _YEAR, "items": []})
        assert resp.status_code == 422, resp.text
        assert resp.json()["detail"]["error_code"] == "FORMULA_BATCH_EMPTY"

    @pytest.mark.asyncio
    async def test_batch_over_limit_rejected_422_no_write(self, db, seed):
        from app.routers.wp_formula import _BATCH_MAX_ROWS

        user = await _load_user(db, seed.user_id)
        app = _make_app(db, user)
        items = [
            {"sheet_name": "Z1-1", "target_cell": f"C{i}", "expression": "1 + 1"}
            for i in range(_BATCH_MAX_ROWS + 1)
        ]
        before = await _audit_count(seed.project_id)
        with _NO_REF_ISSUES, TestClient(app, raise_server_exceptions=False) as c:
            resp = c.put(f"/api/workpapers/{seed.wp_id}/formulas/batch",
                         json={"year": _YEAR, "items": items})
        assert resp.status_code == 422, resp.text
        assert resp.json()["detail"]["error_code"] == "FORMULA_BATCH_TOO_MANY_ROWS"
        # 0 副作用：无新审计、无新公式行
        assert await _audit_count(seed.project_id) == before
        async with async_sessionmaker(_engine, class_=AsyncSession,
                                      expire_on_commit=False)() as s:
            cnt = (await s.execute(
                select(func.count()).select_from(WpFormula)
                .where(WpFormula.wp_id == seed.wp_id))).scalar_one()
            assert cnt == 1, "超限批次不得落库任何行"

    @pytest.mark.asyncio
    async def test_batch_one_row_fails_whole_rollback(self, db, seed):
        """批内一条合法、一条非法（非法 formula_type）→ 整批 422 回滚，合法行也不落库。"""
        user = await _load_user(db, seed.user_id)
        app = _make_app(db, user)
        items = [
            {"sheet_name": "Z1-1", "target_cell": "D1", "expression": "2 + 2"},
            # 第二行非法类型 → service 返 issues → 整批回滚
            {"sheet_name": "Z1-1", "target_cell": "D2", "expression": "3 + 3",
             "formula_type": "NOT_A_TYPE"},
        ]
        before = await _audit_count(seed.project_id)
        with _NO_REF_ISSUES, TestClient(app, raise_server_exceptions=False) as c:
            resp = c.put(f"/api/workpapers/{seed.wp_id}/formulas/batch",
                         json={"year": _YEAR, "items": items})
        assert resp.status_code == 422, resp.text
        assert resp.json()["detail"]["failed_index"] == 1
        # 单事务一致：合法的 D1 也不得落库；审计不新增
        async with async_sessionmaker(_engine, class_=AsyncSession,
                                      expire_on_commit=False)() as s:
            d1 = (await s.execute(select(WpFormula).where(
                WpFormula.wp_id == seed.wp_id,
                WpFormula.target_cell == "D1"))).scalar_one_or_none()
            assert d1 is None, "整批回滚后，先前成功的 D1 行也不得残留"
        assert await _audit_count(seed.project_id) == before

    @pytest.mark.asyncio
    async def test_batch_all_ok_commits_and_audits(self, db, seed):
        user = await _load_user(db, seed.user_id)
        app = _make_app(db, user)
        items = [
            {"sheet_name": "Z1-1", "target_cell": "E1", "expression": "4 + 4"},
            {"sheet_name": "Z1-1", "target_cell": "E2", "expression": "5 + 5"},
        ]
        before = await _audit_count(seed.project_id)
        with _NO_REF_ISSUES, TestClient(app, raise_server_exceptions=False) as c:
            resp = c.put(f"/api/workpapers/{seed.wp_id}/formulas/batch",
                         json={"year": _YEAR, "items": items})
        assert resp.status_code == 200, resp.text
        assert resp.json()["saved_count"] == 2
        async with async_sessionmaker(_engine, class_=AsyncSession,
                                      expire_on_commit=False)() as s:
            cnt = (await s.execute(
                select(func.count()).select_from(WpFormula)
                .where(WpFormula.wp_id == seed.wp_id,
                       WpFormula.target_cell.in_(["E1", "E2"])))).scalar_one()
            assert cnt == 2
        # 审计链每行一条新条目
        assert await _audit_count(seed.project_id) == before + 2


# ══════════════════════════════════════════════════════════════════════════
# 2. CAS 乐观锁冲突（单条 + 批量）
# ══════════════════════════════════════════════════════════════════════════


class TestCAS:

    @pytest.mark.asyncio
    async def test_single_cas_conflict_409(self, db, seed):
        """既有行 version=1，提交 expected_version=99（陈旧）→ 409，不覆盖。"""
        user = await _load_user(db, seed.user_id)
        app = _make_app(db, user)
        with _NO_REF_ISSUES, TestClient(app, raise_server_exceptions=False) as c:
            resp = c.put(f"/api/workpapers/{seed.wp_id}/formulas",
                         json={"sheet_name": "Z1-1", "target_cell": "B2",
                               "expression": "9 + 9", "year": _YEAR,
                               "expected_version": 99})
        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"]["error_code"] == "FORMULA_VERSION_CONFLICT"
        # 不覆盖：原表达式仍是 "1 + 1"
        async with async_sessionmaker(_engine, class_=AsyncSession,
                                      expire_on_commit=False)() as s:
            row = (await s.execute(select(WpFormula).where(
                WpFormula.id == seed.existing_formula_id))).scalar_one()
            assert row.expression == "1 + 1", "CAS 冲突不得覆盖既有公式"

    @pytest.mark.asyncio
    async def test_single_cas_match_passes(self, db, seed):
        """反向断言：expected_version=1（与库中一致）→ 保存通过、版本自增为 2。"""
        user = await _load_user(db, seed.user_id)
        app = _make_app(db, user)
        with _NO_REF_ISSUES, TestClient(app, raise_server_exceptions=False) as c:
            resp = c.put(f"/api/workpapers/{seed.wp_id}/formulas",
                         json={"sheet_name": "Z1-1", "target_cell": "B2",
                               "expression": "7 + 7", "year": _YEAR,
                               "expected_version": 1})
        assert resp.status_code == 200, resp.text
        async with async_sessionmaker(_engine, class_=AsyncSession,
                                      expire_on_commit=False)() as s:
            row = (await s.execute(select(WpFormula).where(
                WpFormula.id == seed.existing_formula_id))).scalar_one()
            assert row.expression == "7 + 7"
            assert row.definition_version == 2, "版本一致的保存应自增 definition_version"

    @pytest.mark.asyncio
    async def test_batch_cas_conflict_whole_rollback_409(self, db, seed):
        """批内一行命中 CAS 冲突 → 整批 409 回滚，其它行不落库。"""
        user = await _load_user(db, seed.user_id)
        app = _make_app(db, user)
        items = [
            {"sheet_name": "Z1-1", "target_cell": "F1", "expression": "1 + 2"},
            {"sheet_name": "Z1-1", "target_cell": "B2", "expression": "3 + 4",
             "expected_version": 42},  # 陈旧版本 → 冲突
        ]
        with _NO_REF_ISSUES, TestClient(app, raise_server_exceptions=False) as c:
            resp = c.put(f"/api/workpapers/{seed.wp_id}/formulas/batch",
                         json={"year": _YEAR, "items": items})
        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"]["error_code"] == "FORMULA_VERSION_CONFLICT"
        async with async_sessionmaker(_engine, class_=AsyncSession,
                                      expire_on_commit=False)() as s:
            f1 = (await s.execute(select(WpFormula).where(
                WpFormula.wp_id == seed.wp_id,
                WpFormula.target_cell == "F1"))).scalar_one_or_none()
            assert f1 is None, "CAS 冲突整批回滚后新行 F1 不得残留"
            b2 = (await s.execute(select(WpFormula).where(
                WpFormula.id == seed.existing_formula_id))).scalar_one()
            assert b2.expression == "1 + 1", "CAS 冲突不得覆盖既有 B2"


# ══════════════════════════════════════════════════════════════════════════
# 3. wp CRUD 审计哈希链（真实 user_id）
# ══════════════════════════════════════════════════════════════════════════


class TestAuditChain:

    @pytest.mark.asyncio
    async def test_single_save_writes_audit_real_user(self, db, seed):
        user = await _load_user(db, seed.user_id)
        app = _make_app(db, user)
        before = await _audit_count(seed.project_id)
        with _NO_REF_ISSUES, TestClient(app, raise_server_exceptions=False) as c:
            resp = c.put(f"/api/workpapers/{seed.wp_id}/formulas",
                         json={"sheet_name": "Z1-1", "target_cell": "G1",
                               "expression": "6 + 6", "year": _YEAR})
        assert resp.status_code == 200, resp.text
        assert await _audit_count(seed.project_id) == before + 1
        # user_id 为真实操作人（非全零），module=workpaper
        async with async_sessionmaker(_engine, class_=AsyncSession,
                                      expire_on_commit=False)() as s:
            entry = (await s.execute(
                select(AuditLogEntry)
                .where(AuditLogEntry.object_type == "wp_formula")
                .order_by(AuditLogEntry.ts.desc()))).scalars().first()
            assert entry.user_id == seed.user_id, "审计 user_id 必须是真实操作人"
            assert entry.user_id != uuid.UUID(int=0), "禁写死全零 user_id"
            assert entry.action_type == "formula.changed"
            assert (entry.payload or {}).get("module") == "workpaper"

    @pytest.mark.asyncio
    async def test_single_delete_writes_audit(self, db, seed):
        user = await _load_user(db, seed.user_id)
        app = _make_app(db, user)
        before = await _audit_count(seed.project_id)
        with _NO_REF_ISSUES, TestClient(app, raise_server_exceptions=False) as c:
            resp = c.delete(
                f"/api/workpapers/{seed.wp_id}/formulas/{seed.existing_formula_id}")
        assert resp.status_code == 200, resp.text
        assert await _audit_count(seed.project_id) == before + 1
        async with async_sessionmaker(_engine, class_=AsyncSession,
                                      expire_on_commit=False)() as s:
            entry = (await s.execute(
                select(AuditLogEntry)
                .where(AuditLogEntry.object_type == "wp_formula")
                .order_by(AuditLogEntry.ts.desc()))).scalars().first()
            assert (entry.payload or {}).get("action") == "delete"
            assert entry.user_id == seed.user_id


# ══════════════════════════════════════════════════════════════════════════
# 4. 强制版本前置条件（原子并发由真实 PG 专测）
# ══════════════════════════════════════════════════════════════════════════


class TestCASPreconditionRequired:

    @pytest.mark.asyncio
    async def test_existing_formula_without_expected_version_returns_428(self, db, seed):
        user = await _load_user(db, seed.user_id)
        app = _make_app(db, user)
        with _NO_REF_ISSUES, TestClient(app, raise_server_exceptions=False) as c:
            resp = c.put(
                f"/api/workpapers/{seed.wp_id}/formulas",
                json={
                    "sheet_name": "Z1-1",
                    "target_cell": "B2",
                    "expression": "8 + 8",
                    "year": _YEAR,
                },
            )
        assert resp.status_code == 428, resp.text
        assert resp.json()["detail"]["error_code"] == "FORMULA_VERSION_REQUIRED"

    @pytest.mark.asyncio
    async def test_batch_missing_expected_version_rolls_back_all(self, db, seed):
        user = await _load_user(db, seed.user_id)
        app = _make_app(db, user)
        items = [
            {"sheet_name": "Z1-1", "target_cell": "NEW1", "expression": "1 + 1"},
            {"sheet_name": "Z1-1", "target_cell": "B2", "expression": "2 + 2"},
        ]
        with _NO_REF_ISSUES, TestClient(app, raise_server_exceptions=False) as c:
            resp = c.put(
                f"/api/workpapers/{seed.wp_id}/formulas/batch",
                json={"year": _YEAR, "items": items},
            )
        assert resp.status_code == 428, resp.text
        async with async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)() as s:
            created = (await s.execute(select(WpFormula).where(
                WpFormula.wp_id == seed.wp_id,
                WpFormula.target_cell == "NEW1",
            ))).scalar_one_or_none()
            existing = (await s.execute(select(WpFormula).where(
                WpFormula.id == seed.existing_formula_id,
            ))).scalar_one()
        assert created is None
        assert existing.expression == "1 + 1"
        assert existing.definition_version == 1
