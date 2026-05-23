"""L-3 快照对比端点单测（spec proposal-remaining-18 task 2.4）

验证 GET /api/projects/{pid}/working-papers/{wp_id}/prefill/snapshot-diff
返回 working_paper.prefill_tb_snapshot 与当前 trial_balance.audited_amount 的对比。

Validates:
- 无快照时 has_snapshot=False / rows=[]
- 有快照且 TB 未变 → is_stale=False / delta=0
- 有快照且 TB 变化 → is_stale=True / delta=current-last
- TB 缺失科目 → current_amount=None / is_stale=True
- 浮点容差 0.01 元（不能误报）
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User, UserRole
from app.models.workpaper_models import (
    WorkingPaper,
    WpIndex,
    WpSourceType,
)
from app.routers.wp_prefill_preview import router as prefill_preview_router

# SQLite 不识别 PG JSONB；映射到 JSON
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON


FAKE_USER_ID = uuid.uuid4()
FAKE_PROJECT_ID = uuid.uuid4()


class _FakeUser:
    def __init__(self):
        self.id = FAKE_USER_ID
        self.role = UserRole.admin
        self.email = "tester@example.com"


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def _seed_project_and_wp(
    db: AsyncSession,
    snapshot: dict | None = None,
    audit_year: int = 2025,
) -> uuid.UUID:
    project = Project(
        id=FAKE_PROJECT_ID,
        name="L-3 快照 endpoint 测试",
        client_name="L-3 快照 endpoint 测试",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=FAKE_USER_ID,
        audit_period_start=date(audit_year, 1, 1),
        audit_period_end=date(audit_year, 12, 31),
    )
    db.add(project)
    await db.flush()

    wp_index = WpIndex(
        project_id=FAKE_PROJECT_ID,
        wp_code="PF-DIFF",
        wp_name="L-3 快照 endpoint 测试底稿",
    )
    db.add(wp_index)
    await db.flush()

    wp = WorkingPaper(
        project_id=FAKE_PROJECT_ID,
        wp_index_id=wp_index.id,
        file_path="/tmp/dummy.xlsx",
        source_type=WpSourceType.template,
        file_version=1,
        prefill_tb_snapshot=snapshot,
    )
    db.add(wp)
    await db.commit()
    return wp.id


def _add_tb(
    db: AsyncSession,
    code: str,
    audited: float,
    year: int = 2025,
) -> None:
    db.add(TrialBalance(
        project_id=FAKE_PROJECT_ID,
        year=year,
        company_code="C001",
        standard_account_code=code,
        account_name=f"科目-{code}",
        account_category=AccountCategory.asset,
        unadjusted_amount=audited,
        audited_amount=audited,
    ))


def _build_app(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    # SQLite 不支持 PG `SET LOCAL` 语法，跳过 RLS context 设置
    async def _noop_rls(*_args, **_kwargs):
        return None

    monkeypatch.setattr("app.deps.set_rls_context", _noop_rls)
    monkeypatch.setattr("app.core.database.set_rls_context", _noop_rls)

    app = FastAPI()
    app.include_router(prefill_preview_router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return _FakeUser()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    return app


@pytest.mark.asyncio
async def test_no_snapshot_returns_has_snapshot_false(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    """working_paper.prefill_tb_snapshot 为 NULL → has_snapshot=False, rows=[]"""
    wp_id = await _seed_project_and_wp(db_session, snapshot=None)

    app = _build_app(db_session, monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            f"/api/projects/{FAKE_PROJECT_ID}/working-papers/{wp_id}/prefill/snapshot-diff"
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["has_snapshot"] is False
    assert body["snapshot_account_count"] == 0
    assert body["stale_count"] == 0
    assert body["rows"] == []


@pytest.mark.asyncio
async def test_snapshot_unchanged_returns_no_stale(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    """快照与 TB 一致 → 全部 is_stale=False / delta=0"""
    snapshot = {"1001": 12345.67, "2001": 99999.00}
    wp_id = await _seed_project_and_wp(db_session, snapshot=snapshot)
    _add_tb(db_session, "1001", 12345.67)
    _add_tb(db_session, "2001", 99999.00)
    await db_session.commit()

    app = _build_app(db_session, monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            f"/api/projects/{FAKE_PROJECT_ID}/working-papers/{wp_id}/prefill/snapshot-diff"
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_snapshot"] is True
    assert body["snapshot_account_count"] == 2
    assert body["stale_count"] == 0
    for r in body["rows"]:
        assert r["is_stale"] is False
        assert r["delta"] == 0.0


@pytest.mark.asyncio
async def test_snapshot_changed_marks_stale(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    """TB 变化 > 0.01 → is_stale=True 且 delta 与正负号正确"""
    snapshot = {"1001": 100.00, "2001": 200.00}
    wp_id = await _seed_project_and_wp(db_session, snapshot=snapshot)
    _add_tb(db_session, "1001", 150.00)   # +50
    _add_tb(db_session, "2001", 199.99)   # 浮点容差内（0.01），不应 stale
    await db_session.commit()

    app = _build_app(db_session, monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            f"/api/projects/{FAKE_PROJECT_ID}/working-papers/{wp_id}/prefill/snapshot-diff"
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_snapshot"] is True
    by_code = {r["account_code"]: r for r in body["rows"]}
    assert by_code["1001"]["is_stale"] is True
    assert by_code["1001"]["delta"] == pytest.approx(50.00)
    assert by_code["1001"]["last_amount"] == pytest.approx(100.00)
    assert by_code["1001"]["current_amount"] == pytest.approx(150.00)
    assert by_code["2001"]["is_stale"] is False
    assert body["stale_count"] == 1


@pytest.mark.asyncio
async def test_tb_account_deleted_marks_stale_with_null_current(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    """快照含科目但当前 TB 不存在 → current_amount=None 且 is_stale=True"""
    snapshot = {"9999": 555.55}
    wp_id = await _seed_project_and_wp(db_session, snapshot=snapshot)
    # 不插入 TB 记录
    await db_session.commit()

    app = _build_app(db_session, monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            f"/api/projects/{FAKE_PROJECT_ID}/working-papers/{wp_id}/prefill/snapshot-diff"
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_snapshot"] is True
    assert body["stale_count"] == 1
    row = body["rows"][0]
    assert row["account_code"] == "9999"
    assert row["last_amount"] == pytest.approx(555.55)
    assert row["current_amount"] is None
    assert row["is_stale"] is True


@pytest.mark.asyncio
async def test_workpaper_not_found_returns_404(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    """底稿不存在 → 404"""
    await _seed_project_and_wp(db_session, snapshot={"1001": 1.0})
    fake_wp_id = uuid.uuid4()

    app = _build_app(db_session, monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            f"/api/projects/{FAKE_PROJECT_ID}/working-papers/{fake_wp_id}/prefill/snapshot-diff"
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_rows_sorted_stale_first_then_by_abs_delta(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    """rows 排序：stale 在前，按 |delta| 降序"""
    snapshot = {"A": 100.0, "B": 100.0, "C": 100.0}
    wp_id = await _seed_project_and_wp(db_session, snapshot=snapshot)
    _add_tb(db_session, "A", 100.0)   # delta 0
    _add_tb(db_session, "B", 200.0)   # delta +100
    _add_tb(db_session, "C", 130.0)   # delta +30
    await db_session.commit()

    app = _build_app(db_session, monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            f"/api/projects/{FAKE_PROJECT_ID}/working-papers/{wp_id}/prefill/snapshot-diff"
        )
    body = resp.json()
    codes = [r["account_code"] for r in body["rows"]]
    # 期望顺序：B（|100|）, C（|30|），最后 A（非 stale）
    assert codes == ["B", "C", "A"]
