"""工时审批关联底稿完成度测试 — proposal-remaining-18 task 0.2 (M-5)

验证：
- _calc_user_wp_completion_rates 按 assigned_to 分组统计 WorkingPaper 完成率
- status >= edit_complete 视为已完成（含历史枚举 review_level1/2_passed）
- 软删除 working_paper 不计入分母
- 用户无任何分配底稿时返回 None（前端将渲染 "—"）
- GET /api/projects/{id}/workhours/approval 返回 wp_completion_rate 字段
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base
from app.models.core import Project, User, UserRole
from app.models.workhour_entry_models import WorkHourEntry
from app.models.workpaper_models import (
    WorkingPaper,
    WpFileStatus,
    WpIndex,
    WpSourceType,
)
from app.routers.workhour_approval import (
    _calc_user_wp_completion_rates,
    router,
)

# SQLite JSONB compat
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler  # noqa: E402

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON


TEST_ENGINE = create_async_engine("sqlite+aiosqlite:///:memory:")
TestSession = async_sessionmaker(
    TEST_ENGINE, class_=AsyncSession, expire_on_commit=False
)


PROJECT_ID = uuid.uuid4()
MGR_USER_ID = uuid.uuid4()
USER_A_ID = uuid.uuid4()  # 已分配 4 wp，2 完成
USER_B_ID = uuid.uuid4()  # 已分配 2 wp，0 完成
USER_C_ID = uuid.uuid4()  # 未分配任何 wp


def _wp(
    *,
    session: AsyncSession,
    project_id: uuid.UUID,
    wp_code: str,
    wp_name: str,
    assigned_to: uuid.UUID | None,
    status: WpFileStatus,
    is_deleted: bool = False,
) -> tuple[WpIndex, WorkingPaper]:
    """Helper：创建一对 (WpIndex, WorkingPaper)。

    working_paper 表 (project_id, wp_index_id) 唯一约束 → 每个 wp 必须有独立 index。
    """
    idx = WpIndex(
        id=uuid.uuid4(), project_id=project_id,
        wp_code=wp_code, wp_name=wp_name,
    )
    wp = WorkingPaper(
        id=uuid.uuid4(),
        project_id=project_id,
        wp_index_id=idx.id,
        file_path="/dummy.xlsx",
        source_type=WpSourceType.template,
        status=status,
        assigned_to=assigned_to,
        is_deleted=is_deleted,
    )
    session.add_all([idx, wp])
    return idx, wp


@pytest_asyncio.fixture
async def db_session():
    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with TestSession() as session:
        # 用户
        mgr = User(
            id=MGR_USER_ID, username="mgr", email="mgr@t.com",
            hashed_password="x", role=UserRole.manager,
        )
        ua = User(
            id=USER_A_ID, username="alice", email="a@t.com",
            hashed_password="x", role=UserRole.auditor,
        )
        ub = User(
            id=USER_B_ID, username="bob", email="b@t.com",
            hashed_password="x", role=UserRole.auditor,
        )
        uc = User(
            id=USER_C_ID, username="carol", email="c@t.com",
            hashed_password="x", role=UserRole.auditor,
        )
        session.add_all([mgr, ua, ub, uc])

        # 项目
        proj = Project(id=PROJECT_ID, name="P1", client_name="客户")
        session.add(proj)
        await session.flush()

        # User A：4 wp 分配，2 已完成（含 1 历史枚举 review_level2_passed）
        _wp(session=session, project_id=PROJECT_ID,
            wp_code="A1-1", wp_name="A 待编",
            assigned_to=USER_A_ID, status=WpFileStatus.draft)
        _wp(session=session, project_id=PROJECT_ID,
            wp_code="A1-2", wp_name="A 起草",
            assigned_to=USER_A_ID, status=WpFileStatus.draft)
        _wp(session=session, project_id=PROJECT_ID,
            wp_code="A1-3", wp_name="A 编完",
            assigned_to=USER_A_ID, status=WpFileStatus.edit_complete)
        _wp(session=session, project_id=PROJECT_ID,
            wp_code="A1-4", wp_name="A 历史复核通过",
            assigned_to=USER_A_ID, status=WpFileStatus.review_level2_passed)

        # User B：2 wp 分配，0 已完成
        _wp(session=session, project_id=PROJECT_ID,
            wp_code="B1-1", wp_name="B 起草 1",
            assigned_to=USER_B_ID, status=WpFileStatus.draft)
        _wp(session=session, project_id=PROJECT_ID,
            wp_code="B1-2", wp_name="B 起草 2",
            assigned_to=USER_B_ID, status=WpFileStatus.draft)

        # 软删除 wp（不应计入分母）：分给 A 但已删
        _wp(session=session, project_id=PROJECT_ID,
            wp_code="A1-DEL", wp_name="A 已删",
            assigned_to=USER_A_ID, status=WpFileStatus.archived,
            is_deleted=True)

        # 工时条目（submitted 待审批）
        today = date.today()
        session.add_all([
            WorkHourEntry(
                id=uuid.uuid4(), user_id=USER_A_ID, project_id=PROJECT_ID,
                date=today, hours=Decimal("8"), cycle="D",
                wp_code="D2-1", description="A",
                status="submitted", submitted_at=datetime.now(timezone.utc),
            ),
            WorkHourEntry(
                id=uuid.uuid4(), user_id=USER_B_ID, project_id=PROJECT_ID,
                date=today, hours=Decimal("4"), cycle="E",
                wp_code="E1-1", description="B",
                status="submitted", submitted_at=datetime.now(timezone.utc),
            ),
            WorkHourEntry(
                id=uuid.uuid4(), user_id=USER_C_ID, project_id=PROJECT_ID,
                date=today, hours=Decimal("2"), cycle="A",
                wp_code=None, description="C-未分配",
                status="submitted", submitted_at=datetime.now(timezone.utc),
            ),
        ])
        await session.commit()
        yield session

    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _make_client(db_session: AsyncSession):
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return User(
            id=MGR_USER_ID, username="mgr", email="mgr@t.com",
            hashed_password="x", role=UserRole.manager,
        )

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ── 单元测试：_calc_user_wp_completion_rates ──


class TestCalcWpCompletion:
    @pytest.mark.asyncio
    async def test_user_with_partial_completion(self, db_session):
        """A 4 wp / 2 完成（edit_complete + review_level2_passed），软删除不计 → 50%"""
        rates = await _calc_user_wp_completion_rates(
            db_session, PROJECT_ID, [USER_A_ID]
        )
        assert rates[USER_A_ID] == 50.0

    @pytest.mark.asyncio
    async def test_user_with_zero_completion(self, db_session):
        """B 2 wp / 0 完成 → 0%（区别于 None）"""
        rates = await _calc_user_wp_completion_rates(
            db_session, PROJECT_ID, [USER_B_ID]
        )
        assert rates[USER_B_ID] == 0.0

    @pytest.mark.asyncio
    async def test_user_without_assignment_returns_none(self, db_session):
        """C 无任何分配 → None（前端渲染为 —）"""
        rates = await _calc_user_wp_completion_rates(
            db_session, PROJECT_ID, [USER_C_ID]
        )
        assert rates[USER_C_ID] is None

    @pytest.mark.asyncio
    async def test_batch_query_returns_all_users(self, db_session):
        """批量查询 3 个用户单 SQL 返回完整字典（含 None 占位）"""
        rates = await _calc_user_wp_completion_rates(
            db_session, PROJECT_ID, [USER_A_ID, USER_B_ID, USER_C_ID]
        )
        assert set(rates.keys()) == {USER_A_ID, USER_B_ID, USER_C_ID}
        assert rates[USER_A_ID] == 50.0
        assert rates[USER_B_ID] == 0.0
        assert rates[USER_C_ID] is None

    @pytest.mark.asyncio
    async def test_empty_user_list_returns_empty(self, db_session):
        rates = await _calc_user_wp_completion_rates(db_session, PROJECT_ID, [])
        assert rates == {}


# ── 端点集成测试 ──


class TestApprovalEndpointWithCompletion:
    @pytest.mark.asyncio
    async def test_endpoint_returns_wp_completion_rate(self, db_session):
        async with _make_client(db_session) as client:
            resp = await client.get(
                f"/api/projects/{PROJECT_ID}/workhours/approval"
            )
            assert resp.status_code == 200
            body = resp.json()
            assert "items" in body
            assert body["total"] == 3

            by_user = {item["user_id"]: item for item in body["items"]}
            # 每个 entry 必含 wp_completion_rate 字段
            for item in body["items"]:
                assert "wp_completion_rate" in item

            # A 50% / B 0% / C None
            assert by_user[str(USER_A_ID)]["wp_completion_rate"] == 50.0
            assert by_user[str(USER_B_ID)]["wp_completion_rate"] == 0.0
            assert by_user[str(USER_C_ID)]["wp_completion_rate"] is None
