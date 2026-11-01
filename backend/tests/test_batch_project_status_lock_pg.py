"""批量建项 status lock_timeout 的真实 PostgreSQL 行为。"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import engine as app_engine
from app.models.base import UserRole
from app.models.batch_project_models import ProjectBatchImportPlan
from app.models.core import User
from app.services.batch_project_execution import get_owned_plan, get_readable_plan
from app.services.batch_project_status_lock import BatchPlanStatusBusy, with_status_lock_timeout


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_status_timeout_never_reads_old_validated_then_retry_gets_applied():
    if app_engine.dialect.name != "postgresql":
        pytest.skip("需要 PostgreSQL")
    url = settings.DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    token = uuid.uuid4().hex
    actor_id = plan_id = None
    try:
        async with factory() as setup:
            actor = User(
                username=f"status_busy_{token[:16]}",
                email=f"status_busy_{token[:16]}@example.test",
                hashed_password="x", role=UserRole.admin,
            )
            setup.add(actor)
            await setup.flush()
            plan = ProjectBatchImportPlan(
                actor_user_id=actor.id, mode="project", status="validated",
                file_name="【测试】status busy.xlsx", file_sha256="a" * 64,
                request_hash="b" * 64, idempotency_key=f"status-busy-{token[:20]}",
                rows=[], tree_preview=[], warnings=[],
                summary={"_plan_dependencies": {
                    "version": 1, "inventory_entities": [],
                    "read_project_ids": [], "edit_project_ids": [],
                }},
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            )
            setup.add(plan)
            await setup.commit()
            actor_id, plan_id = actor.id, plan.id

        async with factory() as writer:
            locked = await get_owned_plan(writer, plan_id, actor, for_update=True)
            locked.status = "applying"
            await writer.flush()
            async with factory() as reader:
                started = time.perf_counter()
                with pytest.raises(BatchPlanStatusBusy):
                    await with_status_lock_timeout(
                        reader,
                        lambda: get_readable_plan(reader, plan_id, actor, for_update=True),
                        timeout_ms=100,
                    )
                elapsed = time.perf_counter() - started
                assert 0.07 <= elapsed < 1.5
                assert await reader.scalar(sa.text("SELECT 1")) == 1

            locked.status = "applied"
            locked.receipt = {"success_count": 0, "fail_count": 0}
            await writer.commit()

        async with factory() as retry:
            visible = await with_status_lock_timeout(
                retry,
                lambda: get_readable_plan(retry, plan_id, actor, for_update=True),
                timeout_ms=500,
            )
            assert visible.status == "applied"
    finally:
        try:
            if actor_id or plan_id:
                async with factory() as cleanup:
                    if plan_id:
                        await cleanup.execute(sa.delete(ProjectBatchImportPlan).where(
                            ProjectBatchImportPlan.id == plan_id
                        ))
                    if actor_id:
                        await cleanup.execute(sa.delete(User).where(User.id == actor_id))
                    await cleanup.commit()
        finally:
            await engine.dispose()
