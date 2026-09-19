# Feature: audit-report-deliverable-center, Property 21: 打包内容为各类最新 confirmed 版本
# Feature: audit-report-deliverable-center, Property 22: 打包结构与清单完整
# Feature: audit-report-deliverable-center, Property 56: 打包进度单调递增
"""deliverable-center Task 20 — 打包下载异步化与进度 属性化测试

Property 21: 打包内容为各类最新 confirmed 版本
Property 22: 打包结构与清单完整
Property 56: 打包进度单调递增

后端 PBT 用 Hypothesis，max_examples=5（项目铁律）。
为每个 hypothesis 样例建独立内存 SQLite DB，避免跨样例状态污染。
"""

from __future__ import annotations

import asyncio
import tempfile
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.base import Base, ProjectStatus, ProjectType, UserRole
from app.models.core import Project, User
from app.models.phase13_models import (
    ExportJob,
    ExportJobItem,
    WordExportDocType,
    WordExportStatus,
    WordExportTask,
    WordExportTaskVersion,
)

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
    ExportJob.__table__,
    ExportJobItem.__table__,
]

DOC_TYPES = [
    WordExportDocType.audit_report.value,
    WordExportDocType.financial_report.value,
    WordExportDocType.disclosure_notes.value,
]


async def _seed_project_user(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    suffix = user_id.hex[:8]
    session.add(
        User(
            id=user_id,
            username=f"pkg_{suffix}",
            email=f"pkg_{suffix}@test.com",
            hashed_password="x",
            role=UserRole.manager,
        )
    )
    await session.flush()
    session.add(
        Project(
            id=project_id,
            name="打包测试项目",
            client_name="打包测试",
            project_type=ProjectType.annual,
            status=ProjectStatus.reporting,
            created_by=user_id,
        )
    )
    await session.flush()
    return project_id, user_id


def _run_in_isolated_db(coro_factory):
    """为单个 hypothesis 样例建独立内存库并运行。"""

    async def _runner():
        engine = create_async_engine(TEST_DATABASE_URL, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, tables=_DELIVERABLE_TABLES)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                project_id, user_id = await _seed_project_user(session)
                await session.commit()
                return await coro_factory(session, project_id, user_id)
        finally:
            await engine.dispose()

    return asyncio.run(_runner())


# ---------------------------------------------------------------------------
# Strategies: 生成带 confirmed 状态交付物的列表
# ---------------------------------------------------------------------------

# 每个 doc_type 可能有多个 confirmed 交付物（不同更新时间），只取最新
@st.composite
def deliverable_set_strategy(draw):
    """生成一组交付物描述 (doc_type, updated_time_offset_minutes, file_content)。
    至少 1 个，最多 6 个，覆盖多个 doc_type 的情况。"""
    n = draw(st.integers(min_value=1, max_value=6))
    items = []
    for i in range(n):
        doc_type = draw(st.sampled_from(DOC_TYPES))
        # 用 offset 代表时间偏移（分钟），便于确定最新
        offset = draw(st.integers(min_value=0, max_value=100))
        content = draw(st.binary(min_size=4, max_size=32))
        items.append((doc_type, offset, content))
    return items


# ---------------------------------------------------------------------------
# Property 21: 打包内容为各类最新 confirmed 版本
# ---------------------------------------------------------------------------
# For any 交付物集合，打包 ZIP 包含且仅包含每个文档类型中状态为 confirmed 的最新版本文件。
# Validates: Requirements 10.1


@given(items=deliverable_set_strategy())
@settings(max_examples=5, deadline=None)
def test_package_contains_only_latest_confirmed_per_doc_type(items):
    """Property 21: 打包 ZIP 仅包含各 doc_type 的最新 confirmed 版本。

    Validates: Requirements 10.1
    """

    async def _inner(session: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID):
        base_time = datetime(2025, 1, 1)  # naive — SQLite 不存储 tz
        tmpdir = tempfile.mkdtemp()

        # 创建交付物 tasks（均为 confirmed），设置不同 updated_at
        created_tasks: list[WordExportTask] = []
        for idx, (doc_type, offset, content) in enumerate(items):
            task_id = uuid.uuid4()
            file_name = f"file_{idx}.docx"
            file_path = Path(tmpdir) / file_name
            file_path.write_bytes(content)

            task = WordExportTask(
                id=task_id,
                project_id=project_id,
                doc_type=doc_type,
                status=WordExportStatus.confirmed.value,
                file_path=str(file_path),
                file_size=len(content),
                created_by=user_id,
                created_at=base_time + timedelta(minutes=offset),
                updated_at=base_time + timedelta(minutes=offset),
            )
            session.add(task)
            created_tasks.append(task)

        await session.flush()
        await session.commit()

        # 计算预期结果：每个 doc_type 中 updated_at 最大的交付物
        expected_by_type: dict[str, WordExportTask] = {}
        for task in created_tasks:
            prev = expected_by_type.get(task.doc_type)
            if prev is None or (task.updated_at or task.created_at) > (
                prev.updated_at or prev.created_at
            ):
                expected_by_type[task.doc_type] = task

        # 执行打包
        from app.services.deliverable_package_service import DeliverablePackageService

        pkg_svc = DeliverablePackageService(session)
        job_id, _ = await pkg_svc.create_package_job(
            project_id, 2025, user_id, ignore_incomplete=True
        )
        await session.commit()

        # mock event_bus to avoid Redis dependency
        mock_bus = MagicMock()
        mock_bus.broadcast_raw = lambda *a, **kw: None
        with patch("app.services.event_bus.event_bus", mock_bus):
            zip_path = await pkg_svc.run_package_job(job_id)
            await session.commit()

        assert zip_path is not None and zip_path.exists()

        # 验证 ZIP 内容
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = [n for n in zf.namelist() if n != "deliverable_manifest.txt"]
            # ZIP 中文件数 == 不同 doc_type 数（每类最新一个）
            assert len(names) == len(expected_by_type), (
                f"ZIP 文件数 {len(names)} != 预期 {len(expected_by_type)}"
            )
            # 每个预期文件必须在 ZIP 中
            for doc_type, task in expected_by_type.items():
                expected_name = f"{doc_type}/{Path(task.file_path).name}"
                assert expected_name in names, (
                    f"ZIP 缺少 {expected_name}, 实际: {names}"
                )
                # 内容校验
                zip_content = zf.read(expected_name)
                original_content = Path(task.file_path).read_bytes()
                assert zip_content == original_content

    _run_in_isolated_db(_inner)


# ---------------------------------------------------------------------------
# Property 22: 打包结构与清单完整
# ---------------------------------------------------------------------------
# For any 打包操作，ZIP 内每个交付物文件位于以其文档类型命名的子目录下，
# 且 ZIP 必含一份列出全部文件名、版本号与状态的清单文件（deliverable_manifest.txt）。
# Validates: Requirements 10.3, 10.4


@given(items=deliverable_set_strategy())
@settings(max_examples=5, deadline=None)
def test_package_structure_and_manifest(items):
    """Property 22: ZIP 子目录按 doc_type 组织且包含 deliverable_manifest.txt 清单。

    Validates: Requirements 10.3, 10.4
    """

    async def _inner(session: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID):
        base_time = datetime(2025, 1, 1)  # naive — SQLite 不存储 tz
        tmpdir = tempfile.mkdtemp()

        # 创建 confirmed 交付物 + 对应 version 记录
        for idx, (doc_type, offset, content) in enumerate(items):
            task_id = uuid.uuid4()
            file_name = f"doc_{idx}.docx"
            file_path = Path(tmpdir) / file_name
            file_path.write_bytes(content)

            task = WordExportTask(
                id=task_id,
                project_id=project_id,
                doc_type=doc_type,
                status=WordExportStatus.confirmed.value,
                file_path=str(file_path),
                file_size=len(content),
                created_by=user_id,
                created_at=base_time + timedelta(minutes=offset),
                updated_at=base_time + timedelta(minutes=offset),
            )
            session.add(task)
            await session.flush()

            # 添加版本记录（打包时会查最新版本号）
            version = WordExportTaskVersion(
                id=uuid.uuid4(),
                word_export_task_id=task_id,
                version_no=1,
                file_path=str(file_path),
                created_by=user_id,
                created_at=base_time + timedelta(minutes=offset),
            )
            session.add(version)

        await session.flush()
        await session.commit()

        from app.services.deliverable_package_service import DeliverablePackageService

        pkg_svc = DeliverablePackageService(session)
        job_id, _ = await pkg_svc.create_package_job(
            project_id, 2025, user_id, ignore_incomplete=True
        )
        await session.commit()

        mock_bus = MagicMock()
        mock_bus.broadcast_raw = lambda *a, **kw: None
        with patch("app.services.event_bus.event_bus", mock_bus):
            zip_path = await pkg_svc.run_package_job(job_id)
            await session.commit()

        assert zip_path is not None and zip_path.exists()

        with zipfile.ZipFile(zip_path, "r") as zf:
            all_names = zf.namelist()

            # 1. manifest 存在
            assert "deliverable_manifest.txt" in all_names, (
                "ZIP 缺少 deliverable_manifest.txt"
            )

            # 2. 所有非 manifest 文件都在 doc_type 子目录下
            data_files = [n for n in all_names if n != "deliverable_manifest.txt"]
            for name in data_files:
                parts = name.split("/")
                assert len(parts) == 2, (
                    f"文件 {name} 未在子目录内（期望 doc_type/filename 格式）"
                )
                doc_type_dir = parts[0]
                assert doc_type_dir in DOC_TYPES or doc_type_dir in (
                    "full_package", "special_report"
                ), f"子目录 {doc_type_dir} 不是合法的 doc_type"

            # 3. manifest 内容包含表头和数据行
            manifest_content = zf.read("deliverable_manifest.txt").decode("utf-8")
            lines = manifest_content.strip().split("\n")
            # 至少有注释行 + project 行 + 表头行
            assert len(lines) >= 3, f"manifest 行数不足: {len(lines)}"
            # 表头含 doc_type/filename/version_no/status/file_size
            header_line = lines[2]
            for field in ["doc_type", "filename", "version_no", "status", "file_size"]:
                assert field in header_line, (
                    f"manifest 表头缺少字段 {field}"
                )
            # 数据行数 == 打包文件数
            data_lines = [l for l in lines[3:] if l.strip()]
            assert len(data_lines) == len(data_files), (
                f"manifest 数据行数 {len(data_lines)} != 文件数 {len(data_files)}"
            )

    _run_in_isolated_db(_inner)


# ---------------------------------------------------------------------------
# Property 56: 打包进度单调递增
# ---------------------------------------------------------------------------
# For any 异步打包任务，通过 SSE 推送的进度值随时间单调不减，
# 并最终到达任务总量（progress_done == progress_total）。
# Validates: Requirements 30.2


@given(items=deliverable_set_strategy())
@settings(max_examples=5, deadline=None)
def test_package_progress_monotonically_increasing(items):
    """Property 56: SSE 进度值单调不减且最终到达总量。

    Validates: Requirements 30.2
    """

    async def _inner(session: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID):
        base_time = datetime(2025, 1, 1)  # naive — SQLite 不存储 tz
        tmpdir = tempfile.mkdtemp()

        # 创建交付物
        for idx, (doc_type, offset, content) in enumerate(items):
            task_id = uuid.uuid4()
            file_name = f"prog_{idx}.docx"
            file_path = Path(tmpdir) / file_name
            file_path.write_bytes(content)

            task = WordExportTask(
                id=task_id,
                project_id=project_id,
                doc_type=doc_type,
                status=WordExportStatus.confirmed.value,
                file_path=str(file_path),
                file_size=len(content),
                created_by=user_id,
                created_at=base_time + timedelta(minutes=offset),
                updated_at=base_time + timedelta(minutes=offset),
            )
            session.add(task)

        await session.flush()
        await session.commit()

        from app.services.deliverable_package_service import DeliverablePackageService

        pkg_svc = DeliverablePackageService(session)
        job_id, _ = await pkg_svc.create_package_job(
            project_id, 2025, user_id, ignore_incomplete=True
        )
        await session.commit()

        # 收集 SSE 进度推送
        progress_events: list[dict] = []

        def _capture_broadcast(event_type: str, extra: dict | None = None):
            if event_type == "deliverable.package.progress":
                progress_events.append(dict(extra or {}))

        mock_bus = MagicMock()
        mock_bus.broadcast_raw = _capture_broadcast
        with patch("app.services.event_bus.event_bus", mock_bus):
            zip_path = await pkg_svc.run_package_job(job_id)
            await session.commit()

        # 验证进度单调不减
        done_values = [e["done"] for e in progress_events]
        for i in range(1, len(done_values)):
            assert done_values[i] >= done_values[i - 1], (
                f"进度非单调递增: {done_values}"
            )

        # 验证最终到达总量
        if zip_path is not None and progress_events:
            total = progress_events[-1]["total"]
            final_done = done_values[-1]
            assert final_done == total, (
                f"最终进度 {final_done} != 总量 {total}"
            )

    _run_in_isolated_db(_inner)
