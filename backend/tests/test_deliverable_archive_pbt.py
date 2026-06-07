# Feature: audit-report-deliverable-center, Property 20: 不齐全则归档被阻止
# Feature: audit-report-deliverable-center, Property 23: 项目归档级联状态一致性
# Feature: audit-report-deliverable-center, Property 24: 归档锁定不变式
# Feature: audit-report-deliverable-center, Property 25: 解除归档权限与留痕
# Feature: audit-report-deliverable-center, Property 53: 项目阶段聚合完结
"""deliverable-center 归档锁定与项目生命周期联动 属性化测试（任务 17.2-17.6）。

后端 PBT 用 Hypothesis，max_examples=5（项目铁律）。
为每个 hypothesis 样例建独立内存库（asyncio.run），避免跨样例状态污染。
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_log_models import AuditLogEntry
from app.models.base import Base, ProjectStatus, ProjectType, UserRole
from app.models.core import Project, User
from app.models.phase13_models import (
    WordExportDocType,
    WordExportStatus,
    WordExportTask,
    WordExportTaskVersion,
)
from app.models.report_models import AuditReport, CompanyType, OpinionType, ReportStatus
from app.services.deliverable_permissions import DeliverableAction, can_deliverable
from app.services.deliverable_service import DeliverableService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if hasattr(SQLiteTypeCompiler, "visit_uuid"):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

_DELIVERABLE_TABLES = [
    User.__table__,
    Project.__table__,
    WordExportTask.__table__,
    WordExportTaskVersion.__table__,
    AuditReport.__table__,
    AuditLogEntry.__table__,
]

_TRIO = [
    WordExportDocType.audit_report.value,
    WordExportDocType.financial_report.value,
    WordExportDocType.disclosure_notes.value,
]

# 推进到各状态所需的 update_status 序列（绕过 EQCR 守卫，直接走状态机）
_PATH_TO: dict[str, list[str]] = {
    "draft": [],
    "generating": ["generating"],
    "generated": ["generating", "generated"],
    "editing": ["generating", "generated", "editing"],
    "confirmed": ["generating", "generated", "editing", "confirmed"],
    "signed": ["generating", "generated", "editing", "confirmed", "signed"],
}


async def _seed_project_user(
    session: AsyncSession, role: UserRole = UserRole.manager
) -> tuple[uuid.UUID, uuid.UUID]:
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    suffix = user_id.hex[:8]
    session.add(
        User(
            id=user_id,
            username=f"arc_{suffix}",
            email=f"arc_{suffix}@test.com",
            hashed_password="x",
            role=role,
        )
    )
    await session.flush()
    session.add(
        Project(
            id=project_id,
            name="归档测试项目",
            client_name="归档测试",
            project_type=ProjectType.annual,
            status=ProjectStatus.reporting,
            created_by=user_id,
        )
    )
    await session.flush()
    return project_id, user_id


def _run_in_isolated_db(coro_factory, *, role: UserRole = UserRole.manager):
    """为单个 hypothesis 样例建独立内存库并运行 coro_factory(session, project_id, user_id)。"""

    async def _runner():
        engine = create_async_engine(TEST_DATABASE_URL, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, tables=_DELIVERABLE_TABLES)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                project_id, user_id = await _seed_project_user(session, role=role)
                await session.commit()
                return await coro_factory(session, project_id, user_id)
        finally:
            await engine.dispose()

    return asyncio.run(_runner())


async def _make_task_at(
    svc: DeliverableService,
    project_id: uuid.UUID,
    doc_type: str,
    user_id: uuid.UUID,
    target_status: str,
    *,
    snapshot_refs: dict | None = None,
) -> WordExportTask:
    """创建任务并通过状态机推进到 target_status（绕过 EQCR）。"""
    task = await svc.create_task(project_id, doc_type, "soe", user_id)
    if snapshot_refs is not None:
        task.source_snapshot_refs = snapshot_refs
        await svc.db.flush()
    for step in _PATH_TO[target_status]:
        await svc.update_status(task.id, step)
    return task


async def _make_complete_project(
    svc: DeliverableService,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    base_status: str = "confirmed",
) -> None:
    """构造一个齐全（三件套 + 至少一 confirmed + 一致快照）的项目以便归档可通过。"""
    snap = {"tb_hash": "HASH_CONSISTENT", "doc_type": "trio", "year": 2024}
    for doc_type in _TRIO:
        task = await _make_task_at(
            svc, project_id, doc_type, user_id, base_status, snapshot_refs=snap
        )
        task.file_path = f"/storage/{doc_type}.docx"
        if doc_type == WordExportDocType.financial_report.value:
            task.selected_sections = ["balance_sheet", "income_statement"]
        await svc.db.flush()


# ---------------------------------------------------------------------------
# Property 20: 不齐全则归档被阻止
# Validates: Requirements 8.4, 11.3
# ---------------------------------------------------------------------------
# For any 不满足完整性的项目，归档操作被阻止（除非用户显式确认绕过 force=True）。


@given(
    # 仅生成部分三件套 → 必然缺失 → 完整性不通过
    present_types=st.lists(
        st.sampled_from(_TRIO), min_size=0, max_size=2, unique=True
    ),
    year=st.integers(min_value=2018, max_value=2030),
)
@settings(max_examples=5, deadline=None)
def test_incomplete_blocks_archive(present_types, year):
    # Feature: audit-report-deliverable-center, Property 20: 不齐全则归档被阻止
    """Property 20: 三件套不齐全时归档被阻止；force=True 时绕过完整性放行。"""

    async def _scenario(session, project_id, user_id):
        svc = DeliverableService(session)
        # 仅创建部分类型且置为 confirmed（保证不是「全 draft」而是真的缺类型）
        for doc_type in present_types:
            task = await _make_task_at(
                svc, project_id, doc_type, user_id, "confirmed"
            )
            task.file_path = f"/storage/{doc_type}.docx"
            await session.flush()

        # 不齐全 → 阻止
        with pytest.raises(ValueError, match="完整性检查未通过"):
            await svc.archive_project_deliverables(project_id, user_id, year)

        # 阻止后不应有任何交付物变为 archived
        archived = await session.execute(
            select(func.count())
            .select_from(WordExportTask)
            .where(
                WordExportTask.project_id == project_id,
                WordExportTask.status == WordExportStatus.archived.value,
            )
        )
        assert archived.scalar_one() == 0

        # force=True 显式绕过完整性 → 不再因完整性抛错
        count = await svc.archive_project_deliverables(
            project_id, user_id, year, force=True
        )
        # force 放行后，已 confirmed 的应被归档
        assert count == len(present_types)

    _run_in_isolated_db(_scenario)


# ---------------------------------------------------------------------------
# Property 23: 项目归档级联状态一致性
# Validates: Requirements 11.1, 27.1, 27.3
# ---------------------------------------------------------------------------
# 执行项目归档后所有 {confirmed, signed} 交付物变为 archived；
# 不存在「项目已归档而仍有 confirmed/signed 交付物」的状态组合。


@given(
    statuses=st.lists(
        st.sampled_from(["editing", "confirmed", "signed"]),
        min_size=1,
        max_size=5,
    ),
    year=st.integers(min_value=2018, max_value=2030),
)
@settings(max_examples=5, deadline=None)
def test_archive_cascade_consistency(statuses, year):
    # Feature: audit-report-deliverable-center, Property 23: 项目归档级联状态一致性
    """Property 23: 归档后 confirmed/signed 全部 → archived，无残留终态。"""

    async def _scenario(session, project_id, user_id):
        svc = DeliverableService(session)
        tasks: list[uuid.UUID] = []
        for i, status in enumerate(statuses):
            # 用不同 doc_type 后缀避免被当成同类型聚合处理
            doc_type = _TRIO[i % len(_TRIO)]
            task = await _make_task_at(svc, project_id, doc_type, user_id, status)
            tasks.append(task.id)

        before_terminal = [s for s in statuses if s in ("confirmed", "signed")]

        # force=True：聚焦验证级联一致性，不受完整性影响
        count = await svc.archive_project_deliverables(
            project_id, user_id, year, force=True
        )
        assert count == len(before_terminal)

        # 原 confirmed/signed 全部变 archived
        for tid, status in zip(tasks, statuses):
            t = await svc.get_task(tid)
            if status in ("confirmed", "signed"):
                assert t.status == WordExportStatus.archived.value
                assert t.archived_at is not None
            else:
                assert t.status == status  # 非终态不动

        # 不变式：不存在「仍有 confirmed/signed」与归档动作并存的残留
        leftover = await session.execute(
            select(func.count())
            .select_from(WordExportTask)
            .where(
                WordExportTask.project_id == project_id,
                WordExportTask.status.in_(
                    [
                        WordExportStatus.confirmed.value,
                        WordExportStatus.signed.value,
                    ]
                ),
            )
        )
        assert leftover.scalar_one() == 0

    _run_in_isolated_db(_scenario)


# ---------------------------------------------------------------------------
# Property 24: 归档锁定不变式
# Validates: Requirements 11.2
# ---------------------------------------------------------------------------
# For any archived 交付物，任何编辑或创建新版本的操作均被拒绝，
# 交付物内容与版本集合保持不变。


@given(
    edit_target=st.sampled_from(
        [
            WordExportStatus.editing.value,
            WordExportStatus.generating.value,
            WordExportStatus.signed.value,
            WordExportStatus.draft.value,
        ]
    ),
    year=st.integers(min_value=2018, max_value=2030),
)
@settings(max_examples=5, deadline=None)
def test_archived_lock_invariant(edit_target, year):
    # Feature: audit-report-deliverable-center, Property 24: 归档锁定不变式
    """Property 24: archived 态拒绝 create_version 与任意编辑状态转换，版本集合不变。"""

    async def _scenario(session, project_id, user_id):
        svc = DeliverableService(session)
        task = await _make_task_at(svc, project_id, "audit_report", user_id, "confirmed")
        # 推进到 archived
        await svc.update_status(task.id, WordExportStatus.archived.value)
        assert (await svc.get_task(task.id)).status == WordExportStatus.archived.value

        # 记录归档前版本集合
        before = await svc.get_version_chain(task.id)
        before_ids = {v.id for v in before}

        # 1) 创建新版本被拒
        with pytest.raises(ValueError, match="已归档"):
            await svc.create_version(
                task.id,
                file_path="/storage/illegal.docx",
                html_path=None,
                user_id=user_id,
            )

        # 2) 任意编辑/再生成状态转换被拒（状态机仅允许 archived→confirmed）
        if edit_target != WordExportStatus.confirmed.value:
            with pytest.raises(ValueError, match="非法状态转换"):
                await svc.update_status(task.id, edit_target)

        # 版本集合与状态保持不变
        after = await svc.get_version_chain(task.id)
        assert {v.id for v in after} == before_ids
        assert (await svc.get_task(task.id)).status == WordExportStatus.archived.value

    _run_in_isolated_db(_scenario)


# ---------------------------------------------------------------------------
# Property 25: 解除归档权限与留痕
# Validates: Requirements 11.4
# ---------------------------------------------------------------------------
# 非 admin 角色被拒绝；admin 角色执行成功并写入一条 archive_unarchive 审计日志。

_NON_ADMIN_ROLES = ["auditor", "qc", "manager", "partner"]


@given(role=st.sampled_from(_NON_ADMIN_ROLES + ["admin"]))
@settings(max_examples=5, deadline=None)
def test_unarchive_permission_matrix(role):
    # Feature: audit-report-deliverable-center, Property 25: 解除归档权限与留痕
    """Property 25（权限部分）：unarchive 仅 admin 允许，其余角色被拒。"""
    allowed = can_deliverable(role, DeliverableAction.unarchive)
    assert allowed == (role == "admin")


@given(reason=st.text(min_size=1, max_size=40))
@settings(max_examples=5, deadline=None)
def test_unarchive_writes_audit_log(reason):
    # Feature: audit-report-deliverable-center, Property 25: 解除归档权限与留痕
    """Property 25（留痕部分）：admin 解除归档成功且写入一条 archive_unarchive 审计日志。"""

    async def _scenario(session, project_id, user_id):
        svc = DeliverableService(session)
        task = await _make_task_at(svc, project_id, "audit_report", user_id, "confirmed")
        await svc.update_status(task.id, WordExportStatus.archived.value)

        before = await session.execute(
            select(func.count()).select_from(AuditLogEntry)
        )
        before_count = before.scalar_one()

        updated = await svc.unarchive(task.id, user_id, reason)
        assert updated.status == WordExportStatus.confirmed.value
        assert updated.archived_at is None

        # 恰好新增一条 archive_unarchive 审计日志
        logs = await session.execute(
            select(AuditLogEntry).where(
                AuditLogEntry.action_type == "deliverable_unarchive"
            )
        )
        entries = list(logs.scalars().all())
        assert len(entries) == 1
        payload = entries[0].payload or {}
        assert payload.get("event_type") == "archive_unarchive"
        assert payload.get("reason") == reason
        assert payload.get("previous_status") == WordExportStatus.archived.value

        after = await session.execute(
            select(func.count()).select_from(AuditLogEntry)
        )
        assert after.scalar_one() == before_count + 1

    _run_in_isolated_db(_scenario)


# ---------------------------------------------------------------------------
# Property 53: 项目阶段聚合完结
# Validates: Requirements 27.2
# ---------------------------------------------------------------------------
# For any 项目，当其全部交付物均为 archived 状态时，完成与报告阶段标记为完结
# （project.status → archived）。


@given(
    n_terminal=st.integers(min_value=1, max_value=3),
    year=st.integers(min_value=2018, max_value=2030),
)
@settings(max_examples=5, deadline=None)
def test_project_phase_aggregation_complete(n_terminal, year):
    # Feature: audit-report-deliverable-center, Property 53: 项目阶段聚合完结
    """Property 53: 全部交付物 archived → 项目阶段标记完结（status=archived）。"""

    async def _scenario(session, project_id, user_id):
        svc = DeliverableService(session)
        for i in range(n_terminal):
            doc_type = _TRIO[i % len(_TRIO)]
            await _make_task_at(svc, project_id, doc_type, user_id, "confirmed")

        project = await session.get(Project, project_id)
        assert project.status != ProjectStatus.archived

        # force=True 归档所有 confirmed → 全部 archived
        count = await svc.archive_project_deliverables(
            project_id, user_id, year, force=True
        )
        assert count == n_terminal

        # 当且仅当全部交付物 archived 时，项目阶段标记完结
        all_tasks = await session.execute(
            select(WordExportTask).where(WordExportTask.project_id == project_id)
        )
        tasks = list(all_tasks.scalars().all())
        assert all(t.status == WordExportStatus.archived.value for t in tasks)

        project = await session.get(Project, project_id)
        assert project.status == ProjectStatus.archived

    _run_in_isolated_db(_scenario)


@given(year=st.integers(min_value=2018, max_value=2030))
@settings(max_examples=5, deadline=None)
def test_project_phase_not_complete_when_partial(year):
    # Feature: audit-report-deliverable-center, Property 53: 项目阶段聚合完结
    """Property 53 边界：尚有非 archived 交付物时，项目阶段不标记完结。"""

    async def _scenario(session, project_id, user_id):
        svc = DeliverableService(session)
        # 一个 confirmed（会被归档）+ 一个 editing（不会被归档）→ 非全 archived
        await _make_task_at(svc, project_id, "audit_report", user_id, "confirmed")
        await _make_task_at(svc, project_id, "financial_report", user_id, "editing")

        await svc.archive_project_deliverables(project_id, user_id, year, force=True)

        project = await session.get(Project, project_id)
        # 仍有 editing 未归档 → 项目阶段不应标记完结
        assert project.status != ProjectStatus.archived

    _run_in_isolated_db(_scenario)
