"""Property 7：manual_override 守卫不变量 — hypothesis 属性测试

V3 收官增强 Req 7.7。

不变量定义：

P7-INV-1：is_manual_override=True + propagation_origin='user_edit'
  → _check_manual_override_before_propagate 返回 'block_enqueued'
  且数据库新增 1 条 status='pending' 冲突。

P7-INV-2：is_manual_override=True + propagation_origin='system_recompute'
  → 返回 'auto_resolved'
  且数据库新增 1 条 status='resolved' resolution='accept_new'。

P7-INV-3：is_manual_override=False
  → 返回 'allow' 且数据库无新增冲突记录。

P7-INV-4：pending 冲突 resolve 后 status='resolved'，
  final_value 严格按 resolution 选择（keep_manual=manual / accept_new=upstream / merge=merge_value）。

调速：max_examples=15-20，列表 size 0-30。

Validates: Requirements 7.7
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
import pytest_asyncio
from hypothesis import HealthCheck, given, settings, strategies as st
from sqlalchemy import select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from unittest.mock import patch

# SQLite 兼容（必须先于模型导入）
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

from app.models.base import Base  # noqa: E402

# 注册测试所需模型
import app.models.core  # noqa: E402, F401
import app.models.audit_log_models  # noqa: E402, F401
import app.models.v3_refinement_models  # noqa: E402, F401

from app.models.base import ProjectStatus, ProjectType, UserRole  # noqa: E402
from app.models.core import Project, User  # noqa: E402
from app.models.v3_refinement_models import CrossModuleConflict  # noqa: E402
from app.services import conflict_resolution_service as svc  # noqa: E402


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _setup_db_with_user_project() -> tuple[
    async_sessionmaker, AsyncSession, uuid.UUID, uuid.UUID
]:
    """重置 DB + 写一条 user/project，返回 (factory, session, user_id, project_id)。"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        tables_to_create = [
            Base.metadata.tables["users"],
            Base.metadata.tables["projects"],
            Base.metadata.tables["audit_log_entries"],
            Base.metadata.tables["cross_module_conflicts"],
        ]
        await conn.run_sync(Base.metadata.create_all, tables=tables_to_create)

    factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    session = factory()

    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    user = User(
        id=user_id,
        username=f"pbt7-{user_id.hex[:8]}",
        email=f"{user_id.hex[:8]}@pbt.local",
        hashed_password="x",
        role=UserRole.auditor,
        is_active=True,
    )
    project = Project(
        id=project_id,
        name="P7 PBT 项目",
        client_name="P7 客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.execution,
    )
    session.add(user)
    session.add(project)
    await session.commit()
    return factory, session, user_id, project_id


async def _count_conflicts(
    session: AsyncSession, project_id: uuid.UUID, *, status: str | None = None
) -> int:
    stmt = select(CrossModuleConflict).where(
        CrossModuleConflict.project_id == project_id
    )
    if status is not None:
        stmt = stmt.where(CrossModuleConflict.status == status)
    result = await session.execute(stmt)
    return len(result.scalars().all())


# ---------------------------------------------------------------------------
# P7-INV-1：user_edit + manual_override → block_enqueued + 1 pending
# ---------------------------------------------------------------------------


