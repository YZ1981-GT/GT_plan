"""委派保存后必须失效程序表 auto_data 缓存（A1 看板复核人员姓名）。

🔴 背景（2026-09-29 数据链断点 3 的副作用收口）：
``AssignmentService.save_assignments`` 原来发布 ``EventType.DATA_IMPORTED`` 冒充「数据导入」，
会把全项目底稿标 stale、清地址库/报表缓存——已改为 ``broadcast_raw('workpaper.assigned')``。
但那条伪事件**顺带**触发了 ``_invalidate_procedure_table_cache``；去掉之后，
A1 看板 ``review_dashboard_status``（读 ``project_assignments`` 取五级复核人姓名，缓存 TTL 30s）
会在委派后继续显示旧复核人。修复 = router 在 commit 之后显式 ``invalidate_auto_cache``。

测试方式：TestClient 真发 ``POST /api/projects/{pid}/assignments``（只 override
``get_current_user`` / ``get_db``），断言：
1. 本项目缓存被清空、他项目缓存保留（不能退化成全局清空）；
2. SOD 冲突 409 时（事务回滚）缓存**不**被清——库没变，缓存仍与库一致。
"""
from __future__ import annotations

import time
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
from app.models.base import Base, UserRole  # noqa: E402
import app.models.core  # noqa: E402, F401
import app.models.staff_models  # noqa: E402, F401
import app.models.audit_platform_models  # noqa: E402, F401
import app.models.collaboration_models  # noqa: E402, F401
from app.models.core import Project, ProjectStatus, ProjectType, User  # noqa: E402
from app.models.staff_models import StaffMember  # noqa: E402
from app.services import procedure_table_auto_service as pta  # noqa: E402

_SOURCE = "review_dashboard_status"


@pytest_asyncio.fixture
async def env():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    pid, other_pid = uuid.uuid4(), uuid.uuid4()
    staff_id = uuid.uuid4()
    admin = User(
        id=uuid.uuid4(), username="admin_assign", email="a@t.local",
        hashed_password="x", role=UserRole.admin, is_active=True,
    )
    async with factory() as db:
        db.add(admin)
        for p in (pid, other_pid):
            db.add(Project(
                id=p, name=f"委派缓存项目_{p.hex[:4]}", client_name="测试客户",
                project_type=ProjectType.annual, status=ProjectStatus.created, audit_year=2025,
            ))
        db.add(StaffMember(id=staff_id, name="张三", employee_no="E-001"))
        await db.commit()

    from app.routers.assignments import router

    app = FastAPI()
    app.include_router(router)

    async def _db():
        async with factory() as s:
            yield s

    async def _user():
        return admin

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    pta._auto_cache.clear()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, pid, other_pid, staff_id
    pta._auto_cache.clear()
    await engine.dispose()


def _seed_cache(project_id: uuid.UUID) -> str:
    key = pta._cache_key(project_id, 2025, _SOURCE)
    pta._auto_cache[key] = (time.time(), {"levels": [{"role": "manager", "name": "旧复核人"}]})
    return key


@pytest.mark.asyncio
async def test_save_assignments_invalidates_only_this_project_cache(env):
    client, pid, other_pid, staff_id = env
    mine = _seed_cache(pid)
    other = _seed_cache(other_pid)

    r = await client.post(
        f"/api/projects/{pid}/assignments",
        json={"assignments": [{"staff_id": str(staff_id), "role": "manager"}]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["count"] == 1

    assert mine not in pta._auto_cache, "委派后本项目 A1 看板缓存仍在 ⇒ 30s 内显示旧复核人"
    assert other in pta._auto_cache, "失效范围退化成全局清空（误伤其他项目）"


@pytest.mark.asyncio
async def test_sod_conflict_rolls_back_and_keeps_cache(env, monkeypatch):
    client, pid, _other_pid, staff_id = env
    mine = _seed_cache(pid)

    from app.services import sod_guard_service

    async def _reject(self, *args, **kwargs):  # noqa: ANN001
        raise sod_guard_service.SodViolation(
            "EQCR 不得兼任签字合伙人", policy_code="EQCR_INDEPENDENCE",
        )

    monkeypatch.setattr(sod_guard_service.EqcrIndependenceRule, "check", _reject)

    r = await client.post(
        f"/api/projects/{pid}/assignments",
        json={"assignments": [{"staff_id": str(staff_id), "role": "eqcr"}]},
    )
    assert r.status_code == 409, r.text
    assert mine in pta._auto_cache, "事务已回滚（库未变）却清了缓存 —— 失效必须在 commit 之后"
