"""Sprint 2 端到端集成测试 — PM 工作流 (Batch 1 P0.5)

验证链路：委派 → 催办 → 重新分配 → 承诺 → 审批 → 简报
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user, require_project_access, require_role
from app.models.base import Base, ProjectStatus, ProjectType, UserRole
from app.models.core import Notification, Project
from app.models.phase15_models import IssueTicket
from app.models.staff_models import ProjectAssignment, StaffMember
from app.models.workpaper_models import (
    WorkingPaper,
    WpFileStatus,
    WpIndex,
    WpReviewStatus,
    WpSourceType,
    WpStatus,
)
from app.routers.batch_assign_enhanced import router as bae_router
from app.routers.pm_dashboard import router as pm_router
from app.routers.workhour_approve import router as wa_router
from app.routers.working_paper import router as wp_router
from app.routers.workpaper_remind import router as remind_router
from app.routers.wp_review_router import router as wp_review_router

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON


TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
engine = create_async_engine(TEST_DB_URL, echo=False)


class _FakeUser:
    def __init__(self, uid, role=UserRole.admin):
        self.id = uid
        self.username = "pm"
        self.email = "pm@x.com"
        self.role = role
        self.is_active = True
        self.is_deleted = False


MGR_USER_ID = uuid.uuid4()
AUD_USER_ID = uuid.uuid4()
MGR_STAFF_ID = uuid.uuid4()
AUD_STAFF_ID = uuid.uuid4()
NEW_AUD_STAFF_ID = uuid.uuid4()
PROJECT_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded(db_session: AsyncSession):
    """一个项目，含 manager / auditor / 新 auditor，一张底稿。"""
    proj = Project(
        id=PROJECT_ID, name="E2E 项目", client_name="客户 Z",
        project_type=ProjectType.annual, status=ProjectStatus.execution,
        created_by=MGR_USER_ID, wizard_state={},
    )
    db_session.add(proj)
    await db_session.flush()

    mgr = StaffMember(id=MGR_STAFF_ID, user_id=MGR_USER_ID, name="经理", title="经理")
    aud = StaffMember(id=AUD_STAFF_ID, user_id=AUD_USER_ID, name="审计员 A", title="审计员")
    new_aud = StaffMember(id=NEW_AUD_STAFF_ID, user_id=uuid.uuid4(), name="审计员 B", title="审计员")
    db_session.add_all([mgr, aud, new_aud])
    await db_session.flush()

    db_session.add_all([
        ProjectAssignment(id=uuid.uuid4(), project_id=PROJECT_ID,
                          staff_id=MGR_STAFF_ID, role="manager"),
        # 团队分配勾选 D：编制人走底稿主编委派后，被委派人须看得到该循环
        # （spec procedure-trim-generation-delegation-chain 任务 12）
        ProjectAssignment(id=uuid.uuid4(), project_id=PROJECT_ID,
                          staff_id=AUD_STAFF_ID, role="auditor", assigned_cycles=["D"]),
        ProjectAssignment(id=uuid.uuid4(), project_id=PROJECT_ID,
                          staff_id=NEW_AUD_STAFF_ID, role="auditor", assigned_cycles=["D"]),
    ])
    await db_session.flush()

    wp_idx = WpIndex(
        id=uuid.uuid4(), project_id=PROJECT_ID, wp_code="E-1",
        wp_name="E2E 底稿", audit_cycle="D", status=WpStatus.in_progress,
    )
    db_session.add(wp_idx)
    await db_session.flush()

    wp = WorkingPaper(
        id=uuid.uuid4(), project_id=PROJECT_ID, wp_index_id=wp_idx.id,
        file_path="/tmp/e.xlsx", source_type=WpSourceType.template,
        status=WpFileStatus.draft, review_status=WpReviewStatus.not_submitted,
        file_version=1,
    )
    db_session.add(wp)
    await db_session.commit()
    return {"wp_id": wp.id}


def _app(db_session: AsyncSession, user_id=MGR_USER_ID, role=UserRole.admin):
    app = FastAPI()
    app.include_router(bae_router)
    app.include_router(remind_router)
    app.include_router(wp_router)
    # 分配端点已拆到 wp_review_router（working_paper.py 只 re-export 函数，不含路由）——
    # 原用例只挂 wp_router，第 3 步恒 404、从未走到分配逻辑
    app.include_router(wp_review_router)
    app.include_router(pm_router)
    app.include_router(wa_router)

    fake = _FakeUser(user_id, role=role)

    async def _db():
        yield db_session

    async def _u():
        return fake

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _u
    # 绕过 require_project_access / require_role
    app.dependency_overrides[require_project_access("readonly")] = _u
    app.dependency_overrides[require_project_access("edit")] = _u
    app.dependency_overrides[require_project_access("review")] = _u
    app.dependency_overrides[require_role(["manager", "admin"])] = _u
    app.dependency_overrides[require_role(["admin", "partner", "manager"])] = _u
    return app


@pytest.mark.asyncio
async def test_pm_full_workflow(db_session, seeded):
    """完整 PM 工作流：委派→催办→重新分配→承诺→审批→简报。"""
    app = _app(db_session)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://t") as c:
        # 1. 委派：batch-assign-enhanced 给底稿分配 auditor A
        resp = await c.post(
            "/api/workpapers/batch-assign-enhanced",
            json={
                "wp_ids": [str(seeded["wp_id"])],
                "strategy": "manual",
                "candidates": [str(AUD_USER_ID)],
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["updated"] == 1

        # 2. 催办 auditor A
        resp = await c.post(
            f"/api/projects/{PROJECT_ID}/workpapers/{seeded['wp_id']}/remind",
            json={},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["remind_count"] == 1

        # 3. 重新分配到 auditor B（传人员 id：分配走底稿主编委派事务，人员 id / 用户 id 都解析为本项目人员，
        #    落库为其用户 id —— spec procedure-trim-generation-delegation-chain 任务 12）
        resp = await c.put(
            f"/api/projects/{PROJECT_ID}/working-papers/{seeded['wp_id']}/assign",
            json={"assigned_to": str(uuid.UUID(str(NEW_AUD_STAFF_ID)).hex)},
        )
        assert resp.status_code == 200, resp.text
        import sqlalchemy as _sa
        new_user = (await db_session.execute(
            _sa.select(StaffMember.user_id).where(StaffMember.id == NEW_AUD_STAFF_ID))).scalar_one()
        assigned = (await db_session.execute(
            _sa.select(WorkingPaper.assigned_to).where(WorkingPaper.id == seeded["wp_id"]))).scalar_one()
        assert assigned == new_user

        # 4. 沟通记录承诺 (POST /api/projects/{id}/communications)
        resp = await c.post(
            f"/api/projects/{PROJECT_ID}/communications",
            json={
                "date": "2026-05-10",
                "contact_person": "客户 A",
                "topic": "PBC 催收",
                "content": "客户承诺本周提供银行流水",
                "commitments": [
                    {"content": "银行流水", "due_date": "2026-05-15"},
                ],
                "related_wp_codes": [],
                "related_accounts": [],
            },
        )
        assert resp.status_code == 200, resp.text

        # 5. 工时审批（需先造一条待审批工时）
        # 审批服务按 work_hour_entries（WorkHourEntry，submitted → approved）审批；原用例造的是旧表
        # WorkHour + confirmed，第 3 步恒 404 时从未走到这里，复活后才暴露（审批路由的项目鉴权仍查旧表，
        # 见 spec procedure-trim-generation-delegation-chain design §8 范围外登记）
        from datetime import datetime, timezone
        from app.models.workhour_entry_models import WorkHourEntry
        wh = WorkHourEntry(
            id=uuid.uuid4(), user_id=AUD_USER_ID, project_id=PROJECT_ID,
            date=date.today(), hours=Decimal("8"), cycle="D", wp_code="E-1",
            description="E2E 工时", status="submitted", submitted_at=datetime.now(timezone.utc),
        )
        db_session.add(wh)
        await db_session.commit()

        resp = await c.post(
            "/api/workhours/batch-approve",
            json={"hour_ids": [str(wh.id)], "action": "approve"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["approved_count"] == 1

    # 验证各链路产出了对应记录
    import sqlalchemy as sa
    # Notification >= 2: assignment_created + workpaper_reminder + workhour_approved
    notifs = (await db_session.execute(sa.select(Notification))).scalars().all()
    types = {n.message_type for n in notifs}
    assert "assignment_created" in types
    assert "workpaper_reminder" in types
    assert "workhour_approved" in types

    # IssueTicket >= 2: reminder + client_commitment
    tickets = (await db_session.execute(sa.select(IssueTicket))).scalars().all()
    sources = {t.source for t in tickets}
    assert "reminder" in sources
    assert "client_commitment" in sources
