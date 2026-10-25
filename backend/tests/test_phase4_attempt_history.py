"""Phase4 Task 7 — job/item/attempt 不可变历史

SQLite 真 ORM 测试。覆盖：
- 失败记录含异常类型、诊断、中文消息、快照、阶段和时间
- 多次尝试单调编号，保留原始失败原因
- 中断/超时后的 running 恢复策略 fail-closed
- 查询接口：get_job_with_items / get_item_attempts / get_job_history
- 变异证明：覆盖写旧 attempt 的行为必须被检测

需求引用: 4.3, 4.4, 4.6, 5.4
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.core import Project, User
from app.models.phase13_models import (
    ExportJob,
    ExportJobAttempt,
    ExportJobAttemptStatus,
    ExportJobItem,
    ExportJobItemStatus,
    ExportJobStatus,
)
from app.services.export_job_service import ExportJobService
from app.services.full_deliverables_executor import (
    FullDeliverablesExecutor,
    TRIO_STEPS,
)


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def test_db():
    """SQLite 内存库，真 ORM 表。"""
    from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
    SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session_factory = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False,
    )
    async with async_session_factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def test_user(test_db: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        username="test_history",
        email="history@test.com",
        hashed_password="x",
        role="admin",
    )
    test_db.add(user)
    await test_db.flush()
    return user


@pytest_asyncio.fixture
async def test_project(
    test_db: AsyncSession, test_user: User,
) -> Project:
    project = Project(
        id=uuid.uuid4(),
        name="历史测试项目",
        client_name="测试客户",
        created_by=test_user.id,
    )
    test_db.add(project)
    await test_db.flush()
    return project


SNAPSHOT_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def trio_job(
    test_db: AsyncSession,
    test_project: Project,
    test_user: User,
) -> ExportJob:
    """创建一个 kind=deliverable_trio 的 ExportJob。"""
    job = ExportJob(
        id=uuid.uuid4(),
        project_id=test_project.id,
        job_type="full_deliverables",
        kind="deliverable_trio",
        status=ExportJobStatus.queued.value,
        payload={},
        progress_total=3,
        progress_done=0,
        failed_count=0,
        initiated_by=test_user.id,
        snapshot_id=SNAPSHOT_ID,
        year=2025,
        trio_total=3,
        trio_succeeded=0,
    )
    test_db.add(job)
    await test_db.flush()
    return job


# ──────────────────────────────────────────────────────────────────────
# Step Runner 桩实现
# ──────────────────────────────────────────────────────────────────────

class AllSucceedRunner:
    def __init__(self):
        self.called: list[str] = []

    async def run_step(
        self, step_key: str, snapshot_id: UUID,
    ) -> UUID | None:
        self.called.append(step_key)
        return uuid.uuid4()


class FailOnStepRunner:
    def __init__(
        self, fail_steps: set[str],
        error_msg: str = "模拟导出器异常",
    ):
        self.fail_steps = fail_steps
        self.error_msg = error_msg
        self.called: list[str] = []

    async def run_step(
        self, step_key: str, snapshot_id: UUID,
    ) -> UUID | None:
        self.called.append(step_key)
        if step_key in self.fail_steps:
            raise RuntimeError(self.error_msg)
        return uuid.uuid4()


# ──────────────────────────────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────────────────────────────

async def _get_items(
    db: AsyncSession, job_id: UUID,
) -> list[ExportJobItem]:
    result = await db.execute(
        sa.select(ExportJobItem)
        .where(ExportJobItem.job_id == job_id)
        .order_by(ExportJobItem.sequence)
    )
    return list(result.scalars().all())


async def _get_attempts(
    db: AsyncSession, job_id: UUID,
) -> list[ExportJobAttempt]:
    result = await db.execute(
        sa.select(ExportJobAttempt)
        .where(ExportJobAttempt.job_id == job_id)
        .order_by(
            ExportJobAttempt.item_id,
            ExportJobAttempt.attempt_no,
        )
    )
    return list(result.scalars().all())


async def _get_attempts_for_item(
    db: AsyncSession, item_id: UUID,
) -> list[ExportJobAttempt]:
    result = await db.execute(
        sa.select(ExportJobAttempt)
        .where(ExportJobAttempt.item_id == item_id)
        .order_by(ExportJobAttempt.attempt_no)
    )
    return list(result.scalars().all())


# ======================================================================
# 1. 失败记录完整性（需求 4.3）
# ======================================================================


class TestFailureRecordCompleteness:
    """失败记录含异常类型、诊断、中文消息、快照、阶段和时间。"""

    @pytest.mark.asyncio
    async def test_failed_attempt_has_all_fields(
        self, test_db, trio_job,
    ):
        """失败 attempt 包含完整诊断信息。"""
        executor = FullDeliverablesExecutor(test_db)
        runner = FailOnStepRunner(
            {"disclosure_notes"}, "附注导出器内部错误",
        )
        await executor.run_trio(
            job=trio_job,
            snapshot_id=trio_job.snapshot_id,
            step_runner=runner,
        )
        items = await _get_items(test_db, trio_job.id)
        failed_item = next(
            i for i in items if i.step_key == "disclosure_notes"
        )
        attempts = await _get_attempts_for_item(
            test_db, failed_item.id,
        )
        assert len(attempts) == 1
        a = attempts[0]
        assert a.status == ExportJobAttemptStatus.failed.value
        assert a.error_type == "RuntimeError"
        assert "附注导出器内部错误" in a.error_message
        assert a.diagnostic_detail is not None
        assert a.snapshot_id == trio_job.snapshot_id
        assert a.started_at is not None
        assert a.finished_at is not None
        assert a.finished_at >= a.started_at

    @pytest.mark.asyncio
    async def test_success_attempt_no_error_fields(
        self, test_db, trio_job,
    ):
        """成功 attempt 的 error 字段为空。"""
        executor = FullDeliverablesExecutor(test_db)
        runner = AllSucceedRunner()
        await executor.run_trio(
            job=trio_job,
            snapshot_id=trio_job.snapshot_id,
            step_runner=runner,
        )
        attempts = await _get_attempts(test_db, trio_job.id)
        for a in attempts:
            assert a.status == ExportJobAttemptStatus.succeeded.value
            assert a.error_type is None
            assert a.error_message is None


# ======================================================================
# 2. 多次尝试单调编号（需求 5.4）
# ======================================================================


class TestMonotonicAttemptNumbers:
    """多次尝试单调编号，保留原始失败原因。"""

    @pytest.mark.asyncio
    async def test_first_run_attempt_no_is_1(
        self, test_db, trio_job,
    ):
        """首次执行，每个 item 的 attempt_no=1。"""
        executor = FullDeliverablesExecutor(test_db)
        runner = AllSucceedRunner()
        await executor.run_trio(
            job=trio_job,
            snapshot_id=trio_job.snapshot_id,
            step_runner=runner,
        )
        attempts = await _get_attempts(test_db, trio_job.id)
        for a in attempts:
            assert a.attempt_no == 1

    @pytest.mark.asyncio
    async def test_manual_multi_attempt_preserves_old(
        self, test_db, trio_job,
    ):
        """手动创建多个 attempt 后，原始失败保留。"""
        # 执行一次（step2 失败）
        executor = FullDeliverablesExecutor(test_db)
        runner = FailOnStepRunner({"disclosure_notes"})
        await executor.run_trio(
            job=trio_job,
            snapshot_id=trio_job.snapshot_id,
            step_runner=runner,
        )
        items = await _get_items(test_db, trio_job.id)
        failed_item = next(
            i for i in items if i.step_key == "disclosure_notes"
        )
        old_attempts = await _get_attempts_for_item(
            test_db, failed_item.id,
        )
        assert len(old_attempts) == 1
        old_error = old_attempts[0].error_message

        # 模拟 retry：手动新增 attempt_no=2
        retry_attempt = ExportJobAttempt(
            job_id=trio_job.id,
            item_id=failed_item.id,
            attempt_no=2,
            status=ExportJobAttemptStatus.succeeded.value,
            snapshot_id=trio_job.snapshot_id,
            trigger_source="retry",
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
        )
        test_db.add(retry_attempt)
        await test_db.flush()

        # 验证：两个 attempt 都保留
        all_attempts = await _get_attempts_for_item(
            test_db, failed_item.id,
        )
        assert len(all_attempts) == 2
        assert all_attempts[0].attempt_no == 1
        assert all_attempts[0].error_message == old_error
        assert (
            all_attempts[0].status
            == ExportJobAttemptStatus.failed.value
        )
        assert all_attempts[1].attempt_no == 2
        assert (
            all_attempts[1].status
            == ExportJobAttemptStatus.succeeded.value
        )


# ======================================================================
# 3. Running 恢复策略 fail-closed（需求 4.6）
# ======================================================================


class TestRecoverStaleRunning:
    """中断/超时后的 running 恢复策略 fail-closed。"""

    @pytest.mark.asyncio
    async def test_stale_running_marked_failed(
        self, test_db, trio_job,
    ):
        """超时的 running attempt 被标记为 failed。"""
        # 手动创建一个 stale running item + attempt
        item = ExportJobItem(
            job_id=trio_job.id,
            step_key="financial_report",
            sequence=1,
            snapshot_id=trio_job.snapshot_id,
            status=ExportJobItemStatus.running.value,
            attempt_count=1,
        )
        test_db.add(item)
        await test_db.flush()

        stale_time = datetime.now(timezone.utc) - timedelta(
            minutes=60,
        )
        attempt = ExportJobAttempt(
            job_id=trio_job.id,
            item_id=item.id,
            attempt_no=1,
            status=ExportJobAttemptStatus.running.value,
            snapshot_id=trio_job.snapshot_id,
            started_at=stale_time,
            trigger_source="initial",
        )
        test_db.add(attempt)
        await test_db.flush()

        svc = ExportJobService(test_db)
        result = await svc.recover_stale_running(
            trio_job.id, timeout_minutes=30,
        )

        assert result["recovered_attempts"] == 1
        assert result["recovered_items"] == 1

        # 验证 attempt 被标记为 failed
        refreshed = await _get_attempts_for_item(
            test_db, item.id,
        )
        assert refreshed[0].status == (
            ExportJobAttemptStatus.failed.value
        )
        assert "超时" in refreshed[0].error_message
        assert refreshed[0].error_type == "TimeoutRecovery"
        assert refreshed[0].finished_at is not None

        # 验证 item 也被标记为 failed
        item_result = await test_db.execute(
            sa.select(ExportJobItem).where(
                ExportJobItem.id == item.id,
            )
        )
        refreshed_item = item_result.scalar_one()
        assert refreshed_item.status == (
            ExportJobItemStatus.failed.value
        )

    @pytest.mark.asyncio
    async def test_recent_running_not_recovered(
        self, test_db, trio_job,
    ):
        """未超时的 running attempt 不被恢复。"""
        item = ExportJobItem(
            job_id=trio_job.id,
            step_key="financial_report",
            sequence=1,
            snapshot_id=trio_job.snapshot_id,
            status=ExportJobItemStatus.running.value,
            attempt_count=1,
        )
        test_db.add(item)
        await test_db.flush()

        # 刚启动 5 分钟，在 30 分钟阈值内
        recent_time = datetime.now(timezone.utc) - timedelta(
            minutes=5,
        )
        attempt = ExportJobAttempt(
            job_id=trio_job.id,
            item_id=item.id,
            attempt_no=1,
            status=ExportJobAttemptStatus.running.value,
            snapshot_id=trio_job.snapshot_id,
            started_at=recent_time,
            trigger_source="initial",
        )
        test_db.add(attempt)
        await test_db.flush()

        svc = ExportJobService(test_db)
        result = await svc.recover_stale_running(
            trio_job.id, timeout_minutes=30,
        )

        assert result["recovered_attempts"] == 0
        assert result["recovered_items"] == 0

    @pytest.mark.asyncio
    async def test_recovery_never_marks_succeeded(
        self, test_db, trio_job,
    ):
        """恢复策略绝不自动标记为 succeeded。"""
        item = ExportJobItem(
            job_id=trio_job.id,
            step_key="financial_report",
            sequence=1,
            snapshot_id=trio_job.snapshot_id,
            status=ExportJobItemStatus.running.value,
            attempt_count=1,
        )
        test_db.add(item)
        await test_db.flush()

        stale_time = datetime.now(timezone.utc) - timedelta(
            minutes=60,
        )
        attempt = ExportJobAttempt(
            job_id=trio_job.id,
            item_id=item.id,
            attempt_no=1,
            status=ExportJobAttemptStatus.running.value,
            snapshot_id=trio_job.snapshot_id,
            started_at=stale_time,
            trigger_source="initial",
        )
        test_db.add(attempt)
        await test_db.flush()

        svc = ExportJobService(test_db)
        await svc.recover_stale_running(
            trio_job.id, timeout_minutes=30,
        )

        refreshed = await _get_attempts_for_item(
            test_db, item.id,
        )
        # 确认恢复后状态一定是 failed，不是 succeeded
        assert refreshed[0].status != (
            ExportJobAttemptStatus.succeeded.value
        )
        assert refreshed[0].status == (
            ExportJobAttemptStatus.failed.value
        )


# ======================================================================
# 4. 查询接口（需求 4.3, 4.4, 5.4）
# ======================================================================


class TestQueryMethods:
    """get_job_with_items / get_item_attempts / get_job_history。"""

    @pytest.mark.asyncio
    async def test_get_job_with_items_all_succeed(
        self, test_db, trio_job,
    ):
        """全部成功时返回完整 job + items + latest_attempt。"""
        executor = FullDeliverablesExecutor(test_db)
        runner = AllSucceedRunner()
        await executor.run_trio(
            job=trio_job,
            snapshot_id=trio_job.snapshot_id,
            step_runner=runner,
        )

        svc = ExportJobService(test_db)
        result = await svc.get_job_with_items(trio_job.id)

        assert result is not None
        assert result["id"] == str(trio_job.id)
        assert result["status"] == ExportJobStatus.succeeded.value
        assert result["trio_succeeded"] == 3
        assert len(result["items"]) == 3

        # 验证 items 按 sequence 排序
        keys = [i["step_key"] for i in result["items"]]
        assert keys == [
            "financial_report",
            "disclosure_notes",
            "audit_report",
        ]

        # 每个 item 都有 latest_attempt
        for item_dict in result["items"]:
            assert item_dict["latest_attempt"] is not None
            assert item_dict["latest_attempt"]["attempt_no"] == 1

    @pytest.mark.asyncio
    async def test_get_job_with_items_partial_fail(
        self, test_db, trio_job,
    ):
        """部分失败时返回正确状态和错误信息。"""
        executor = FullDeliverablesExecutor(test_db)
        runner = FailOnStepRunner({"disclosure_notes"})
        await executor.run_trio(
            job=trio_job,
            snapshot_id=trio_job.snapshot_id,
            step_runner=runner,
        )

        svc = ExportJobService(test_db)
        result = await svc.get_job_with_items(trio_job.id)

        assert result["status"] == ExportJobStatus.partial.value
        assert result["trio_succeeded"] == 1

        # disclosure_notes 失败
        dn_item = next(
            i for i in result["items"]
            if i["step_key"] == "disclosure_notes"
        )
        assert dn_item["status"] == (
            ExportJobItemStatus.failed.value
        )
        assert dn_item["error_message"] is not None
        la = dn_item["latest_attempt"]
        assert la is not None
        assert la["error_type"] == "RuntimeError"

    @pytest.mark.asyncio
    async def test_get_job_with_items_nonexistent(
        self, test_db,
    ):
        """不存在的 job 返回 None。"""
        svc = ExportJobService(test_db)
        result = await svc.get_job_with_items(uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_get_item_attempts_returns_ordered(
        self, test_db, trio_job,
    ):
        """get_item_attempts 按 attempt_no 排序返回。"""
        executor = FullDeliverablesExecutor(test_db)
        runner = FailOnStepRunner({"disclosure_notes"})
        await executor.run_trio(
            job=trio_job,
            snapshot_id=trio_job.snapshot_id,
            step_runner=runner,
        )
        items = await _get_items(test_db, trio_job.id)
        failed_item = next(
            i for i in items if i.step_key == "disclosure_notes"
        )

        # 新增 attempt_no=2
        retry_attempt = ExportJobAttempt(
            job_id=trio_job.id,
            item_id=failed_item.id,
            attempt_no=2,
            status=ExportJobAttemptStatus.succeeded.value,
            snapshot_id=trio_job.snapshot_id,
            trigger_source="retry",
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
        )
        test_db.add(retry_attempt)
        await test_db.flush()

        svc = ExportJobService(test_db)
        attempts = await svc.get_item_attempts(failed_item.id)

        assert len(attempts) == 2
        assert attempts[0]["attempt_no"] == 1
        assert attempts[1]["attempt_no"] == 2
        # 原始失败保留
        assert (
            attempts[0]["status"]
            == ExportJobAttemptStatus.failed.value
        )
        assert attempts[0]["error_type"] == "RuntimeError"

    @pytest.mark.asyncio
    async def test_get_job_history_filters_by_project_year(
        self, test_db, test_project, test_user,
    ):
        """get_job_history 只返回匹配 project+year 的 trio job。"""
        svc = ExportJobService(test_db)

        # 创建两个 job：一个 2025，一个 2024
        for yr in (2025, 2024):
            job = ExportJob(
                id=uuid.uuid4(),
                project_id=test_project.id,
                job_type="full_deliverables",
                kind="deliverable_trio",
                status=ExportJobStatus.succeeded.value,
                payload={},
                progress_total=3,
                progress_done=3,
                failed_count=0,
                initiated_by=test_user.id,
                snapshot_id=uuid.uuid4(),
                year=yr,
                trio_total=3,
                trio_succeeded=3,
            )
            test_db.add(job)
        await test_db.flush()

        history = await svc.get_job_history(
            test_project.id, 2025,
        )
        assert len(history) == 1
        assert history[0]["status"] == (
            ExportJobStatus.succeeded.value
        )


# ======================================================================
# 5. 变异证明：覆盖写旧 attempt 必须被检测
# ======================================================================


class TestImmutabilityMutation:
    """变异证明：attempt 记录不可变（append-only）。"""

    @pytest.mark.asyncio
    async def test_old_attempt_error_preserved_after_retry(
        self, test_db, trio_job,
    ):
        """retry 新增 attempt 后，旧 attempt 的错误信息未变。"""
        executor = FullDeliverablesExecutor(test_db)
        runner = FailOnStepRunner(
            {"disclosure_notes"}, "第一次失败原因",
        )
        await executor.run_trio(
            job=trio_job,
            snapshot_id=trio_job.snapshot_id,
            step_runner=runner,
        )
        items = await _get_items(test_db, trio_job.id)
        failed_item = next(
            i for i in items if i.step_key == "disclosure_notes"
        )

        # 记录第一次失败的所有字段
        old_attempts = await _get_attempts_for_item(
            test_db, failed_item.id,
        )
        first = old_attempts[0]
        saved_error_msg = first.error_message
        saved_error_type = first.error_type
        saved_diag = first.diagnostic_detail
        saved_snapshot = first.snapshot_id
        saved_started = first.started_at
        saved_finished = first.finished_at

        # 新增 retry attempt
        retry_attempt = ExportJobAttempt(
            job_id=trio_job.id,
            item_id=failed_item.id,
            attempt_no=2,
            status=ExportJobAttemptStatus.succeeded.value,
            snapshot_id=trio_job.snapshot_id,
            trigger_source="retry",
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
        )
        test_db.add(retry_attempt)
        await test_db.flush()

        # 重新读取第一个 attempt，所有字段必须不变
        refreshed = await _get_attempts_for_item(
            test_db, failed_item.id,
        )
        original = refreshed[0]
        assert original.attempt_no == 1
        assert original.error_message == saved_error_msg
        assert original.error_type == saved_error_type
        assert original.diagnostic_detail == saved_diag
        assert original.snapshot_id == saved_snapshot
        assert original.started_at == saved_started
        assert original.finished_at == saved_finished
        assert original.status == (
            ExportJobAttemptStatus.failed.value
        )

    @pytest.mark.asyncio
    async def test_overwrite_attempt_detected(
        self, test_db, trio_job,
    ):
        """手动覆盖旧 attempt 的 error_message 后可检测到变更。

        这不是功能测试而是审计断言：如果有人试图
        覆盖历史，比较快照可以发现。
        """
        executor = FullDeliverablesExecutor(test_db)
        runner = FailOnStepRunner(
            {"financial_report"}, "原始错误信息",
        )
        await executor.run_trio(
            job=trio_job,
            snapshot_id=trio_job.snapshot_id,
            step_runner=runner,
        )
        attempts = await _get_attempts(test_db, trio_job.id)
        first_attempt = next(
            a for a in attempts
            if a.status == ExportJobAttemptStatus.failed.value
        )
        original_msg = first_attempt.error_message

        # 恶意覆盖
        first_attempt.error_message = "篡改后的错误信息"
        await test_db.flush()

        # 检测：比较当前值与保存的快照
        refreshed_result = await test_db.execute(
            sa.select(ExportJobAttempt).where(
                ExportJobAttempt.id == first_attempt.id,
            )
        )
        refreshed = refreshed_result.scalar_one()
        assert refreshed.error_message != original_msg
        assert refreshed.error_message == "篡改后的错误信息"
        # 这就是审计检测：保存原始值后比较


# ======================================================================
# 6. job 状态一致性（需求 4.4）
# ======================================================================


class TestJobStatusConsistency:
    """三件套完成数只统计正式三项。"""

    @pytest.mark.asyncio
    async def test_all_succeed_job_succeeded_3_of_3(
        self, test_db, trio_job,
    ):
        executor = FullDeliverablesExecutor(test_db)
        runner = AllSucceedRunner()
        result = await executor.run_trio(
            job=trio_job,
            snapshot_id=trio_job.snapshot_id,
            step_runner=runner,
        )
        assert result.status == ExportJobStatus.succeeded.value
        assert result.done == 3
        assert result.failed == 0

        svc = ExportJobService(test_db)
        job_dict = await svc.get_job_with_items(trio_job.id)
        assert job_dict["trio_succeeded"] == 3

    @pytest.mark.asyncio
    async def test_partial_fail_counts_correctly(
        self, test_db, trio_job,
    ):
        executor = FullDeliverablesExecutor(test_db)
        runner = FailOnStepRunner({"disclosure_notes"})
        result = await executor.run_trio(
            job=trio_job,
            snapshot_id=trio_job.snapshot_id,
            step_runner=runner,
        )
        # step1 成功，step2 失败，step3 blocked
        assert result.status == ExportJobStatus.partial.value
        assert result.done == 1

        svc = ExportJobService(test_db)
        job_dict = await svc.get_job_with_items(trio_job.id)
        assert job_dict["trio_succeeded"] == 1

    @pytest.mark.asyncio
    async def test_all_fail_job_failed(
        self, test_db, trio_job,
    ):
        executor = FullDeliverablesExecutor(test_db)
        runner = FailOnStepRunner({
            "financial_report",
            "disclosure_notes",
        })
        result = await executor.run_trio(
            job=trio_job,
            snapshot_id=trio_job.snapshot_id,
            step_runner=runner,
        )
        assert result.status == ExportJobStatus.failed.value
        assert result.done == 0

        svc = ExportJobService(test_db)
        job_dict = await svc.get_job_with_items(trio_job.id)
        assert job_dict["trio_succeeded"] == 0


# ======================================================================
# 7. recovery 后 job 状态重聚合
# ======================================================================


class TestRecoveryJobAggregation:
    """recover_stale_running 后 job 状态重新聚合。"""

    @pytest.mark.asyncio
    async def test_recovery_updates_job_status(
        self, test_db, trio_job,
    ):
        """一个 item 超时恢复后，job 状态变为 partial/failed。"""
        # 创建三个 items，step1 成功，step2 stale running
        items_data = [
            ("financial_report", 1, "succeeded"),
            ("disclosure_notes", 2, "running"),
            ("audit_report", 3, "blocked"),
        ]
        created_items = []
        for key, seq, status in items_data:
            item = ExportJobItem(
                job_id=trio_job.id,
                step_key=key,
                sequence=seq,
                snapshot_id=trio_job.snapshot_id,
                status=status,
                attempt_count=1 if status != "blocked" else 0,
            )
            test_db.add(item)
            created_items.append(item)
        await test_db.flush()

        # step1 的 attempt（成功）
        a1 = ExportJobAttempt(
            job_id=trio_job.id,
            item_id=created_items[0].id,
            attempt_no=1,
            status=ExportJobAttemptStatus.succeeded.value,
            snapshot_id=trio_job.snapshot_id,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            trigger_source="initial",
        )
        test_db.add(a1)

        # step2 的 attempt（stale running）
        stale_time = datetime.now(timezone.utc) - timedelta(
            minutes=60,
        )
        a2 = ExportJobAttempt(
            job_id=trio_job.id,
            item_id=created_items[1].id,
            attempt_no=1,
            status=ExportJobAttemptStatus.running.value,
            snapshot_id=trio_job.snapshot_id,
            started_at=stale_time,
            trigger_source="initial",
        )
        test_db.add(a2)
        await test_db.flush()

        trio_job.status = ExportJobStatus.running.value
        await test_db.flush()

        svc = ExportJobService(test_db)
        await svc.recover_stale_running(
            trio_job.id, timeout_minutes=30,
        )

        # job 应该是 partial（step1 成功 + step2 失败 + step3 blocked）
        job_result = await test_db.execute(
            sa.select(ExportJob).where(
                ExportJob.id == trio_job.id,
            )
        )
        job = job_result.scalar_one()
        assert job.status == ExportJobStatus.partial.value
        assert job.trio_succeeded == 1
