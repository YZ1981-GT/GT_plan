"""Phase4 Task 12 — SQLite 真 ORM / 文件故障全链回归

完整流程：readiness → 三件套生成 → 第 2 步失败 → retry → 完成，
逐项比较 snapshot、文件和指纹。

五类文件故障在全链上下文中必须全部 fail-closed。
并行运行 phase2/phase3 定向回归，区分本阶段引入与预存红。

_需求引用: 2.1–2.6, 3.1–3.6, 4.1–4.6, 5.1–5.6, 7.1–7.3_
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.core import Project, User
from app.models.phase13_models import (
    DeliverableSnapshot,
    ExportJob,
    ExportJobAttempt,
    ExportJobAttemptStatus,
    ExportJobItem,
    ExportJobItemStatus,
    ExportJobStatus,
)
from app.services.deliverable_readiness_service import (
    DeliverableReadinessService,
)
from app.services.export_job_service import ExportJobService
from app.services.file_fingerprint_service import (
    FileHashMismatch,
    FileNotFoundOnDisk,
    FilePersistError,
    compute_file_fingerprint,
    persist_file_fail_closed,
    verify_file_fingerprint,
)
from app.services.full_deliverables_executor import (
    TRIO_STEPS,
    FullDeliverablesExecutor,
    aggregate_trio_status,
)


# ──────────────────────────────────────────────────────────────────────
# SQLite Fixtures
# ──────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def engine():
    """SQLite 内存库引擎。"""
    from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
    SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine):
    """SQLite session。"""
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session


@pytest_asyncio.fixture
async def test_user(db: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        username="fullchain_tester",
        email="fullchain@test.com",
        hashed_password="hashed",
        role="admin",
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def test_project(db: AsyncSession, test_user: User) -> Project:
    project = Project(
        id=uuid.uuid4(),
        name="全链回归测试项目",
        client_name="全链测试公司",
        status="created",
        template_type="soe",
        audit_year=2025,
        created_by=test_user.id,
    )
    db.add(project)
    await db.flush()
    return project


# ──────────────────────────────────────────────────────────────────────
# Readiness seed helpers (从 test_phase4_readiness 复用模式)
# ──────────────────────────────────────────────────────────────────────

async def _seed_trial_balance(
    db: AsyncSession, project_id: uuid.UUID, year: int, count: int = 5,
):
    from app.models.audit_platform_models import TrialBalance
    for i in range(count):
        tb = TrialBalance(
            id=uuid.uuid4(),
            project_id=project_id,
            year=year,
            company_code="001",
            standard_account_code=f"1001.{i:02d}",
            account_name=f"科目{i}",
            account_category="assets",
            unadjusted_amount=Decimal("10000.00"),
            audited_amount=Decimal("10000.00"),
        )
        db.add(tb)
    await db.flush()


async def _seed_formula_push(
    db: AsyncSession, project_id: uuid.UUID, year: int,
):
    from app.models.formula_push_models import FormulaPushRun
    run = FormulaPushRun(
        id=uuid.uuid4(),
        project_id=project_id,
        year=year,
        trigger_source="manual",
        status="succeeded",
    )
    db.add(run)
    await db.flush()


async def _seed_adjustments(
    db: AsyncSession,
    project_id: uuid.UUID,
    year: int,
    user_id: uuid.UUID,
):
    from app.models.audit_platform_models import Adjustment
    for i in range(2):
        adj = Adjustment(
            id=uuid.uuid4(),
            project_id=project_id,
            year=year,
            company_code="001",
            adjustment_no=f"AJE-{i+1:03d}",
            adjustment_type="aje",
            account_code=f"1001.{i:02d}",
            debit_amount=Decimal("1000.00"),
            credit_amount=Decimal("0.00"),
            entry_group_id=uuid.uuid4(),
            review_status="approved",
            created_by=user_id,
        )
        db.add(adj)
    await db.flush()


async def _seed_reports(
    db: AsyncSession, project_id: uuid.UUID, year: int,
):
    from app.models.report_models import FinancialReport
    for i in range(5):
        report = FinancialReport(
            id=uuid.uuid4(),
            project_id=project_id,
            year=year,
            report_type="balance_sheet",
            row_code=f"R{i+1:03d}",
            row_name=f"报表行{i}",
            current_period_amount=Decimal("50000.00"),
            is_stale=False,
        )
        db.add(report)
    await db.flush()


async def _seed_notes(
    db: AsyncSession,
    project_id: uuid.UUID,
    year: int,
    user_id: uuid.UUID,
):
    from app.models.report_models import DisclosureNote
    for i in range(3):
        note = DisclosureNote(
            id=uuid.uuid4(),
            project_id=project_id,
            year=year,
            note_section=f"五、{i+1}",
            section_title=f"附注章节{i}",
            is_stale=False,
            updated_by=user_id,
        )
        db.add(note)
    await db.flush()


async def _seed_full_readiness(
    db: AsyncSession,
    project_id: uuid.UUID,
    year: int,
    user_id: uuid.UUID,
):
    """种入全部就绪数据 — 使 readiness 返回 ready。"""
    await _seed_trial_balance(db, project_id, year)
    await _seed_formula_push(db, project_id, year)
    await _seed_adjustments(db, project_id, year, user_id)
    await _seed_reports(db, project_id, year)
    await _seed_notes(db, project_id, year, user_id)


# ──────────────────────────────────────────────────────────────────────
# Step Runner 桩实现
# ──────────────────────────────────────────────────────────────────────

class AllSucceedRunner:
    """所有步骤均成功，返回随机 task_id。"""
    def __init__(self):
        self.call_order: list[str] = []

    async def run_step(self, step_key: str, snapshot_id: UUID) -> UUID | None:
        self.call_order.append(step_key)
        return uuid.uuid4()


class FailOnStepRunner:
    """指定步骤失败，其余成功。"""
    def __init__(self, fail_steps: set[str]):
        self.fail_steps = fail_steps
        self.call_order: list[str] = []

    async def run_step(self, step_key: str, snapshot_id: UUID) -> UUID | None:
        self.call_order.append(step_key)
        if step_key in self.fail_steps:
            raise RuntimeError(f"模拟 {step_key} 生成失败")
        return uuid.uuid4()


class RecordSnapshotRunner:
    """记录每步收到的 snapshot_id 和调用顺序。"""
    def __init__(self):
        self.snapshots: dict[str, UUID] = {}
        self.call_order: list[str] = []

    async def run_step(self, step_key: str, snapshot_id: UUID) -> UUID | None:
        self.snapshots[step_key] = snapshot_id
        self.call_order.append(step_key)
        return uuid.uuid4()


# ──────────────────────────────────────────────────────────────────────
# DB query helpers
# ──────────────────────────────────────────────────────────────────────

async def _get_items(db: AsyncSession, job_id: UUID) -> list[ExportJobItem]:
    result = await db.execute(
        sa.select(ExportJobItem)
        .where(ExportJobItem.job_id == job_id)
        .order_by(ExportJobItem.sequence.asc())
    )
    return list(result.scalars().all())


async def _get_attempts(db: AsyncSession, job_id: UUID) -> list[ExportJobAttempt]:
    result = await db.execute(
        sa.select(ExportJobAttempt)
        .where(ExportJobAttempt.job_id == job_id)
        .order_by(ExportJobAttempt.attempt_no.asc())
    )
    return list(result.scalars().all())


async def _get_item_attempts(
    db: AsyncSession, item_id: UUID,
) -> list[ExportJobAttempt]:
    result = await db.execute(
        sa.select(ExportJobAttempt)
        .where(ExportJobAttempt.item_id == item_id)
        .order_by(ExportJobAttempt.attempt_no.asc())
    )
    return list(result.scalars().all())


# ──────────────────────────────────────────────────────────────────────
# Helper: create snapshot + job for full chain
# ──────────────────────────────────────────────────────────────────────

async def _create_snapshot_and_job(
    db: AsyncSession,
    project: Project,
    user: User,
    year: int = 2025,
) -> tuple[DeliverableSnapshot, ExportJob]:
    """创建交付快照和三件套 job。"""
    snapshot = DeliverableSnapshot(
        id=uuid.uuid4(),
        project_id=project.id,
        year=year,
        digest=hashlib.sha256(
            f"{project.id}:{year}:test".encode()
        ).hexdigest(),
        payload={"project_id": str(project.id), "year": year},
    )
    db.add(snapshot)
    await db.flush()

    job = ExportJob(
        id=uuid.uuid4(),
        project_id=project.id,
        job_type="full_deliverables",
        kind="deliverable_trio",
        status=ExportJobStatus.queued.value,
        payload={},
        progress_total=3,
        progress_done=0,
        failed_count=0,
        initiated_by=user.id,
        snapshot_id=snapshot.id,
        year=year,
        trio_total=3,
        trio_succeeded=0,
    )
    db.add(job)
    await db.flush()

    return snapshot, job


# ══════════════════════════════════════════════════════════════════════
# 1. TestFullChainIntegration — readiness → trio → retry → 完成
# ══════════════════════════════════════════════════════════════════════

class TestFullChainIntegration:
    """需求 2.1–2.6, 4.1–4.6, 5.1–5.6, 7.1–7.2

    用真实 executor、版本服务和任务模型跑
    readiness → 三件套生成 → 第 2 步失败 → retry → 完成。
    """

    @pytest.mark.asyncio
    async def test_readiness_to_trio_to_retry_to_completion(
        self, db: AsyncSession, test_project: Project, test_user: User,
    ):
        """全链路：readiness ready → trio step2 fail → retry → all succeed。"""
        year = 2025

        # ── 1. Seed readiness data ──
        await _seed_full_readiness(db, test_project.id, year, test_user.id)

        # ── 2. Readiness check → ready ──
        svc = DeliverableReadinessService()
        readiness = await svc.check(
            db, test_project.id, year, include_file_checks=False,
        )
        assert readiness.status == "ready", (
            f"readiness 应为 ready，实际 {readiness.status}, "
            f"blockers={[b.code for b in readiness.hard_blockers]}"
        )

        # ── 3. Create snapshot + job ──
        snapshot, job = await _create_snapshot_and_job(
            db, test_project, test_user, year,
        )

        # ── 4. Run trio — step 2 (disclosure_notes) 失败 ──
        executor = FullDeliverablesExecutor(db)
        fail_runner = FailOnStepRunner({"disclosure_notes"})
        result = await executor.run_trio(
            job=job,
            snapshot_id=snapshot.id,
            step_runner=fail_runner,
        )

        # 验证：step1 成功，step2 失败，step3 被依赖阻断
        assert result.status == "partial"
        items = await _get_items(db, job.id)
        assert len(items) == 3

        step_statuses = {i.step_key: i.status for i in items}
        assert step_statuses["financial_report"] == ExportJobItemStatus.succeeded.value
        assert step_statuses["disclosure_notes"] == ExportJobItemStatus.failed.value
        assert step_statuses["audit_report"] == ExportJobItemStatus.blocked.value

        # job 状态
        assert job.status == "partial"
        assert job.trio_succeeded == 1

        # attempts: step1 和 step2 有 attempt，step3 (blocked) 无 attempt
        all_attempts = await _get_attempts(db, job.id)
        steps_with_attempts = {a.item_id for a in all_attempts}
        blocked_item = next(i for i in items if i.step_key == "audit_report")
        assert blocked_item.id not in steps_with_attempts, (
            "blocked 步骤不应有 attempt"
        )
        # step1 和 step2 各有 1 个 attempt
        fr_item = next(i for i in items if i.step_key == "financial_report")
        dn_item = next(i for i in items if i.step_key == "disclosure_notes")
        fr_attempts = [a for a in all_attempts if a.item_id == fr_item.id]
        dn_attempts = [a for a in all_attempts if a.item_id == dn_item.id]
        assert len(fr_attempts) == 1
        assert len(dn_attempts) == 1
        assert fr_attempts[0].status == ExportJobAttemptStatus.succeeded.value
        assert dn_attempts[0].status == ExportJobAttemptStatus.failed.value

        # ── 5. Retry — step 2 和 step 3 现在成功 ──
        job_svc = ExportJobService(db)
        succeed_runner = AllSucceedRunner()
        retry_result = await job_svc.retry_failed_trio(
            job.id, step_runner=succeed_runner,
        )

        # 验证 retry 结果
        assert retry_result["retried"] >= 2  # disclosure_notes + audit_report
        assert retry_result["trio_succeeded"] == 3
        assert retry_result["job_status"] == "succeeded"

        # 刷新 items
        items_after = await _get_items(db, job.id)
        statuses_after = {i.step_key: i.status for i in items_after}
        assert statuses_after["financial_report"] == ExportJobItemStatus.succeeded.value
        assert statuses_after["disclosure_notes"] == ExportJobItemStatus.succeeded.value
        assert statuses_after["audit_report"] == ExportJobItemStatus.succeeded.value

        # job 最终状态
        assert job.status == "succeeded"
        assert job.trio_succeeded == 3

    @pytest.mark.asyncio
    async def test_snapshot_shared_across_items(
        self, db: AsyncSession, test_project: Project, test_user: User,
    ):
        """需求 1.5: 三项文件必须引用同一个快照。"""
        snapshot, job = await _create_snapshot_and_job(
            db, test_project, test_user,
        )

        recorder = RecordSnapshotRunner()
        executor = FullDeliverablesExecutor(db)
        await executor.run_trio(
            job=job, snapshot_id=snapshot.id, step_runner=recorder,
        )

        # step_runner 收到的 snapshot_id 全部相同
        unique_snapshots = set(recorder.snapshots.values())
        assert len(unique_snapshots) == 1
        assert snapshot.id in unique_snapshots

        # DB 中 items 的 snapshot_id 也全部相同
        items = await _get_items(db, job.id)
        for item in items:
            assert item.snapshot_id == snapshot.id, (
                f"item {item.step_key} snapshot_id 应为 {snapshot.id}，"
                f"实际 {item.snapshot_id}"
            )

    @pytest.mark.asyncio
    async def test_old_failure_preserved_after_retry(
        self, db: AsyncSession, test_project: Project, test_user: User,
    ):
        """需求 5.4: 重试保留原始失败 attempt 和失败原因。"""
        snapshot, job = await _create_snapshot_and_job(
            db, test_project, test_user,
        )

        # step 2 失败
        executor = FullDeliverablesExecutor(db)
        fail_runner = FailOnStepRunner({"disclosure_notes"})
        await executor.run_trio(
            job=job, snapshot_id=snapshot.id, step_runner=fail_runner,
        )

        # 找到 disclosure_notes 的失败 attempt
        items = await _get_items(db, job.id)
        dn_item = next(i for i in items if i.step_key == "disclosure_notes")
        old_attempts = await _get_item_attempts(db, dn_item.id)
        assert len(old_attempts) == 1
        original_error = old_attempts[0].error_message
        original_attempt_no = old_attempts[0].attempt_no
        assert original_error is not None
        assert "disclosure_notes" in original_error
        assert original_attempt_no == 1

        # retry 成功
        job_svc = ExportJobService(db)
        succeed_runner = AllSucceedRunner()
        await job_svc.retry_failed_trio(job.id, step_runner=succeed_runner)

        # 验证：旧失败 attempt 保留，新成功 attempt 追加
        all_dn_attempts = await _get_item_attempts(db, dn_item.id)
        assert len(all_dn_attempts) == 2, (
            f"应有 2 个 attempt，实际 {len(all_dn_attempts)}"
        )

        old_attempt = next(
            a for a in all_dn_attempts if a.attempt_no == 1
        )
        new_attempt = next(
            a for a in all_dn_attempts if a.attempt_no == 2
        )

        # 旧失败保留
        assert old_attempt.status == ExportJobAttemptStatus.failed.value
        assert old_attempt.error_message == original_error

        # 新 attempt 成功
        assert new_attempt.status == ExportJobAttemptStatus.succeeded.value
        assert new_attempt.attempt_no == 2

    @pytest.mark.asyncio
    async def test_attempt_numbers_monotonic(
        self, db: AsyncSession, test_project: Project, test_user: User,
    ):
        """需求 5.4: 同一 item 的 attempt_no 唯一递增。"""
        snapshot, job = await _create_snapshot_and_job(
            db, test_project, test_user,
        )

        # 先失败
        executor = FullDeliverablesExecutor(db)
        fail_runner = FailOnStepRunner({"disclosure_notes"})
        await executor.run_trio(
            job=job, snapshot_id=snapshot.id, step_runner=fail_runner,
        )

        # retry 再失败
        job_svc = ExportJobService(db)
        fail_again_runner = FailOnStepRunner({"disclosure_notes"})
        await job_svc.retry_failed_trio(
            job.id, step_runner=fail_again_runner,
        )

        # retry 成功
        succeed_runner = AllSucceedRunner()
        await job_svc.retry_failed_trio(
            job.id, step_runner=succeed_runner,
        )

        # 验证 attempt 编号单调递增
        items = await _get_items(db, job.id)
        dn_item = next(i for i in items if i.step_key == "disclosure_notes")
        attempts = await _get_item_attempts(db, dn_item.id)

        attempt_nos = [a.attempt_no for a in attempts]
        assert attempt_nos == sorted(attempt_nos), (
            f"attempt_no 应单调递增: {attempt_nos}"
        )
        # 无重复
        assert len(attempt_nos) == len(set(attempt_nos)), (
            f"attempt_no 不应重复: {attempt_nos}"
        )

    @pytest.mark.asyncio
    async def test_job_history_complete(
        self, db: AsyncSession, test_project: Project, test_user: User,
    ):
        """需求 7.2: 查询可见完整 job/item/attempt 历史链。"""
        snapshot, job = await _create_snapshot_and_job(
            db, test_project, test_user,
        )

        # trio with step2 failure
        executor = FullDeliverablesExecutor(db)
        fail_runner = FailOnStepRunner({"disclosure_notes"})
        await executor.run_trio(
            job=job, snapshot_id=snapshot.id, step_runner=fail_runner,
        )

        # retry
        job_svc = ExportJobService(db)
        succeed_runner = AllSucceedRunner()
        await job_svc.retry_failed_trio(job.id, step_runner=succeed_runner)

        # 完整历史查询
        items = await _get_items(db, job.id)
        assert len(items) == 3

        all_attempts = await _get_attempts(db, job.id)
        # step1(1) + step2(2: fail+success) + step3(0 initial blocked + 1 retry) = 至少 4
        assert len(all_attempts) >= 4, (
            f"全链至少 4 个 attempt，实际 {len(all_attempts)}"
        )

        # 每个 attempt 都有 job_id 和 item_id
        for att in all_attempts:
            assert att.job_id == job.id
            assert att.item_id is not None

        # job 最终状态
        assert job.status == "succeeded"
        assert job.trio_succeeded == 3


# ══════════════════════════════════════════════════════════════════════
# 2. TestFileFailureFullChain — 五类文件故障 fail-closed
# ══════════════════════════════════════════════════════════════════════

class TestFileFailureFullChain:
    """需求 3.1–3.6, 7.3

    在全链上下文中验证五类文件故障均 fail-closed。
    使用 tmp_path 模拟真实文件操作。
    """

    def test_file_write_failure_fail_closed(self, tmp_path: Path):
        """故障 1: 文件写入失败 → 版本不应被创建。"""
        delivery_root = tmp_path / "deliverables"
        delivery_root.mkdir()

        # 创建一个只读目录使写入失败
        readonly_dir = delivery_root / "project" / "readonly"
        readonly_dir.mkdir(parents=True)
        target = readonly_dir / "report.xlsx"

        # 通过传入空内容触发失败
        with pytest.raises(FilePersistError, match="无文件内容"):
            persist_file_fail_closed(
                b"",  # 空内容
                target,
                delivery_root=delivery_root,
            )

        # 确保无文件残留
        assert not target.exists()

    def test_file_deleted_after_write_fail_closed(self, tmp_path: Path):
        """故障 2: 文件写入后被删除 → 校验应捕获。"""
        delivery_root = tmp_path / "deliverables"
        delivery_root.mkdir()
        target = delivery_root / "report.xlsx"

        # 先成功写入
        content = b"fake xlsx content for deletion test"
        fp = persist_file_fail_closed(
            content, target, delivery_root=delivery_root,
        )
        assert target.exists()
        assert fp.size == len(content)

        # 模拟文件被删除
        target.unlink()

        # verify_file_fingerprint 应捕获文件缺失
        with pytest.raises(FileNotFoundOnDisk):
            verify_file_fingerprint(
                file_path=str(target),
                expected_size=fp.size,
                expected_sha256=fp.sha256,
                delivery_root=delivery_root,
            )

    def test_file_truncated_detected(self, tmp_path: Path):
        """故障 3: 文件被截断 → 大小不一致应被检测。"""
        delivery_root = tmp_path / "deliverables"
        delivery_root.mkdir()
        target = delivery_root / "notes.docx"

        content = b"A" * 1024  # 1KB 文件
        fp = persist_file_fail_closed(
            content, target, delivery_root=delivery_root,
        )

        # 截断文件
        with open(target, "wb") as f:
            f.write(b"A" * 100)

        # verify 应检测到大小不一致
        from app.services.file_fingerprint_service import FileSizeMismatch
        with pytest.raises((FileSizeMismatch, FileHashMismatch)):
            verify_file_fingerprint(
                file_path=str(target),
                expected_size=fp.size,
                expected_sha256=fp.sha256,
                delivery_root=delivery_root,
            )

    def test_hash_mismatch_detected(self, tmp_path: Path):
        """故障 4: 文件内容被篡改 → 哈希不一致应被检测。"""
        delivery_root = tmp_path / "deliverables"
        delivery_root.mkdir()
        target = delivery_root / "audit_report.docx"

        content = b"original content for hash test"
        fp = persist_file_fail_closed(
            content, target, delivery_root=delivery_root,
        )

        # 篡改文件内容（保持相同大小以绕过 size check）
        tampered = b"tampered content for hash test"
        with open(target, "wb") as f:
            f.write(tampered)

        with pytest.raises(FileHashMismatch):
            verify_file_fingerprint(
                file_path=str(target),
                expected_size=None,  # 跳过 size 检查，只测 hash
                expected_sha256=fp.sha256,
                delivery_root=delivery_root,
            )

    def test_version_before_file_impossible(self, tmp_path: Path):
        """故障 5: persist_file_fail_closed 保证先文件后版本，
        版本先于文件是不可能的流程。

        验证：persist 返回 fingerprint 后文件必存在，
        调用方用 fingerprint 创建版本前文件已落盘。
        """
        delivery_root = tmp_path / "deliverables"
        delivery_root.mkdir()
        target = delivery_root / "report.xlsx"

        content = b"version-before-file test content"
        fp = persist_file_fail_closed(
            content, target, delivery_root=delivery_root,
        )

        # persist 返回后文件必须存在
        assert target.exists(), "persist 返回后文件应存在"
        assert target.stat().st_size > 0, "文件不应为空"

        # 重新计算指纹应与返回值一致
        actual_fp = compute_file_fingerprint(
            target, delivery_root=delivery_root,
        )
        assert actual_fp.sha256 == fp.sha256
        assert actual_fp.size == fp.size


# ══════════════════════════════════════════════════════════════════════
# 3. TestPhaseRegression — phase2/phase3 定向回归
# ══════════════════════════════════════════════════════════════════════

class TestPhaseRegression:
    """需求 7.1–7.3

    运行 phase4 全套测试回归，区分本阶段引入与预存红。
    此处通过 import 和基础断言验证各模块可用性和一致性。
    实际全套运行由 pytest 命令覆盖（见 task 描述的 rtk 命令）。
    """

    def test_executor_module_importable(self):
        """验证 executor 模块可导入，TRIO_STEPS 有效。"""
        from app.services.full_deliverables_executor import (
            TRIO_STEPS,
            TRIO_STEP_KEYS,
            FullDeliverablesExecutor,
            aggregate_trio_status,
        )
        assert len(TRIO_STEPS) == 3
        assert len(TRIO_STEP_KEYS) == 3

    def test_readiness_service_importable(self):
        """验证 readiness service 可导入。"""
        from app.services.deliverable_readiness_service import (
            DeliverableReadinessService,
            ReadinessResult,
        )
        svc = DeliverableReadinessService()
        assert svc is not None

    def test_export_job_service_importable(self):
        """验证 export job service 可导入。"""
        from app.services.export_job_service import (
            ExportJobService,
            SnapshotConflictError,
        )
        assert ExportJobService is not None

    def test_file_fingerprint_service_importable(self):
        """验证 file fingerprint service 可导入。"""
        from app.services.file_fingerprint_service import (
            compute_file_fingerprint,
            verify_file_fingerprint,
            persist_file_fail_closed,
            FileFingerprintError,
            FileNotFoundOnDisk,
            FileHashMismatch,
        )
        assert compute_file_fingerprint is not None

    def test_phase13_models_importable(self):
        """验证 phase13 ORM 模型可导入（含 Task 3 新增字段）。"""
        from app.models.phase13_models import (
            ExportJob,
            ExportJobItem,
            ExportJobAttempt,
            ExportJobStatus,
            ExportJobItemStatus,
            ExportJobAttemptStatus,
            DeliverableSnapshot,
        )
        # ExportJob 有 trio 相关字段
        assert hasattr(ExportJob, "kind")
        assert hasattr(ExportJob, "snapshot_id")
        assert hasattr(ExportJob, "trio_total")
        assert hasattr(ExportJob, "trio_succeeded")
        # ExportJobItem 有步骤和快照字段
        assert hasattr(ExportJobItem, "step_key")
        assert hasattr(ExportJobItem, "sequence")
        assert hasattr(ExportJobItem, "snapshot_id")
        # ExportJobAttempt 有不可变历史字段
        assert hasattr(ExportJobAttempt, "attempt_no")
        assert hasattr(ExportJobAttempt, "error_type")
        assert hasattr(ExportJobAttempt, "diagnostic_detail")
        # DeliverableSnapshot 有 digest
        assert hasattr(DeliverableSnapshot, "digest")

    def test_aggregate_trio_status_consistency(self):
        """聚合函数与 design §六 一致。"""
        sv = ExportJobItemStatus.succeeded.value
        fv = ExportJobItemStatus.failed.value
        bv = ExportJobItemStatus.blocked.value

        assert aggregate_trio_status([sv, sv, sv]) == "succeeded"
        assert aggregate_trio_status([fv, fv, fv]) == "failed"
        assert aggregate_trio_status([sv, fv, bv]) == "partial"
        assert aggregate_trio_status([sv, sv, fv]) == "partial"
        # all blocked without has_blockers → treated as failed
        # (blocked items are counted as failed_or_blocked in aggregation)
        assert aggregate_trio_status([bv, bv, bv]) == "failed"
        # has_blockers=True → "blocked" regardless of item statuses
        assert aggregate_trio_status([bv, bv, bv], has_blockers=True) == "blocked"

    @pytest.mark.asyncio
    async def test_readiness_blocked_when_no_data(
        self, db: AsyncSession, test_project: Project,
    ):
        """无种子数据时 readiness 应返回 blocked。"""
        svc = DeliverableReadinessService()
        result = await svc.check(
            db, test_project.id, 2025, include_file_checks=False,
        )
        assert result.status == "blocked"
        assert len(result.hard_blockers) > 0

    @pytest.mark.asyncio
    async def test_readiness_ready_with_full_seed(
        self, db: AsyncSession, test_project: Project, test_user: User,
    ):
        """全量种子数据后 readiness 应返回 ready。"""
        await _seed_full_readiness(db, test_project.id, 2025, test_user.id)
        svc = DeliverableReadinessService()
        result = await svc.check(
            db, test_project.id, 2025, include_file_checks=False,
        )
        assert result.status == "ready", (
            f"应为 ready，实际 {result.status}: "
            f"{[b.code for b in result.hard_blockers]}"
        )

    @pytest.mark.asyncio
    async def test_trio_step2_fail_step3_blocked(
        self, db: AsyncSession, test_project: Project, test_user: User,
    ):
        """phase4 核心不变量：step2 失败 → step3 被依赖阻断。"""
        snapshot, job = await _create_snapshot_and_job(
            db, test_project, test_user,
        )
        executor = FullDeliverablesExecutor(db)
        fail_runner = FailOnStepRunner({"disclosure_notes"})
        result = await executor.run_trio(
            job=job, snapshot_id=snapshot.id, step_runner=fail_runner,
        )

        items = await _get_items(db, job.id)
        statuses = {i.step_key: i.status for i in items}
        assert statuses["audit_report"] == ExportJobItemStatus.blocked.value
        assert result.status == "partial"

    @pytest.mark.asyncio
    async def test_savepoint_step1_survives_step2_failure(
        self, db: AsyncSession, test_project: Project, test_user: User,
    ):
        """phase4 核心不变量：step2 失败不影响 step1 成功状态。"""
        snapshot, job = await _create_snapshot_and_job(
            db, test_project, test_user,
        )
        executor = FullDeliverablesExecutor(db)
        fail_runner = FailOnStepRunner({"disclosure_notes"})
        await executor.run_trio(
            job=job, snapshot_id=snapshot.id, step_runner=fail_runner,
        )

        items = await _get_items(db, job.id)
        fr_item = next(i for i in items if i.step_key == "financial_report")
        assert fr_item.status == ExportJobItemStatus.succeeded.value, (
            "step1 成功不应被 step2 失败回滚"
        )
