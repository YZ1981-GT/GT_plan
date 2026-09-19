"""deliverable-center Task 9 — DeliverableSnapshotService 属性化测试

Property 27: 快照绑定完整性
Property 28: 数据过时检测正确性

后端 PBT 用 Hypothesis，max_examples=5（项目铁律）。
"""

from __future__ import annotations

import asyncio
import tempfile
import uuid
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.audit_log_models import AuditLogEntry
from app.models.base import Base, ProjectStatus, ProjectType, UserRole
from app.models.core import Project, User
from app.models.phase13_models import (
    ReportSnapshot,
    WordExportStatus,
    WordExportTask,
    WordExportTaskVersion,
)
from app.services import deliverable_service as ds_module
from app.services.deliverable_service import DeliverableService
from app.services.deliverable_snapshot_service import DeliverableSnapshotService

# Feature: audit-report-deliverable-center

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if hasattr(SQLiteTypeCompiler, "visit_uuid"):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

_DELIVERABLE_TABLES = [
    User.__table__,
    Project.__table__,
    WordExportTask.__table__,
    WordExportTaskVersion.__table__,
    ReportSnapshot.__table__,
    AuditLogEntry.__table__,
]


async def _seed_project_user(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    suffix = user_id.hex[:8]
    session.add(
        User(
            id=user_id,
            username=f"snap_{suffix}",
            email=f"snap_{suffix}@test.com",
            hashed_password="x",
            role=UserRole.admin,
        )
    )
    await session.flush()
    session.add(
        Project(
            id=project_id,
            name="快照测试项目",
            client_name="快照测试",
            project_type=ProjectType.annual,
            status=ProjectStatus.planning,
            created_by=user_id,
        )
    )
    await session.flush()
    return project_id, user_id


def _run_in_isolated_db(coro_factory, *, with_tmp_root: bool = False):
    """为单个 hypothesis 样例建独立内存库并运行 coro_factory(session, project_id, user_id[, tmp_root])。"""

    async def _runner():
        engine = create_async_engine(TEST_DATABASE_URL, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, tables=_DELIVERABLE_TABLES)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        original_root = ds_module.STORAGE_ROOT
        try:
            async with session_factory() as session:
                project_id, user_id = await _seed_project_user(session)
                await session.commit()
                if with_tmp_root:
                    with tempfile.TemporaryDirectory() as td:
                        ds_module.STORAGE_ROOT = Path(td)
                        return await coro_factory(
                            session, project_id, user_id, Path(td)
                        )
                return await coro_factory(session, project_id, user_id)
        finally:
            ds_module.STORAGE_ROOT = original_root
            await engine.dispose()

    return asyncio.run(_runner())


# ---------------------------------------------------------------------------
# Property 27: 快照绑定完整性
# ---------------------------------------------------------------------------
# For any 成功完成的导出，对应版本记录的 source_snapshot_refs 非空且包含数据快照哈希。
# Validates: Requirements 13.1, 13.2, 19.1


@given(
    doc_type=st.sampled_from(
        ["audit_report", "financial_report", "disclosure_notes"]
    ),
    year=st.integers(min_value=2018, max_value=2030),
    content=st.binary(min_size=1, max_size=64),
)
@settings(max_examples=5, deadline=None)
def test_snapshot_ref_binding_completeness(doc_type, year, content):
    # Feature: audit-report-deliverable-center, Property 27: 快照绑定完整性
    """Property 27: 成功导出后版本记录 source_snapshot_refs 非空且含 tb_hash。

    Validates: Requirements 13.1, 13.2, 19.1
    """

    async def _body(session, project_id, user_id, tmp_root):
        snap_svc = DeliverableSnapshotService(session)

        async def _fake_hash(_pid, _year):
            return "deterministic_tb_hash"

        snap_svc._snap_svc._compute_trial_balance_hash = _fake_hash  # type: ignore[method-assign]

        # capture_snapshot_ref 返回的引用本身必须含非空 tb_hash
        ref = await snap_svc.capture_snapshot_ref(project_id, year, doc_type)
        assert ref.tb_hash
        refs = snap_svc.snapshot_ref_to_dict(ref)
        assert refs.get("tb_hash")

        # 走完整 render_and_store 导出链路，验证版本记录绑定了快照引用
        svc = DeliverableService(session)
        task = await svc.create_task(project_id, doc_type, "soe", user_id)
        await svc.update_status(task.id, WordExportStatus.generating.value)
        result = await svc.render_and_store(
            task.id,
            docx_bytes=content,
            user_id=user_id,
            source_snapshot_refs=refs,
        )

        assert result.platform_persist_failed is False
        version = result.version
        # 版本记录的 source_snapshot_refs 非空且包含数据快照哈希
        assert version.source_snapshot_refs is not None
        assert version.source_snapshot_refs.get("tb_hash") == "deterministic_tb_hash"
        # task 维度也回填了快照引用
        refreshed = await svc.get_task(task.id)
        assert refreshed.source_snapshot_refs is not None
        assert refreshed.source_snapshot_refs.get("tb_hash") == "deterministic_tb_hash"

    _run_in_isolated_db(_body, with_tmp_root=True)


# ---------------------------------------------------------------------------
# Property 28: 数据过时检测正确性
# ---------------------------------------------------------------------------
# For any 交付物版本，预览时返回的 stale 标志为真当且仅当其绑定的快照哈希与
# 当前底层数据哈希不一致。
# Validates: Requirements 13.4, 13.5, 16.2


@given(
    bound_hash=st.text(
        alphabet="0123456789abcdef", min_size=8, max_size=32
    ),
    current_hash=st.text(
        alphabet="0123456789abcdef", min_size=8, max_size=32
    ),
    doc_type=st.sampled_from(
        ["audit_report", "financial_report", "disclosure_notes"]
    ),
    year=st.integers(min_value=2018, max_value=2030),
)
@settings(max_examples=5, deadline=None)
def test_stale_detection_iff_hash_mismatch(
    bound_hash, current_hash, doc_type, year
):
    # Feature: audit-report-deliverable-center, Property 28: 数据过时检测正确性
    """Property 28: stale 为真 当且仅当 绑定快照哈希 != 当前底层数据哈希。

    Validates: Requirements 13.4, 13.5, 16.2
    """

    async def _body(session, project_id, user_id):
        svc = DeliverableService(session)
        task = await svc.create_task(project_id, doc_type, "soe", user_id)
        task.source_snapshot_refs = {
            "tb_hash": bound_hash,
            "year": year,
            "doc_type": doc_type,
        }
        await session.flush()

        snap_svc = DeliverableSnapshotService(session)

        async def _fake_hash(_pid, _year):
            return current_hash

        snap_svc._snap_svc._compute_trial_balance_hash = _fake_hash  # type: ignore[method-assign]

        result = await snap_svc.check_stale(task, year)

        # 当且仅当哈希不一致时 stale 为真
        assert result.stale == (bound_hash != current_hash)
        assert result.bound_tb_hash == bound_hash
        assert result.current_tb_hash == current_hash

    _run_in_isolated_db(_body)


@given(
    doc_type=st.sampled_from(
        ["audit_report", "financial_report", "disclosure_notes"]
    ),
    year=st.integers(min_value=2018, max_value=2030),
)
@settings(max_examples=5, deadline=None)
def test_stale_false_when_no_snapshot_ref(doc_type, year):
    # Feature: audit-report-deliverable-center, Property 28: 数据过时检测正确性
    """Property 28 边界：未绑定快照引用的交付物不判定为过时（无可比基准）。

    Validates: Requirements 13.4, 13.5, 16.2
    """

    async def _body(session, project_id, user_id):
        svc = DeliverableService(session)
        task = await svc.create_task(project_id, doc_type, "soe", user_id)
        # 不设置 source_snapshot_refs
        await session.flush()

        snap_svc = DeliverableSnapshotService(session)
        result = await snap_svc.check_stale(task, year)
        assert result.stale is False

    _run_in_isolated_db(_body)
