"""枚举字典 usage-count 真实数据验证 [template-library-coordination Sprint 6 Task 6.2]

复盘退回原因：原 Task 6.2 仅实现 SQL + rollback 兜底，未通过真实数据验证。
本测试用 SQLite in-memory + 真实 ORM 模型构造 fixture，断言：
  1. 已知字典（wp_status）插入 5 行 WorkingPaper 后能正确返回 11 个枚举值的 counts
  2. 不存在的字典返回 404 + DICT_NOT_FOUND
  3. 配置中表名为空字符串的字典（template_status / pdf_task_status）返回全部 0 + 200
  4. db.execute 异常时走 try/except rollback 兜底返回 counts=0 不 500

Validates: Requirements 21.4
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# SQLite JSONB 兼容（与邻居 test_template_library_mgmt_integration.py 对齐）
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from app.core.database import get_db  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.models.core import Project, ProjectStatus, ProjectType, User, UserRole  # noqa: E402
from app.models.workpaper_models import (  # noqa: E402
    WorkingPaper,
    WpFileStatus,
    WpIndex,
    WpSourceType,
)

# 注册全部 ORM 模型到 metadata（避免 create_all 缺表，与邻居测试一致）
import app.models.audit_platform_models  # noqa: E402, F401
import app.models.dataset_models  # noqa: E402, F401
import app.models.report_models  # noqa: E402, F401
import app.models.consolidation_models  # noqa: E402, F401
import app.models.staff_models  # noqa: E402, F401
import app.models.collaboration_models  # noqa: E402, F401
import app.models.ai_models  # noqa: E402, F401
import app.models.extension_models  # noqa: E402, F401
import app.models.gt_coding_models  # noqa: E402, F401
import app.models.t_account_models  # noqa: E402, F401
import app.models.attachment_models  # noqa: E402, F401
import app.models.phase10_models  # noqa: E402, F401
import app.models.phase12_models  # noqa: E402, F401
import app.models.phase13_models  # noqa: E402, F401
import app.models.phase14_models  # noqa: E402, F401
import app.models.phase15_models  # noqa: E402, F401
import app.models.phase16_models  # noqa: E402, F401
import app.models.archive_models  # noqa: E402, F401
import app.models.knowledge_models  # noqa: E402, F401

import sqlalchemy as _sa  # noqa: E402

# Stub for 'workpapers' table referenced by AI models FK
class _WorkpaperStub(Base):
    __tablename__ = "workpapers"
    __table_args__ = {"extend_existing": True}
    id = _sa.Column(_sa.Uuid, primary_key=True)


_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


ADMIN_USER_ID = uuid.uuid4()
PROJECT_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """每个测试独立 SQLite in-memory + 全表 create_all。"""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        admin = User(
            id=ADMIN_USER_ID,
            username="admin_test",
            email="admin@test.com",
            hashed_password="x",
            role=UserRole.admin,
        )
        session.add(admin)

        proj = Project(
            id=PROJECT_ID,
            name="usage-count 测试",
            client_name="测试客户",
            project_type=ProjectType.annual,
            status=ProjectStatus.planning,
            created_by=ADMIN_USER_ID,
        )
        session.add(proj)
        await session.commit()

        yield session


def _make_app(db_session: AsyncSession) -> FastAPI:
    """构造最小 FastAPI app，挂载 system_dicts router。"""
    from app.routers.system_dicts import router as sd_router

    app = FastAPI()
    app.include_router(sd_router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return User(
            id=ADMIN_USER_ID,
            username="admin",
            email="admin@test.com",
            hashed_password="x",
            role=UserRole.admin,
        )

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    return app


def _make_client(db_session: AsyncSession):
    return AsyncClient(transport=ASGITransport(app=_make_app(db_session)), base_url="http://test")


async def _create_wp_index(db: AsyncSession, wp_code: str) -> WpIndex:
    idx = WpIndex(project_id=PROJECT_ID, wp_code=wp_code, wp_name=f"测试_{wp_code}")
    db.add(idx)
    await db.flush()
    return idx


async def _seed_working_papers_with_statuses(
    db: AsyncSession, statuses: list[WpFileStatus]
) -> None:
    """批量插入 WorkingPaper（每个 status 创建独立的 WpIndex 和 WorkingPaper）。"""
    for i, status in enumerate(statuses):
        idx = await _create_wp_index(db, f"D{i+1}")
        wp = WorkingPaper(
            project_id=PROJECT_ID,
            wp_index_id=idx.id,
            file_path=f"/test/{i}.xlsx",
            source_type=WpSourceType.template,
            status=status,
            created_by=ADMIN_USER_ID,
        )
        db.add(wp)
    await db.commit()


# ---------------------------------------------------------------------------
# Test 1: wp_status 真实数据计数
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_usage_count_with_seeded_wp_status(db_session: AsyncSession):
    """插入 5 行 WorkingPaper（draft x2 / review_passed x1 / archived x2），断言：
      - 返回 list 包含全部 11 个 wp_status 枚举值
      - draft=2 / review_passed=1 / archived=2 / 其他全为 0

    Validates: Requirement 21.4 (引用计数真实数据准确性)
    """
    await _seed_working_papers_with_statuses(
        db_session,
        [
            WpFileStatus.draft,
            WpFileStatus.draft,
            WpFileStatus.review_passed,
            WpFileStatus.archived,
            WpFileStatus.archived,
        ],
    )

    async with _make_client(db_session) as client:
        resp = await client.get("/api/system/dicts/wp_status/usage-count")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body, list)

    # 字典 _DICTS["wp_status"] 共 11 个枚举值，必须全部出现（即使 count=0）
    counts = {item["value"]: item["count"] for item in body}
    assert len(counts) == 11, f"预期 11 个枚举值，实际 {len(counts)}"

    # 关键 status 计数准确
    assert counts.get("draft") == 2, f"draft 计数错误: {counts}"
    assert counts.get("review_passed") == 1, f"review_passed 计数错误: {counts}"
    assert counts.get("archived") == 2, f"archived 计数错误: {counts}"

    # 其余全部为 0
    other_values = {
        "not_started", "in_progress", "draft_complete", "edit_complete",
        "under_review", "revision_required",
        "review_level1_passed", "review_level2_passed",
    }
    for v in other_values:
        assert counts.get(v) == 0, f"{v} 应为 0，实际 {counts.get(v)}"


# ---------------------------------------------------------------------------
# Test 2: 未知字典返回 404 + DICT_NOT_FOUND
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_usage_count_returns_404_for_unknown_dict(db_session: AsyncSession):
    """请求不存在的字典 → 404 + error_code=DICT_NOT_FOUND。

    Validates: Requirement 21.4（端点错误处理）
    """
    async with _make_client(db_session) as client:
        resp = await client.get("/api/system/dicts/nonexistent_dict/usage-count")

    assert resp.status_code == 404, resp.text
    body = resp.json()
    # FastAPI HTTPException.detail 通过全局 handler 可能放在 message 字段或保留 detail
    detail = body.get("detail") or body.get("message") or {}
    if isinstance(detail, dict):
        assert detail.get("error_code") == "DICT_NOT_FOUND"
        assert detail.get("dict_key") == "nonexistent_dict"


# ---------------------------------------------------------------------------
# Test 3: 配置中无对应业务表的字典返回全部 0
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_usage_count_handles_missing_table_gracefully(db_session: AsyncSession):
    """template_status / pdf_task_status 在 _USAGE_COUNT_QUERIES 中 table=""
    （无对应业务表），应返回全部 0 而非 500。

    Validates: Requirement 21.4（无业务表的字典也要保持响应结构稳定）
    """
    async with _make_client(db_session) as client:
        # template_status：3 个枚举值
        r1 = await client.get("/api/system/dicts/template_status/usage-count")
        assert r1.status_code == 200
        body1 = r1.json()
        assert all(item["count"] == 0 for item in body1)
        # 字典 _DICTS["template_status"] 含 3 个值（draft/published/deprecated）
        values1 = {item["value"] for item in body1}
        assert values1 == {"draft", "published", "deprecated"}

        # pdf_task_status：4 个枚举值
        r2 = await client.get("/api/system/dicts/pdf_task_status/usage-count")
        assert r2.status_code == 200
        body2 = r2.json()
        assert all(item["count"] == 0 for item in body2)
        values2 = {item["value"] for item in body2}
        assert values2 == {"queued", "processing", "completed", "failed"}


# ---------------------------------------------------------------------------
# Test 4: db.execute 异常时走 rollback 兜底
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_usage_count_handles_query_failure_with_rollback(
    db_session: AsyncSession, monkeypatch
):
    """monkeypatch db.execute 抛异常 → 应 rollback + 返回 counts=0（不 500）。

    Validates: Requirement 21.4（端点对异常的健壮性，try/except + rollback 兜底）
    """
    rollback_called = {"value": False}

    original_execute = db_session.execute
    original_rollback = db_session.rollback

    async def patched_execute(*args, **kwargs):
        # 仅对 SELECT FROM working_paper 的查询抛错，其他放行
        sql = str(args[0]) if args else ""
        if "FROM working_paper" in sql:
            raise RuntimeError("simulated DB failure")
        return await original_execute(*args, **kwargs)

    async def patched_rollback():
        rollback_called["value"] = True
        return await original_rollback()

    monkeypatch.setattr(db_session, "execute", patched_execute)
    monkeypatch.setattr(db_session, "rollback", patched_rollback)

    async with _make_client(db_session) as client:
        resp = await client.get("/api/system/dicts/wp_status/usage-count")

    # 端点应返回 200 + 全部 counts=0（异常被 try/except 吞掉走兜底）
    assert resp.status_code == 200, resp.text
    body = resp.json()
    counts = {item["value"]: item["count"] for item in body}
    # 11 个枚举值都返回（结构稳定）
    assert len(counts) == 11
    # 异常时全部 count=0
    assert all(c == 0 for c in counts.values()), f"预期全 0，实际 {counts}"
    # rollback 被调用（事务污染恢复）
    assert rollback_called["value"], "异常时未调用 db.rollback() 恢复事务"
