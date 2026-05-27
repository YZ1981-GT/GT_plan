"""conflict_resolution_service 单元测试 — V3 收官增强 Req 7.1

覆盖以下用例：
- test_enqueue_pending — 入队后 status='pending' resolution=None final_value=None
- test_enqueue_writes_audit — 入队同步写 cross_module_conflict_enqueued 审计
- test_enqueue_emits_sse_event — 入队 broadcast_raw 调用一次（mock）
- test_resolve_keep_manual — final_value=manual_value
- test_resolve_accept_new — final_value=upstream_value
- test_resolve_merge_with_value — final_value=merge_value
- test_resolve_merge_without_value_raises — merge 缺 merge_value 报错
- test_resolve_invalid_resolution_raises — resolution 非法值报错
- test_resolve_already_resolved_raises — 重复 resolve 抛 ConflictAlreadyResolvedError
- test_resolve_not_found_raises — 不存在 conflict_id 抛 ConflictNotFoundError
- test_list_pending_filters — list_pending 仅返回 pending
- test_list_by_project_filters — 按 status / target_module 过滤
- test_count_pending — 计数随调解减少
- test_auto_resolve_system_recompute — 直接写 status='resolved' resolution='accept_new'
- test_audit_log_for_each_action — enqueue + resolve + auto_resolve 各写一条审计

Validates: Requirements 7.1
"""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# SQLite 兼容 JSONB + ARRAY（必须先于模型导入）
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

from app.models.base import Base  # noqa: E402

# 注册测试所需模型
import app.models.core  # noqa: E402, F401
import app.models.audit_log_models  # noqa: E402, F401
import app.models.v3_refinement_models  # noqa: E402, F401