class TestProperty7UserEditBlocksAndEnqueues:
    """**Validates: Requirements 7.7**

    P7-INV-1：is_manual_override=True + 'user_edit'
    → 'block_enqueued' + 1 条 pending。
    """

    @settings(
        max_examples=15,
        deadline=None,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
        ],
    )
    @given(
        target_field=st.sampled_from(["amount", "narrative_p1", "cells.A1", "cells.B2"]),
        new_value=st.text(min_size=0, max_size=20),
        manual_value=st.text(min_size=0, max_size=20),
    )
    @pytest.mark.asyncio
    async def test_user_edit_blocks_and_enqueues(
        self,
        target_field: str,
        new_value: str,
        manual_value: str,
    ):
        """user_edit + manual_override → block_enqueued + pending 计数 +1。"""
        factory, session, user_id, project_id = await _setup_db_with_user_project()
        try:
            with patch("app.services.event_bus.event_bus.broadcast_raw"):
                result = await svc._check_manual_override_before_propagate(
                    db=session,
                    project_id=project_id,
                    source_module="workpaper",
                    source_id=uuid.uuid4(),
                    target_module="disclosure",
                    target_id=uuid.uuid4(),
                    target_field=target_field,
                    new_value=new_value,
                    current_value=manual_value,
                    is_manual_override=True,
                    user_id=user_id,
                    propagation_origin="user_edit",
                )
            await session.commit()

            assert result == "block_enqueued"
            assert await _count_conflicts(session, project_id, status="pending") == 1
            assert await _count_conflicts(session, project_id, status="resolved") == 0
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# P7-INV-2：system_recompute + manual_override → auto_resolved + resolved
# ---------------------------------------------------------------------------


class TestProperty7SystemRecomputeAutoResolves:
    """**Validates: Requirements 7.7**

    P7-INV-2：is_manual_override=True + 'system_recompute'
    → 'auto_resolved' + status='resolved' + resolution='accept_new'。
    """

    @settings(
        max_examples=15,
        deadline=None,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
        ],
    )
    @given(
        target_field=st.sampled_from(["amount", "narrative_p1", "cells.A1"]),
        new_value=st.text(min_size=0, max_size=20),
        manual_value=st.text(min_size=0, max_size=20),
    )
    @pytest.mark.asyncio
    async def test_system_recompute_auto_resolves(
        self,
        target_field: str,
        new_value: str,
        manual_value: str,
    ):
        """system_recompute + manual_override → auto_resolved + final_value=new_value。"""
        factory, session, user_id, project_id = await _setup_db_with_user_project()
        try:
            with patch("app.services.event_bus.event_bus.broadcast_raw"):
                result = await svc._check_manual_override_before_propagate(
                    db=session,
                    project_id=project_id,
                    source_module="trial_balance",
                    source_id=uuid.uuid4(),
                    target_module="report",
                    target_id=uuid.uuid4(),
                    target_field=target_field,
                    new_value=new_value,
                    current_value=manual_value,
                    is_manual_override=True,
                    user_id=user_id,
                    propagation_origin="system_recompute",
                )
            await session.commit()

            assert result == "auto_resolved"
            # 0 pending + 1 resolved（resolution='accept_new'）
            assert await _count_conflicts(session, project_id, status="pending") == 0
            assert await _count_conflicts(session, project_id, status="resolved") == 1

            stmt = select(CrossModuleConflict).where(
                CrossModuleConflict.project_id == project_id
            )
            res = await session.execute(stmt)
            conflict = res.scalar_one()
            assert conflict.resolution == "accept_new"
            assert conflict.final_value == new_value
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# P7-INV-3：is_manual_override=False → allow + 0 写入
# ---------------------------------------------------------------------------


class TestProperty7AllowWhenNoOverride:
    """**Validates: Requirements 7.7**

    P7-INV-3：is_manual_override=False → 'allow'，无任何冲突记录写入。
    """

    @settings(
        max_examples=15,
        deadline=None,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
        ],
    )
    @given(
        propagation_origin=st.sampled_from(["user_edit", "system_recompute"]),
        target_field=st.sampled_from(["amount", "narrative_p1", "cells.A1"]),
        new_value=st.text(min_size=0, max_size=20),
        manual_value=st.text(min_size=0, max_size=20),
    )
    @pytest.mark.asyncio
    async def test_no_override_allows(
        self,
        propagation_origin: str,
        target_field: str,
        new_value: str,
        manual_value: str,
    ):
        """is_manual_override=False → allow + 0 冲突。"""
        factory, session, user_id, project_id = await _setup_db_with_user_project()
        try:
            with patch("app.services.event_bus.event_bus.broadcast_raw"):
                result = await svc._check_manual_override_before_propagate(
                    db=session,
                    project_id=project_id,
                    source_module="workpaper",
                    source_id=uuid.uuid4(),
                    target_module="disclosure",
                    target_id=uuid.uuid4(),
                    target_field=target_field,
                    new_value=new_value,
                    current_value=manual_value,
                    is_manual_override=False,
                    user_id=user_id,
                    propagation_origin=propagation_origin,
                )
            await session.commit()

            assert result == "allow"
            assert await _count_conflicts(session, project_id) == 0
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# P7-INV-4：pending → resolve 后 final_value 按 resolution 严格选择
# ---------------------------------------------------------------------------


