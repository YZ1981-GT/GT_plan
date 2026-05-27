"""manual_override 联动守卫 Hook 单测 — V3 收官增强 Req 7.2

覆盖以下用例：

- _check_manual_override_before_propagate
  · test_check_returns_allow_when_no_manual_override        无 override → allow
  · test_check_returns_block_enqueued_when_user_edit_with_override   user_edit + override → 入队 + block
  · test_check_returns_auto_resolved_when_system_recompute_with_override  system_recompute → auto_resolve

- wp_disclosure_sync_service.sync_from_workpaper hook 注入
  · test_wp_disclosure_sync_skips_table_data_when_blocked   user_edit + override → table_data 不更新
  · test_wp_disclosure_sync_updates_when_no_override        无 override → 正常更新

- cross_ref_service.CrossRefService.propagate_with_manual_override_check
  · test_cross_ref_service_propagate_with_override_returns_block
  · test_cross_ref_service_propagate_without_override_returns_allow
  · test_cross_ref_service_detect_target_manual_override_helper

Validates: Requirements 7.2（AC 1/2/6/7）
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.sql.elements import BinaryExpression, BindParameter, BooleanClauseList

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
from app.models.core import User, UserRole  # noqa: E402
from app.models.report_models import DisclosureNote  # noqa: E402
from app.models.v3_refinement_models import CrossModuleConflict  # noqa: E402
from app.services import conflict_resolution_service as crs  # noqa: E402
from app.services.cross_ref_service import (  # noqa: E402
    CrossRefChange,
    CrossRefService,
)
from app.services.wp_disclosure_sync_service import sync_from_workpaper  # noqa: E402


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


# ---------------------------------------------------------------------------
# Fixtures: 真实 SQLite 内存库（用于 hook 直接调用 + 审计写入）
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """SQLite 内存库，建 users / projects / audit_log_entries / cross_module_conflicts 4 表。"""
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
    """预写入 users / projects 各一条。"""
    from app.models.base import ProjectStatus
    from app.models.core import Project

    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    db_session.add(
        User(
            id=user_id,
            username=f"tester-{user_id.hex[:8]}",
            email=f"{user_id.hex[:8]}@test.local",
            hashed_password="hashed",
            role=UserRole.auditor,
            is_active=True,
        )
    )
    from app.models.core import Project

    db_session.add(
        Project(
            id=project_id,
            name="测试项目",
            client_name="测试客户",
            status=ProjectStatus.execution,
        )
    )
    await db_session.commit()
    return user_id, project_id


# ---------------------------------------------------------------------------
# Section 1：_check_manual_override_before_propagate hook 三态返回值
# ---------------------------------------------------------------------------


class TestCheckManualOverrideHook:
    """直接调 hook 验证三态返回值 + 副作用。"""

    @pytest.mark.asyncio
    async def test_check_returns_allow_when_no_manual_override(
        self, db_session: AsyncSession, user_and_project
    ):
        user_id, project_id = user_and_project
        decision = await crs._check_manual_override_before_propagate(
            db=db_session,
            project_id=project_id,
            source_module="workpaper",
            source_id=uuid.uuid4(),
            target_module="disclosure",
            target_id=uuid.uuid4(),
            target_field="narrative_p3",
            new_value="新值",
            current_value="旧值",
            is_manual_override=False,
            user_id=user_id,
            propagation_origin="user_edit",
        )
        await db_session.commit()
        assert decision == "allow"
        # 无副作用：不应写入 cross_module_conflicts 表
        rows = (
            await db_session.execute(select(CrossModuleConflict))
        ).scalars().all()
        assert len(list(rows)) == 0
        # 也不应写入 audit_log
        audit_rows = (
            await db_session.execute(
                select(AuditLogEntry).where(
                    AuditLogEntry.object_type == "cross_module_conflict"
                )
            )
        ).scalars().all()
        assert len(list(audit_rows)) == 0

    @pytest.mark.asyncio
    async def test_check_returns_block_enqueued_when_user_edit_with_override(
        self, db_session: AsyncSession, user_and_project
    ):
        """user_edit + manual_override → 入队 pending 冲突，调用方需 abort 写入。"""
        user_id, project_id = user_and_project
        decision = await crs._check_manual_override_before_propagate(
            db=db_session,
            project_id=project_id,
            source_module="workpaper",
            source_id=uuid.uuid4(),
            target_module="disclosure",
            target_id=uuid.uuid4(),
            target_field="narrative_p3",
            new_value="上游新值",
            current_value="原值-手工覆盖",
            is_manual_override=True,
            user_id=user_id,
            propagation_origin="user_edit",
        )
        await db_session.commit()
        assert decision == "block_enqueued"

        # 应写入一条 pending cross_module_conflict
        rows = list(
            (
                await db_session.execute(select(CrossModuleConflict))
            ).scalars().all()
        )
        assert len(rows) == 1
        c = rows[0]
        assert c.status == "pending"
        assert c.resolution is None
        assert c.upstream_value == "上游新值"
        assert c.manual_value == "原值-手工覆盖"
        assert c.target_field == "narrative_p3"

        # 应写入一条审计：event_type=cross_module_conflict_enqueued
        audit_rows = list(
            (
                await db_session.execute(
                    select(AuditLogEntry).where(
                        AuditLogEntry.object_type == "cross_module_conflict"
                    )
                )
            ).scalars().all()
        )
        assert len(audit_rows) == 1
        payload = audit_rows[0].payload or {}
        assert payload.get("event_type") == "cross_module_conflict_enqueued"

    @pytest.mark.asyncio
    async def test_check_returns_auto_resolved_when_system_recompute_with_override(
        self, db_session: AsyncSession, user_and_project
    ):
        """system_recompute + manual_override → 直接 auto_resolve 留痕，调用方继续写入。"""
        user_id, project_id = user_and_project
        decision = await crs._check_manual_override_before_propagate(
            db=db_session,
            project_id=project_id,
            source_module="trial_balance",
            source_id=uuid.uuid4(),
            target_module="report",
            target_id=uuid.uuid4(),
            target_field="cells.A1",
            new_value="重算后新值",
            current_value="原值-手工",
            is_manual_override=True,
            user_id=user_id,  # 即使有 user_id，propagation_origin='system_recompute' 仍 auto
            propagation_origin="system_recompute",
        )
        await db_session.commit()
        assert decision == "auto_resolved"

        # 应写入一条 status='resolved' 的记录（resolution='accept_new'）
        rows = list(
            (
                await db_session.execute(select(CrossModuleConflict))
            ).scalars().all()
        )
        assert len(rows) == 1
        c = rows[0]
        assert c.status == "resolved"
        assert c.resolution == "accept_new"
        assert c.final_value == "重算后新值"
        assert c.upstream_value == "重算后新值"
        assert c.manual_value == "原值-手工"

        # 审计 resolution_label='system_auto'
        audit_rows = list(
            (
                await db_session.execute(
                    select(AuditLogEntry).where(
                        AuditLogEntry.object_type == "cross_module_conflict"
                    )
                )
            ).scalars().all()
        )
        assert len(audit_rows) == 1
        payload = audit_rows[0].payload or {}
        assert payload.get("event_type") == "cross_module_conflict_resolved"
        assert payload.get("resolution") == "system_auto"


# ---------------------------------------------------------------------------
# Section 2：wp_disclosure_sync_service.sync_from_workpaper hook 注入
# ---------------------------------------------------------------------------


def _extract_filters(stmt: Any) -> dict[str, Any]:
    """从 SQLAlchemy select stmt 的 WHERE 子句提取 BindParameter 值。"""
    filters: dict[str, Any] = {}
    where = stmt.whereclause
    if where is None:
        return filters
    if isinstance(where, BooleanClauseList):
        children = list(where.clauses)
    else:
        children = [where]
    for clause in children:
        if not isinstance(clause, BinaryExpression):
            continue
        col_name = (
            getattr(clause.left, "key", None)
            or getattr(clause.left, "name", None)
        )
        right = clause.right
        if isinstance(right, BindParameter):
            filters[col_name] = right.value
    return filters


class _DiscFakeDB:
    """轻量内存版 AsyncSession：供 sync_from_workpaper 用。

    在 disclosure_notes 路径之外，hook 内部会调用 enqueue/auto_resolve_system_recompute，
    它们也会通过 db.add / db.flush / select(...) 路径触达本 FakeDB；
    本 FakeDB 把 insert 累积到 self.adds_by_table，不做实际查询返回。
    """

    def __init__(self, preset_note: DisclosureNote | None = None) -> None:
        self.preset_note = preset_note
        self.commits = 0
        self.flushes = 0
        self.added_objects: list[Any] = []
        # hook 调用 _get_prev_hash → select(AuditLogEntry.entry_hash)，需返回 None
        # 用一个 default scalar_one_or_none=None 的 result 兜底

    async def execute(self, stmt: Any) -> Any:
        # disclosure_notes 路径：根据 (project_id, year, note_section) 匹配 preset_note
        try:
            filters = _extract_filters(stmt)
        except Exception:
            filters = {}
        result = MagicMock()
        if (
            self.preset_note is not None
            and filters.get("note_section") is not None
            and filters.get("note_section") == self.preset_note.note_section
            and filters.get("project_id") == self.preset_note.project_id
            and filters.get("year") == self.preset_note.year
        ):
            result.scalar_one_or_none = MagicMock(
                return_value=self.preset_note
            )
            result.scalar_one = MagicMock(return_value=self.preset_note)
        else:
            result.scalar_one_or_none = MagicMock(return_value=None)
            result.scalar_one = MagicMock(return_value=None)

        def _scalars():
            inner = MagicMock()
            inner.all = MagicMock(return_value=[])
            return inner

        result.scalars = MagicMock(side_effect=_scalars)
        return result

    def add(self, obj: Any) -> None:
        self.added_objects.append(obj)

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:  # pragma: no cover - 测试不触发
        pass

    async def flush(self) -> None:
        self.flushes += 1


def _make_admin() -> User:
    return User(
        id=uuid.uuid4(),
        username="hook-tester",
        email="hook@test.local",
        hashed_password="x",
        role=UserRole.admin,
        is_active=True,
        is_deleted=False,
    )


def _build_existing_note(
    project_id: uuid.UUID,
    *,
    table_data: dict | None,
) -> DisclosureNote:
    """构造一条已有 disclosure_notes 记录用于 update 路径。"""
    return DisclosureNote(
        id=uuid.uuid4(),
        project_id=project_id,
        year=2024,
        note_section="五-1-2 应收账款",
        section_title="应收账款",
        table_data=table_data,
        is_deleted=False,
    )


class TestWpDisclosureSyncHook:
    @pytest.mark.asyncio
    async def test_wp_disclosure_sync_skips_table_data_when_blocked(
        self,
    ):
        """user_edit + manual_override → table_data 不更新，blocked_by_manual_override=True。"""
        project_id = uuid.uuid4()
        # 模拟既有 note 已被用户手工覆盖
        original_table = {
            "_manual_override": True,
            "sub_table_data": {"existing_table": [{"name": "原值"}]},
        }
        note = _build_existing_note(project_id, table_data=original_table)
        db = _DiscFakeDB(preset_note=note)

        new_sub = {"updated_table": [{"name": "新值"}]}
        result = await sync_from_workpaper(
            db,  # type: ignore[arg-type]
            project_id,
            wp_id=uuid.uuid4(),
            sheet_name="ARSheet",
            section_id="五-1-2 应收账款",
            sub_table_data=new_sub,
            current_standard="listed_standalone",
            user=_make_admin(),
            year=2024,
            propagation_origin="user_edit",
        )

        # 关键断言：table_data 未被覆盖
        assert result["blocked_by_manual_override"] is True
        assert result["created"] is False
        assert result["rows_synced"] == 0
        assert note.table_data is original_table  # 引用未替换
        assert note.table_data["sub_table_data"] == {
            "existing_table": [{"name": "原值"}]
        }
        # last_sync_at 仍被记录（说明同步尝试过）
        assert note.last_sync_at is not None
        assert note.last_sync_source == "workpaper"

    @pytest.mark.asyncio
    async def test_wp_disclosure_sync_updates_when_no_override(self):
        """无 manual_override → 正常更新 table_data + blocked=False。"""
        project_id = uuid.uuid4()
        original_table = {
            "sub_table_data": {"existing_table": [{"name": "原值"}]},
        }
        note = _build_existing_note(project_id, table_data=original_table)
        db = _DiscFakeDB(preset_note=note)

        new_sub = {"updated_table": [{"name": "新值"}]}
        result = await sync_from_workpaper(
            db,  # type: ignore[arg-type]
            project_id,
            wp_id=uuid.uuid4(),
            sheet_name="ARSheet",
            section_id="五-1-2 应收账款",
            sub_table_data=new_sub,
            current_standard="listed_standalone",
            user=_make_admin(),
            year=2024,
            propagation_origin="user_edit",
        )

        assert result["blocked_by_manual_override"] is False
        assert result["created"] is False
        assert result["rows_synced"] == 1  # 一行
        # table_data 已被替换为新内容
        assert note.table_data["sub_table_data"] == new_sub
        assert note.table_data["_source"] == "workpaper"

    @pytest.mark.asyncio
    async def test_wp_disclosure_sync_updates_when_system_recompute_with_override(
        self,
    ):
        """system_recompute + manual_override → 仍正常更新（auto_resolved），blocked=False。"""
        project_id = uuid.uuid4()
        original_table = {
            "_manual_override": True,
            "sub_table_data": {"existing_table": [{"name": "原值"}]},
        }
        note = _build_existing_note(project_id, table_data=original_table)
        db = _DiscFakeDB(preset_note=note)

        new_sub = {"updated_table": [{"name": "汇率重算后"}]}
        result = await sync_from_workpaper(
            db,  # type: ignore[arg-type]
            project_id,
            wp_id=uuid.uuid4(),
            sheet_name="ARSheet",
            section_id="五-1-2 应收账款",
            sub_table_data=new_sub,
            current_standard="listed_standalone",
            user=_make_admin(),
            year=2024,
            propagation_origin="system_recompute",
        )

        # system_recompute 路径不阻断写入
        assert result["blocked_by_manual_override"] is False
        assert note.table_data["sub_table_data"] == new_sub


# ---------------------------------------------------------------------------
# Section 3：CrossRefService.propagate_with_manual_override_check
# ---------------------------------------------------------------------------


class _FakeWp:
    """模拟 WorkingPaper 实例（仅承载 id + parsed_data）。"""

    def __init__(
        self, parsed_data: dict | None = None, wp_id: UUID | None = None
    ) -> None:
        self.id = wp_id or uuid.uuid4()
        self.parsed_data = parsed_data


class TestCrossRefServicePropagateHook:
    def test_detect_target_manual_override_helper(self):
        """_detect_target_manual_override 三种约定字段位置 + 默认 False。"""
        # 1) parsed_data=None / 缺字段 → False
        assert (
            CrossRefService._detect_target_manual_override(_FakeWp(None), "B5")
            is False
        )
        assert (
            CrossRefService._detect_target_manual_override(_FakeWp({}), "B5")
            is False
        )
        # 2) 顶层布尔
        assert (
            CrossRefService._detect_target_manual_override(
                _FakeWp({"_manual_override": True}), "B5"
            )
            is True
        )
        # 3) cells 集合包含 target_field
        assert (
            CrossRefService._detect_target_manual_override(
                _FakeWp({"_manual_override_cells": ["A1", "B5"]}), "B5"
            )
            is True
        )
        # 4) cells 集合不含 target_field → False
        assert (
            CrossRefService._detect_target_manual_override(
                _FakeWp({"_manual_override_cells": ["A1"]}), "B5"
            )
            is False
        )

    @pytest.mark.asyncio
    async def test_cross_ref_service_propagate_with_override_returns_block(
        self, db_session: AsyncSession, user_and_project
    ):
        """目标 wp 带 manual_override 标记 + user_edit → block_enqueued。"""
        user_id, project_id = user_and_project
        svc = CrossRefService()
        change = CrossRefChange(
            ref_id="REF-001",
            source_wp_code="D2",
            source_sheet="主表",
            target_wp_code="A4",
            target_sheet="附注五-3",
            target_cell="B5",
        )
        target_wp = _FakeWp({"_manual_override_cells": ["B5"]})

        decision = await svc.propagate_with_manual_override_check(
            db=db_session,
            project_id=project_id,
            source_wp_id=uuid.uuid4(),
            change=change,
            target_workpaper=target_wp,
            current_value="手工值",
            new_value="上游新值",
            user_id=user_id,
            propagation_origin="user_edit",
        )
        await db_session.commit()
        assert decision == "block_enqueued"

        # 验证已入队 pending 冲突
        rows = list(
            (
                await db_session.execute(select(CrossModuleConflict))
            ).scalars().all()
        )
        assert len(rows) == 1
        c = rows[0]
        assert c.status == "pending"
        assert c.target_module == "workpaper"
        assert c.target_field == "B5"
        assert c.upstream_value == "上游新值"
        assert c.manual_value == "手工值"

    @pytest.mark.asyncio
    async def test_cross_ref_service_propagate_without_override_returns_allow(
        self, db_session: AsyncSession, user_and_project
    ):
        """目标 wp 无 manual_override → allow，无写入。"""
        user_id, project_id = user_and_project
        svc = CrossRefService()
        change = CrossRefChange(
            ref_id="REF-002",
            source_wp_code="D2",
            source_sheet="主表",
            target_wp_code="A4",
            target_sheet="附注五-3",
            target_cell="B5",
        )
        target_wp = _FakeWp({})  # 无 manual_override

        decision = await svc.propagate_with_manual_override_check(
            db=db_session,
            project_id=project_id,
            source_wp_id=uuid.uuid4(),
            change=change,
            target_workpaper=target_wp,
            current_value="原值",
            new_value="新值",
            user_id=user_id,
            propagation_origin="user_edit",
        )
        await db_session.commit()
        assert decision == "allow"
        # 不应入队冲突
        rows = list(
            (
                await db_session.execute(select(CrossModuleConflict))
            ).scalars().all()
        )
        assert len(rows) == 0

    @pytest.mark.asyncio
    async def test_cross_ref_service_propagate_system_recompute_with_override_auto_resolves(
        self, db_session: AsyncSession, user_and_project
    ):
        """目标 wp 有 manual_override + system_recompute → auto_resolved。"""
        _, project_id = user_and_project
        svc = CrossRefService()
        change = CrossRefChange(
            ref_id="REF-003",
            source_wp_code="D2",
            source_sheet="主表",
            target_wp_code="A4",
            target_sheet="附注五-3",
            target_cell="B5",
        )
        target_wp = _FakeWp({"_manual_override": True})

        decision = await svc.propagate_with_manual_override_check(
            db=db_session,
            project_id=project_id,
            source_wp_id=uuid.uuid4(),
            change=change,
            target_workpaper=target_wp,
            current_value="手工值",
            new_value="重算后",
            user_id=None,
            propagation_origin="system_recompute",
        )
        await db_session.commit()
        assert decision == "auto_resolved"
        rows = list(
            (
                await db_session.execute(select(CrossModuleConflict))
            ).scalars().all()
        )
        assert len(rows) == 1
        assert rows[0].status == "resolved"
        assert rows[0].resolution == "accept_new"