from app.models.audit_log_models import AuditLogEntry  # noqa: E402
from app.models.v3_refinement_models import CrossModuleConflict  # noqa: E402
from app.services import conflict_resolution_service as svc  # noqa: E402


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """每个测试独立的内存数据库会话。

    创建：users / projects / audit_log_entries / cross_module_conflicts 4 张表，
    通过预先写入的 user/project 记录保证 FK 完整性。
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        tables_to_create = [
            Base.metadata.tables["users"],
            Base.metadata.tables["projects"],
            Base.metadata.tables["audit_log_entries"],
            Base.metadata.tables["cross_module_conflicts"],
        ]
        await conn.run_sync(Base.metadata.create_all, tables=tables_to_create)

    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def user_and_project(db_session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    """预写入 users / projects 各一条，返回 (user_id, project_id)。"""
    from app.models.base import ProjectStatus, UserRole
    from app.models.core import Project, User

    user_id = uuid.uuid4()
    project_id = uuid.uuid4()

    user = User(
        id=user_id,
        username=f"tester-{user_id.hex[:8]}",
        email=f"{user_id.hex[:8]}@test.local",
        hashed_password="hashed",
        role=UserRole.auditor,
        is_active=True,
    )
    project = Project(
        id=project_id,
        name="测试项目",
        client_name="测试客户",
        status=ProjectStatus.execution,
    )
    db_session.add(user)
    db_session.add(project)
    await db_session.commit()
    return user_id, project_id


def _make_enqueue_kwargs(
    project_id: uuid.UUID,
    *,
    user_id: uuid.UUID | None = None,
    source_module: str = "workpaper",
    source_id: uuid.UUID | None = None,
    target_module: str = "disclosure",
    target_id: uuid.UUID | None = None,
    target_field: str = "narrative_p3",
    upstream_value: str | None = "新值-上游",
    manual_value: str | None = "原值-手工覆盖",
    propagation_origin: str = "user_edit",
) -> dict:
    return {
        "project_id": project_id,
        "source_module": source_module,
        "source_id": source_id or uuid.uuid4(),
        "target_module": target_module,
        "target_id": target_id or uuid.uuid4(),
        "target_field": target_field,
        "upstream_value": upstream_value,
        "manual_value": manual_value,
        "user_id": user_id,
        "propagation_origin": propagation_origin,
    }


# ---------------------------------------------------------------------------
# enqueue
# ---------------------------------------------------------------------------


class TestEnqueue:
    """enqueue() 入队 pending 冲突 + 写审计 + emit SSE 事件。"""

    @pytest.mark.asyncio
    async def test_enqueue_pending(
        self, db_session: AsyncSession, user_and_project
    ):
        user_id, project_id = user_and_project
        conflict = await svc.enqueue(
            db=db_session, **_make_enqueue_kwargs(project_id, user_id=user_id)
        )
        await db_session.commit()

        assert isinstance(conflict.id, uuid.UUID)
        assert conflict.project_id == project_id
        assert conflict.status == "pending"
        assert conflict.resolution is None
        assert conflict.final_value is None
        assert conflict.resolved_by is None
        assert conflict.resolved_at is None
        assert conflict.upstream_value == "新值-上游"
        assert conflict.manual_value == "原值-手工覆盖"
        assert conflict.source_module == "workpaper"
        assert conflict.target_module == "disclosure"

    @pytest.mark.asyncio
    async def test_enqueue_writes_audit(
        self, db_session: AsyncSession, user_and_project
    ):
        user_id, project_id = user_and_project
        conflict = await svc.enqueue(
            db=db_session, **_make_enqueue_kwargs(project_id, user_id=user_id)
        )
        await db_session.commit()

        result = await db_session.execute(
            select(AuditLogEntry).where(
                AuditLogEntry.object_type == "cross_module_conflict"
            )
        )
        entries = list(result.scalars().all())
        assert len(entries) == 1
        entry = entries[0]
        assert entry.action_type == "conflict_enqueue"
        assert entry.object_id == conflict.id
        payload = entry.payload or {}
        assert payload.get("event_type") == "cross_module_conflict_enqueued"
        assert payload.get("conflict_id") == str(conflict.id)
        assert payload.get("source_module") == "workpaper"
        assert payload.get("target_module") == "disclosure"
        # project_id 由 append_audit_log 自动注入
        assert payload.get("project_id") == str(project_id)

    @pytest.mark.asyncio
    async def test_enqueue_emits_sse_event(
        self, db_session: AsyncSession, user_and_project
    ):
        user_id, project_id = user_and_project
        with patch(
            "app.services.event_bus.event_bus.broadcast_raw"
        ) as mock_broadcast:
            await svc.enqueue(
                db=db_session, **_make_enqueue_kwargs(project_id, user_id=user_id)
            )
            await db_session.commit()

        assert mock_broadcast.call_count == 1
        args, _ = mock_broadcast.call_args
        assert args[0] == "cross_module_conflict.enqueued"
        extra = args[1]
        assert "conflict_id" in extra
        assert extra["project_id"] == str(project_id)
        assert extra["source_module"] == "workpaper"
        assert extra["target_module"] == "disclosure"


# ---------------------------------------------------------------------------
# resolve
# ---------------------------------------------------------------------------


class TestResolve:
    """resolve() 三种 resolution + 异常分支。"""

    @pytest.mark.asyncio
    async def test_resolve_keep_manual(
        self, db_session: AsyncSession, user_and_project
    ):
        user_id, project_id = user_and_project
        conflict = await svc.enqueue(
            db=db_session, **_make_enqueue_kwargs(project_id, user_id=user_id)
        )
        await db_session.commit()

        resolver_id = uuid.uuid4()
        resolved = await svc.resolve(
            db=db_session,
            conflict_id=conflict.id,
            user_id=resolver_id,
            resolution="keep_manual",
        )
        await db_session.commit()

        assert resolved.id == conflict.id
        assert resolved.status == "resolved"
        assert resolved.resolution == "keep_manual"
        assert resolved.final_value == "原值-手工覆盖"
        assert resolved.resolved_by == resolver_id
        assert isinstance(resolved.resolved_at, datetime)

    @pytest.mark.asyncio
    async def test_resolve_accept_new(
        self, db_session: AsyncSession, user_and_project
    ):
        user_id, project_id = user_and_project
        conflict = await svc.enqueue(
            db=db_session, **_make_enqueue_kwargs(project_id, user_id=user_id)
        )
        await db_session.commit()

        resolved = await svc.resolve(
            db=db_session,
            conflict_id=conflict.id,
            user_id=user_id,
            resolution="accept_new",
        )
        await db_session.commit()

        assert resolved.resolution == "accept_new"
        assert resolved.final_value == "新值-上游"
        assert resolved.status == "resolved"

    @pytest.mark.asyncio
    async def test_resolve_merge_with_value(
        self, db_session: AsyncSession, user_and_project
    ):
        user_id, project_id = user_and_project
        conflict = await svc.enqueue(
            db=db_session, **_make_enqueue_kwargs(project_id, user_id=user_id)
        )
        await db_session.commit()

        merge_text = "审计师人工合并：上游+手工取并集"
        resolved = await svc.resolve(
            db=db_session,
            conflict_id=conflict.id,
            user_id=user_id,
            resolution="merge",
            merge_value=merge_text,
        )
        await db_session.commit()

        assert resolved.resolution == "merge"
        assert resolved.final_value == merge_text
        assert resolved.status == "resolved"

    @pytest.mark.asyncio
    async def test_resolve_merge_without_value_raises(
        self, db_session: AsyncSession, user_and_project
    ):
        user_id, project_id = user_and_project
        conflict = await svc.enqueue(
            db=db_session, **_make_enqueue_kwargs(project_id, user_id=user_id)
        )
        await db_session.commit()

        with pytest.raises(svc.ConflictMergeValueRequiredError, match="merge_value"):
            await svc.resolve(
                db=db_session,
                conflict_id=conflict.id,
                user_id=user_id,
                resolution="merge",
                merge_value=None,
            )

        # 校验 conflict 状态没被错误改写
        await db_session.rollback()
        result = await db_session.execute(
            select(CrossModuleConflict).where(
                CrossModuleConflict.id == conflict.id
            )
        )
        unchanged = result.scalar_one()
        assert unchanged.status == "pending"
        assert unchanged.resolution is None

    @pytest.mark.asyncio
    async def test_resolve_invalid_resolution_raises(
        self, db_session: AsyncSession, user_and_project
    ):
        user_id, project_id = user_and_project
        conflict = await svc.enqueue(
            db=db_session, **_make_enqueue_kwargs(project_id, user_id=user_id)
        )
        await db_session.commit()

        with pytest.raises(ValueError, match="resolution"):
            await svc.resolve(
                db=db_session,
                conflict_id=conflict.id,
                user_id=user_id,
                resolution="not-a-valid-resolution",  # type: ignore[arg-type]
            )

    @pytest.mark.asyncio
    async def test_resolve_already_resolved_raises(
        self, db_session: AsyncSession, user_and_project
    ):
        user_id, project_id = user_and_project
        conflict = await svc.enqueue(
            db=db_session, **_make_enqueue_kwargs(project_id, user_id=user_id)
        )
        await db_session.commit()
        await svc.resolve(
            db=db_session,
            conflict_id=conflict.id,
            user_id=user_id,
            resolution="keep_manual",
        )
        await db_session.commit()

        with pytest.raises(svc.ConflictAlreadyResolvedError, match="已调解"):
            await svc.resolve(
                db=db_session,
                conflict_id=conflict.id,
                user_id=user_id,
                resolution="accept_new",
            )

    @pytest.mark.asyncio
    async def test_resolve_not_found_raises(
        self, db_session: AsyncSession, user_and_project
    ):
        with pytest.raises(svc.ConflictNotFoundError, match="不存在"):
            await svc.resolve(
                db=db_session,
                conflict_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                resolution="keep_manual",
            )


# ---------------------------------------------------------------------------
# auto_resolve_system_recompute
# ---------------------------------------------------------------------------


class TestAutoResolveSystemRecompute:
    @pytest.mark.asyncio
    async def test_auto_resolve_writes_resolved_record(
        self, db_session: AsyncSession, user_and_project
    ):
        _, project_id = user_and_project
        conflict = await svc.auto_resolve_system_recompute(
            db=db_session,
            project_id=project_id,
            source_module="trial_balance",
            source_id=uuid.uuid4(),
            target_module="report",
            target_id=uuid.uuid4(),
            target_field="cells.A1",
            new_value="自动重算后的新值",
            manual_value="原手工值",
            user_id=None,  # 系统行为
        )
        await db_session.commit()

        assert conflict.status == "resolved"
        assert conflict.resolution == "accept_new"
        assert conflict.final_value == "自动重算后的新值"
        assert conflict.upstream_value == "自动重算后的新值"
        assert conflict.manual_value == "原手工值"
        assert isinstance(conflict.resolved_at, datetime)

    @pytest.mark.asyncio
    async def test_auto_resolve_writes_audit_with_system_auto_label(
        self, db_session: AsyncSession, user_and_project
    ):
        _, project_id = user_and_project
        conflict = await svc.auto_resolve_system_recompute(
            db=db_session,
            project_id=project_id,
            source_module="trial_balance",
            source_id=uuid.uuid4(),
            target_module="report",
            target_id=uuid.uuid4(),
            target_field="cells.A1",
            new_value="新值",
            user_id=None,
        )
        await db_session.commit()

        result = await db_session.execute(
            select(AuditLogEntry).where(
                AuditLogEntry.object_id == conflict.id
            )
        )
        entries = list(result.scalars().all())
        assert len(entries) == 1
        payload = entries[0].payload or {}
        assert payload.get("event_type") == "cross_module_conflict_resolved"
        assert payload.get("resolution") == "system_auto"
        # user_id=None 时 audit_log.user_id 为 NULL（系统行为）
        assert entries[0].user_id is None


# ---------------------------------------------------------------------------
# list / count
# ---------------------------------------------------------------------------


class TestListAndCount:
    @pytest.mark.asyncio
    async def test_list_pending_filters_only_pending(
        self, db_session: AsyncSession, user_and_project
    ):
        user_id, project_id = user_and_project
        # 写 3 条 pending
        pending_ids = []
        for _ in range(3):
            c = await svc.enqueue(
                db=db_session,
                **_make_enqueue_kwargs(project_id, user_id=user_id),
            )
            pending_ids.append(c.id)
        # 1 条已调解
        c_done = await svc.enqueue(
            db=db_session, **_make_enqueue_kwargs(project_id, user_id=user_id)
        )
        await db_session.commit()
        await svc.resolve(
            db=db_session,
            conflict_id=c_done.id,
            user_id=user_id,
            resolution="keep_manual",
        )
        await db_session.commit()

        rows = await svc.list_pending(db=db_session, project_id=project_id)
        assert len(rows) == 3
        assert {r.id for r in rows} == set(pending_ids)
        assert all(r.status == "pending" for r in rows)

    @pytest.mark.asyncio
    async def test_list_pending_filters_by_project(
        self, db_session: AsyncSession, user_and_project
    ):
        user_id, project_id = user_and_project
        # 第二个项目
        from app.models.base import ProjectStatus
        from app.models.core import Project

        other_project_id = uuid.uuid4()
        db_session.add(
            Project(
                id=other_project_id,
                name="项目2",
                client_name="客户2",
                status=ProjectStatus.execution,
            )
        )
        await db_session.commit()

        await svc.enqueue(
            db=db_session, **_make_enqueue_kwargs(project_id, user_id=user_id)
        )
        await svc.enqueue(
            db=db_session,
            **_make_enqueue_kwargs(other_project_id, user_id=user_id),
        )
        await db_session.commit()

        rows = await svc.list_pending(db=db_session, project_id=project_id)
        assert len(rows) == 1
        assert rows[0].project_id == project_id

    @pytest.mark.asyncio
    async def test_list_by_project_status_filter(
        self, db_session: AsyncSession, user_and_project
    ):
        user_id, project_id = user_and_project
        c1 = await svc.enqueue(
            db=db_session, **_make_enqueue_kwargs(project_id, user_id=user_id)
        )
        c2 = await svc.enqueue(
            db=db_session, **_make_enqueue_kwargs(project_id, user_id=user_id)
        )
        await db_session.commit()
        await svc.resolve(
            db=db_session,
            conflict_id=c2.id,
            user_id=user_id,
            resolution="accept_new",
        )
        await db_session.commit()

        pending = await svc.list_by_project(
            db=db_session, project_id=project_id, status="pending"
        )
        assert {r.id for r in pending} == {c1.id}

        resolved = await svc.list_by_project(
            db=db_session, project_id=project_id, status="resolved"
        )
        assert {r.id for r in resolved} == {c2.id}

    @pytest.mark.asyncio
    async def test_list_by_project_target_module_filter(
        self, db_session: AsyncSession, user_and_project
    ):
        user_id, project_id = user_and_project
        await svc.enqueue(
            db=db_session,
            **_make_enqueue_kwargs(
                project_id, user_id=user_id, target_module="disclosure"
            ),
        )
        await svc.enqueue(
            db=db_session,
            **_make_enqueue_kwargs(
                project_id, user_id=user_id, target_module="report"
            ),
        )
        await svc.enqueue(
            db=db_session,
            **_make_enqueue_kwargs(
                project_id, user_id=user_id, target_module="report"
            ),
        )
        await db_session.commit()

        disclosures = await svc.list_by_project(
            db=db_session, project_id=project_id, target_module="disclosure"
        )
        assert len(disclosures) == 1
        assert disclosures[0].target_module == "disclosure"

        reports = await svc.list_by_project(
            db=db_session, project_id=project_id, target_module="report"
        )
        assert len(reports) == 2
        assert all(r.target_module == "report" for r in reports)

    @pytest.mark.asyncio
    async def test_list_by_project_invalid_status_raises(
        self, db_session: AsyncSession, user_and_project
    ):
        _, project_id = user_and_project
        with pytest.raises(ValueError, match="status"):
            await svc.list_by_project(
                db=db_session, project_id=project_id, status="not-a-status"
            )

    @pytest.mark.asyncio
    async def test_count_pending(
        self, db_session: AsyncSession, user_and_project
    ):
        user_id, project_id = user_and_project
        # 0 时返回 0
        assert (
            await svc.count_pending(db=db_session, project_id=project_id)
        ) == 0

        # 写 4 条 pending；调解 2 条；剩 2 条
        cs = []
        for _ in range(4):
            cs.append(
                await svc.enqueue(
                    db=db_session,
                    **_make_enqueue_kwargs(project_id, user_id=user_id),
                )
            )
        await db_session.commit()
        await svc.resolve(
            db=db_session,
            conflict_id=cs[0].id,
            user_id=user_id,
            resolution="keep_manual",
        )
        await svc.resolve(
            db=db_session,
            conflict_id=cs[1].id,
            user_id=user_id,
            resolution="accept_new",
        )
        await db_session.commit()

        count = await svc.count_pending(db=db_session, project_id=project_id)
        assert count == 2

        # auto_resolve 写入的记录直接 resolved，不进 pending
        await svc.auto_resolve_system_recompute(
            db=db_session,
            project_id=project_id,
            source_module="trial_balance",
            source_id=uuid.uuid4(),
            target_module="report",
            target_id=uuid.uuid4(),
            target_field="cells.B2",
            new_value="自动",
        )
        await db_session.commit()
        count_after_auto = await svc.count_pending(
            db=db_session, project_id=project_id
        )
        assert count_after_auto == 2  # auto_resolve 不影响 pending 计数


# ---------------------------------------------------------------------------
# 综合：每次状态变更都写一条审计
# ---------------------------------------------------------------------------


class TestAuditLog:
    @pytest.mark.asyncio
    async def test_audit_log_for_each_action(
        self, db_session: AsyncSession, user_and_project
    ):
        """enqueue / resolve / auto_resolve 各写一条审计，共 3 条。"""
        user_id, project_id = user_and_project

        c1 = await svc.enqueue(
            db=db_session, **_make_enqueue_kwargs(project_id, user_id=user_id)
        )
        await db_session.commit()
        await svc.resolve(
            db=db_session,
            conflict_id=c1.id,
            user_id=user_id,
            resolution="accept_new",
        )
        await svc.auto_resolve_system_recompute(
            db=db_session,
            project_id=project_id,
            source_module="trial_balance",
            source_id=uuid.uuid4(),
            target_module="report",
            target_id=uuid.uuid4(),
            target_field="cells.A1",
            new_value="自动",
            user_id=None,
        )
        await db_session.commit()

        result = await db_session.execute(
            select(AuditLogEntry).where(
                AuditLogEntry.object_type == "cross_module_conflict"
            )
        )
        entries = list(result.scalars().all())
        # enqueue + resolve + auto_resolve = 3 条
        assert len(entries) == 3

        action_types = sorted(e.action_type for e in entries)
        assert action_types == [
            "conflict_enqueue",
            "conflict_resolve",
            "conflict_resolve",
        ]

        # event_type 验证
        event_types = sorted((e.payload or {}).get("event_type") for e in entries)
        assert event_types == [
            "cross_module_conflict_enqueued",
            "cross_module_conflict_resolved",
            "cross_module_conflict_resolved",
        ]

        # resolved 审计 details 必须含 5 字段（schema 强制）
        for e in entries:
            payload = e.payload or {}
            if payload.get("event_type") == "cross_module_conflict_resolved":
                assert "conflict_id" in payload
                assert "resolution" in payload
                assert "upstream_value" in payload
                assert "manual_value" in payload
                assert "final_value" in payload