class TestProperty7ResolveFinalValue:
    """**Validates: Requirements 7.7**

    P7-INV-4：resolve 后 status='resolved'，final_value 按 resolution 选择。
    """

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
        ],
    )
    @given(
        upstream_value=st.text(min_size=1, max_size=20),
        manual_value=st.text(min_size=1, max_size=20),
        merge_value=st.text(min_size=1, max_size=20),
        resolution=st.sampled_from(["keep_manual", "accept_new", "merge"]),
    )
    @pytest.mark.asyncio
    async def test_resolve_final_value_matches_resolution(
        self,
        upstream_value: str,
        manual_value: str,
        merge_value: str,
        resolution: str,
    ):
        """final_value 严格按 resolution 选择 manual / upstream / merge_value。"""
        factory, session, user_id, project_id = await _setup_db_with_user_project()
        try:
            with patch("app.services.event_bus.event_bus.broadcast_raw"):
                conflict = await svc.enqueue(
                    db=session,
                    project_id=project_id,
                    source_module="workpaper",
                    source_id=uuid.uuid4(),
                    target_module="disclosure",
                    target_id=uuid.uuid4(),
                    target_field="amount",
                    upstream_value=upstream_value,
                    manual_value=manual_value,
                    user_id=user_id,
                )

            resolved = await svc.resolve(
                db=session,
                conflict_id=conflict.id,
                user_id=user_id,
                resolution=resolution,  # type: ignore[arg-type]
                merge_value=merge_value if resolution == "merge" else None,
            )
            await session.commit()

            assert resolved.status == "resolved"
            assert resolved.resolution == resolution
            if resolution == "keep_manual":
                assert resolved.final_value == manual_value
            elif resolution == "accept_new":
                assert resolved.final_value == upstream_value
            else:  # merge
                assert resolved.final_value == merge_value
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Sanity 固定场景 — 单独跑保证 hypothesis 失败时仍有传统断言可参考
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sanity_full_lifecycle_user_edit_then_resolve():
    """**Validates: Requirements 7.7** — 完整生命周期：user_edit 入队 → resolve 调解。"""
    factory, session, user_id, project_id = await _setup_db_with_user_project()
    try:
        with patch("app.services.event_bus.event_bus.broadcast_raw"):
            result = await svc._check_manual_override_before_propagate(
                db=session,
                project_id=project_id,
                source_module="workpaper",
                source_id=uuid.uuid4(),
                target_module="disclosure",
                target_id=uuid.uuid4(),
                target_field="amount",
                new_value="100",
                current_value="200",
                is_manual_override=True,
                user_id=user_id,
                propagation_origin="user_edit",
            )
        assert result == "block_enqueued"

        # 取出 pending 冲突
        stmt = select(CrossModuleConflict).where(
            CrossModuleConflict.project_id == project_id,
            CrossModuleConflict.status == "pending",
        )
        res = await session.execute(stmt)
        pending = res.scalar_one()

        resolved = await svc.resolve(
            db=session,
            conflict_id=pending.id,
            user_id=user_id,
            resolution="keep_manual",
        )
        await session.commit()
        assert resolved.status == "resolved"
        assert resolved.final_value == "200"
    finally:
        await session.close()
