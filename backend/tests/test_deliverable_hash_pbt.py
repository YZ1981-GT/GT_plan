"""deliverable-center Task 18 — 哈希链防篡改与在线编辑回写边界 属性化测试

Property 31: 哈希链绑定与连续性
Property 32: 篡改检测正确性
Property 33: 在线编辑源数据隔离

后端 PBT 用 Hypothesis，max_examples=5（项目铁律）。
每个 hypothesis 样例建独立内存库（避免 Windows socket 耗尽的 asyncio.run 抖动通过
单一 asyncio.run/样例 + 内存引擎即时 dispose 控制）。
"""

from __future__ import annotations

import asyncio
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace

from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import select
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
from app.models.report_models import AuditReport, CompanyType, OpinionType, ReportStatus
from app.services import deliverable_service as ds_module
from app.services import onlyoffice_callback_service as oo_module
from app.services.audit_log_helper import GENESIS_HASH
from app.services.deliverable_hash_service import DeliverableHashService
from app.services.deliverable_service import DeliverableService
from app.services.onlyoffice_callback_service import OnlyOfficeCallbackService
from app.services.report_snapshot_service import ReportSnapshotService

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
    AuditReport.__table__,
    AuditLogEntry.__table__,
]


async def _seed_project_user(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    suffix = user_id.hex[:8]
    session.add(
        User(
            id=user_id,
            username=f"hash_{suffix}",
            email=f"hash_{suffix}@test.com",
            hashed_password="x",
            role=UserRole.manager,
        )
    )
    await session.flush()
    session.add(
        Project(
            id=project_id,
            name="哈希链测试项目",
            client_name="哈希链测试",
            project_type=ProjectType.annual,
            status=ProjectStatus.reporting,
            created_by=user_id,
        )
    )
    await session.flush()
    return project_id, user_id


def _run_in_isolated_db(coro_factory):
    """为单个 hypothesis 样例建独立内存库 + 临时 STORAGE_ROOT 并运行。"""

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
                with tempfile.TemporaryDirectory() as td:
                    ds_module.STORAGE_ROOT = Path(td)
                    return await coro_factory(session, project_id, user_id, Path(td))
        finally:
            ds_module.STORAGE_ROOT = original_root
            await engine.dispose()

    return asyncio.run(_runner())


async def _make_task_with_versions(
    session: AsyncSession,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    contents: list[bytes],
) -> tuple[WordExportTask, list[WordExportTaskVersion]]:
    """创建一个交付物并为每段内容生成绑定哈希链的版本。"""
    svc = DeliverableService(session)
    task = await svc.create_task(project_id, "audit_report", "soe", user_id)
    await svc.update_status(task.id, WordExportStatus.generating.value)

    versions: list[WordExportTaskVersion] = []
    for content in contents:
        result = await svc.render_and_store(
            task.id,
            docx_bytes=content,
            user_id=user_id,
        )
        assert result.platform_persist_failed is False
        versions.append(result.version)
    return task, versions


# ---------------------------------------------------------------------------
# Property 31: 哈希链绑定与连续性
# ---------------------------------------------------------------------------
# For any 交付物版本序列，每个版本均记录其文件 SHA256 哈希并写入哈希链，
# 且链上每条记录的 prev_hash 等于前一条记录的 entry_hash（首条为创世哈希）。
# Validates: Requirements 15.1, 15.4


@given(
    contents=st.lists(
        st.binary(min_size=1, max_size=48), min_size=1, max_size=4
    ),
)
@settings(max_examples=5, deadline=None)
def test_hash_chain_binding_and_continuity(contents):
    # Feature: audit-report-deliverable-center, Property 31: 哈希链绑定与连续性
    """Property 31: 每个版本绑定文件哈希 + 链条目，链 prev_hash 连续（首条创世）。

    Validates: Requirements 15.1, 15.4
    """

    async def _body(session, project_id, user_id, _tmp_root):
        task, versions = await _make_task_with_versions(
            session, project_id, user_id, contents
        )

        # 15.1：每个版本均记录文件哈希 + 哈希链条目
        for ver in versions:
            assert ver.file_hash, "版本缺少 file_hash"
            assert len(ver.file_hash) == 64, "file_hash 非 SHA256 长度"
            assert ver.hash_chain_entry_id is not None, "版本未绑定哈希链条目"

        # 取该项目链上所有条目，按写入顺序（ts）排列
        rows = await session.execute(
            select(AuditLogEntry)
            .where(AuditLogEntry.action_type == "deliverable_version_hash")
            .order_by(AuditLogEntry.ts.asc())
        )
        entries = list(rows.scalars().all())
        assert len(entries) == len(versions)

        # 15.4：链连续性 —— 首条 prev_hash 为创世哈希，其余等于前一条 entry_hash
        assert entries[0].prev_hash == GENESIS_HASH
        for prev, cur in zip(entries, entries[1:]):
            assert cur.prev_hash == prev.entry_hash

        # 每个版本的 hash_chain_entry_id 确实指向一条链条目，且其 details 记录了该版本文件哈希
        by_id = {e.id: e for e in entries}
        for ver in versions:
            entry = by_id.get(ver.hash_chain_entry_id)
            assert entry is not None
            assert entry.payload.get("file_hash") == ver.file_hash

    _run_in_isolated_db(_body)


# ---------------------------------------------------------------------------
# Property 32: 篡改检测正确性
# ---------------------------------------------------------------------------
# For any 交付物版本，完整性校验通过当且仅当当前文件哈希等于链上记录哈希；
# 文件被篡改时校验返回失败并标识被篡改的版本号。
# Validates: Requirements 15.2, 15.3


@given(
    contents=st.lists(
        st.binary(min_size=1, max_size=48), min_size=1, max_size=4
    ),
    tamper_seed=st.integers(min_value=0, max_value=10_000),
    do_tamper=st.booleans(),
)
@settings(max_examples=5, deadline=None)
def test_tamper_detection_correctness(contents, tamper_seed, do_tamper):
    # Feature: audit-report-deliverable-center, Property 32: 篡改检测正确性
    """Property 32: 校验通过 iff 文件哈希一致；篡改后失败并标识被篡改版本号。

    Validates: Requirements 15.2, 15.3
    """

    async def _body(session, project_id, user_id, _tmp_root):
        task, versions = await _make_task_with_versions(
            session, project_id, user_id, contents
        )
        hash_svc = DeliverableHashService(session)

        # 未篡改：校验必通过（当前文件哈希 == 链上记录哈希）
        clean = await hash_svc.verify_task_integrity(task.id)
        assert clean.valid is True
        assert clean.tampered_versions == []
        assert clean.checked_count == len(versions)

        if not do_tamper:
            return

        # 篡改某一版本文件：写入与原内容必然不同的字节
        target = versions[tamper_seed % len(versions)]
        path = Path(target.file_path)
        original = path.read_bytes()
        tampered = original + b"_TAMPERED_" + bytes([tamper_seed % 256])
        assert tampered != original
        path.write_bytes(tampered)

        result = await hash_svc.verify_task_integrity(task.id)
        # 15.3：校验失败并标识被篡改的版本号
        assert result.valid is False
        assert target.version_no in result.tampered_versions
        # 仅被篡改版本被标记（其余版本文件未动）
        assert set(result.tampered_versions) == {target.version_no}

    _run_in_isolated_db(_body)


# ---------------------------------------------------------------------------
# Property 33: 在线编辑源数据隔离
# ---------------------------------------------------------------------------
# For any 在线编辑操作，编辑仅修改交付物文件副本，对应的源附注/报表/audit_report
# 数据在编辑前后保持不变。
# Validates: Requirements 16.1


@given(
    original_doc=st.binary(min_size=1, max_size=48),
    edited_doc=st.binary(min_size=1, max_size=48),
    year=st.integers(min_value=2018, max_value=2030),
)
@settings(max_examples=5, deadline=None)
def test_online_edit_source_isolation(original_doc, edited_doc, year):
    # Feature: audit-report-deliverable-center, Property 33: 在线编辑源数据隔离
    """Property 33: OnlyOffice 回写仅新建交付物副本版本，源 audit_report 不变。

    Validates: Requirements 16.1
    """

    async def _body(session, project_id, user_id, _tmp_root):
        # 源数据：audit_report（含可被识别的正文/财务数据）
        report = AuditReport(
            project_id=project_id,
            year=year,
            opinion_type=OpinionType.unqualified,
            company_type=CompanyType.non_listed,
            status=ReportStatus.eqcr_approved,
            created_by=user_id,
            paragraphs={"opinion": "源审计意见正文"},
            financial_data={"total_assets": 12345},
            report_body_json={"sections": [{"section_id": "opinion"}]},
        )
        session.add(report)
        await session.flush()
        report_id = report.id
        before_paragraphs = dict(report.paragraphs)
        before_financial = dict(report.financial_data)
        before_body = dict(report.report_body_json)

        # 初始交付物 + 第一个版本
        svc = DeliverableService(session)
        task = await svc.create_task(project_id, "audit_report", "soe", user_id)
        await svc.update_status(task.id, WordExportStatus.generating.value)
        await svc.render_and_store(task.id, docx_bytes=original_doc, user_id=user_id)
        await svc.update_status(task.id, WordExportStatus.editing.value)

        before_version_count = len(await svc.get_version_chain(task.id))

        # mock 底层试算表哈希（避免查 trial_balance）
        orig_tb = ReportSnapshotService._compute_trial_balance_hash

        async def _fake_hash(self, _pid, _year):  # noqa: ANN001
            return "isolation_tb_hash"

        ReportSnapshotService._compute_trial_balance_hash = _fake_hash  # type: ignore[assignment]

        # mock OnlyOffice 下载（httpx）返回编辑后的 docx 字节
        class _FakeResp:
            def __init__(self, content: bytes):
                self.content = content

            def raise_for_status(self) -> None:
                return None

        class _FakeClient:
            def __init__(self, *_a, **_kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_a):
                return False

            async def get(self, _url):
                return _FakeResp(edited_doc)

        orig_httpx = oo_module.httpx
        oo_module.httpx = SimpleNamespace(AsyncClient=_FakeClient)
        try:
            oo_svc = OnlyOfficeCallbackService(session)
            await oo_svc.handle_callback(
                task.id,
                {"status": 2, "url": "http://onlyoffice/edited.docx"},
                user_id=user_id,
                year=year,
            )
        finally:
            oo_module.httpx = orig_httpx
            ReportSnapshotService._compute_trial_balance_hash = orig_tb  # type: ignore[assignment]

        # 回写仅新建交付物副本版本（word_export_task_versions 增加一条）
        after_version_count = len(await svc.get_version_chain(task.id))
        assert after_version_count == before_version_count + 1

        # 16.1：源 audit_report 数据保持不变
        await session.refresh(report)
        refreshed = await session.get(AuditReport, report_id)
        assert refreshed.paragraphs == before_paragraphs
        assert refreshed.financial_data == before_financial
        assert refreshed.report_body_json == before_body

    _run_in_isolated_db(_body)
