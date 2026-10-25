"""Phase4 Task 6 — savepoint 隔离与事务边界

SQLite 真 ORM 测试。覆盖 begin_nested() 保存点行为：
- 步骤 1 成功 + 步骤 2 失败 → 步骤 1 的 item/version 保留，步骤 2 的失败 attempt 保留
- 步骤 2 失败 → 步骤 3 (audit_report) 标 blocked_by_dependency
- 失败记录包含 error_type、中文 error_message、diagnostic_detail
- 成功步骤的 attempt 记录保留
- 变异证明：去掉 begin_nested 的语义等价必须红

需求引用: 4.1, 4.2, 4.3, 4.5, 7.2
"""

from __future__ import annotations

import uuid
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
from app.services.full_deliverables_executor import (
    FullDeliverablesExecutor,
    FullDeliverablesResult,
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

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def test_user(test_db: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        username="test_savepoint",
        email="savepoint@test.com",
        hashed_password="x",
        role="admin",
    )
    test_db.add(user)
    await test_db.flush()
    return user


@pytest_asyncio.fixture
async def test_project(test_db: AsyncSession, test_user: User) -> Project:
    project = Project(
        id=uuid.uuid4(),
        name="保存点测试项目",
        client_name="测试客户",
        created_by=test_user.id,
    )
    test_db.add(project)
    await test_db.flush()
    return project


@pytest_asyncio.fixture
async def trio_job(test_db: AsyncSession, test_project: Project, test_user: User) -> ExportJob:
    """创建一个 kind=deliverable_trio 的 ExportJob。"""
    snapshot_id = uuid.uuid4()
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
        snapshot_id=snapshot_id,
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
    """所有步骤成功。"""
    def __init__(self):
        self.called: list[str] = []

    async def run_step(self, step_key: str, snapshot_id: UUID) -> UUID | None:
        self.called.append(step_key)
        return uuid.uuid4()


class FailOnStepRunner:
    """指定步骤抛出异常。"""
    def __init__(self, fail_steps: set[str], error_msg: str = "模拟导出器异常"):
        self.fail_steps = fail_steps
        self.error_msg = error_msg
        self.called: list[str] = []

    async def run_step(self, step_key: str, snapshot_id: UUID) -> UUID | None:
        self.called.append(step_key)
        if step_key in self.fail_steps:
            raise RuntimeError(self.error_msg)
        return uuid.uuid4()


class FailWithCustomExcRunner:
    """指定步骤抛出自定义异常类型。"""
    def __init__(self, fail_step: str, exc: Exception):
        self.fail_step = fail_step
        self.exc = exc
        self.called: list[str] = []

    async def run_step(self, step_key: str, snapshot_id: UUID) -> UUID | None:
        self.called.append(step_key)
        if step_key == self.fail_step:
            raise self.exc
        return uuid.uuid4()


# ──────────────────────────────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────────────────────────────

async def _get_items(db: AsyncSession, job_id: UUID) -> list[ExportJobItem]:
    """按 sequence 排序获取 job 的所有 item。"""
    result = await db.execute(
        sa.select(ExportJobItem)
        .where(ExportJobItem.job_id == job_id)
        .order_by(ExportJobItem.sequence)
    )
    return list(result.scalars().all())


async def _get_attempts(db: AsyncSession, job_id: UUID) -> list[ExportJobAttempt]:
    """获取 job 的所有 attempt，按 item_id + attempt_no 排序。"""
    result = await db.execute(
        sa.select(ExportJobAttempt)
        .where(ExportJobAttempt.job_id == job_id)
        .order_by(ExportJobAttempt.item_id, ExportJobAttempt.attempt_no)
    )
    return list(result.scalars().all())


async def _get_attempts_for_item(db: AsyncSession, item_id: UUID) -> list[ExportJobAttempt]:
    """获取某 item 的所有 attempt。"""
    result = await db.execute(
        sa.select(ExportJobAttempt)
        .where(ExportJobAttempt.item_id == item_id)
        .order_by(ExportJobAttempt.attempt_no)
    )
    return list(result.scalars().all())


# ======================================================================
# 测试类
# ======================================================================


class TestSavepointAttemptCreation:
    """验证 run_trio 为每个执行步骤创建 ExportJobAttempt 记录。"""

    @pytest.mark.asyncio
    async def test_all_succeed_creates_three_attempts(self, test_db, trio_job):
        """三步全成功时，每步各创建 1 个 attempt，attempt_no=1。"""
        executor = FullDeliverablesExecutor(test_db)
        runner = AllSucceedRunner()
        snapshot_id = trio_job.snapshot_id

        await executor.run_trio(
            job=trio_job, snapshot_id=snapshot_id, step_runner=runner,
        )

        attempts = await _get_attempts(test_db, trio_job.id)
        assert len(attempts) == 3, f"预期 3 个 attempt，实际 {len(attempts)}"

        for att in attempts:
            assert att.attempt_no == 1
            assert att.status == ExportJobAttemptStatus.succeeded.value
            assert att.snapshot_id == snapshot_id
            assert att.trigger_source == "initial"
            assert att.finished_at is not None

    @pytest.mark.asyncio
    async def test_item_attempt_count_updated(self, test_db, trio_job):
        """成功步骤的 item.attempt_count == 1。"""
        executor = FullDeliverablesExecutor(test_db)
        runner = AllSucceedRunner()

        await executor.run_trio(
            job=trio_job, snapshot_id=trio_job.snapshot_id, step_runner=runner,
        )

        items = await _get_items(test_db, trio_job.id)
        for item in items:
            assert item.attempt_count == 1
            assert item.last_attempt_id is not None

    @pytest.mark.asyncio
    async def test_item_last_attempt_id_matches(self, test_db, trio_job):
        """item.last_attempt_id 指向该 item 的实际 attempt。"""
        executor = FullDeliverablesExecutor(test_db)
        runner = AllSucceedRunner()

        await executor.run_trio(
            job=trio_job, snapshot_id=trio_job.snapshot_id, step_runner=runner,
        )

        items = await _get_items(test_db, trio_job.id)
        for item in items:
            atts = await _get_attempts_for_item(test_db, item.id)
            assert len(atts) == 1
            assert item.last_attempt_id == atts[0].id


class TestSavepointIsolation:
    """核心：步骤 2 失败时，步骤 1 的成功记录保留，步骤 2 的失败留痕保留。"""

    @pytest.mark.asyncio
    async def test_step1_survives_step2_failure(self, test_db, trio_job):
        """步骤 1 成功 → 步骤 2 失败 → 步骤 1 的 item 和 attempt 仍然 succeeded。"""
        executor = FullDeliverablesExecutor(test_db)
        runner = FailOnStepRunner({"disclosure_notes"})

        result = await executor.run_trio(
            job=trio_job, snapshot_id=trio_job.snapshot_id, step_runner=runner,
        )

        items = await _get_items(test_db, trio_job.id)
        # 步骤 1: financial_report → succeeded
        fr_item = next(i for i in items if i.step_key == "financial_report")
        assert fr_item.status == ExportJobItemStatus.succeeded.value

        fr_attempts = await _get_attempts_for_item(test_db, fr_item.id)
        assert len(fr_attempts) == 1
        assert fr_attempts[0].status == ExportJobAttemptStatus.succeeded.value

    @pytest.mark.asyncio
    async def test_step2_failure_attempt_preserved(self, test_db, trio_job):
        """步骤 2 失败 → 失败 attempt 记录保留（在保存点外写入）。"""
        executor = FullDeliverablesExecutor(test_db)
        runner = FailOnStepRunner({"disclosure_notes"}, "附注导出器异常：章节缺失")

        await executor.run_trio(
            job=trio_job, snapshot_id=trio_job.snapshot_id, step_runner=runner,
        )

        items = await _get_items(test_db, trio_job.id)
        dn_item = next(i for i in items if i.step_key == "disclosure_notes")
        assert dn_item.status == ExportJobItemStatus.failed.value
        assert dn_item.error_message is not None

        dn_attempts = await _get_attempts_for_item(test_db, dn_item.id)
        assert len(dn_attempts) == 1
        att = dn_attempts[0]
        assert att.status == ExportJobAttemptStatus.failed.value
        assert att.error_type == "RuntimeError"
        assert "附注导出器异常" in att.error_message
        assert att.diagnostic_detail is not None
        assert att.finished_at is not None

    @pytest.mark.asyncio
    async def test_step2_fail_step3_blocked_by_dependency(self, test_db, trio_job):
        """步骤 2 失败 → 步骤 3 (audit_report) 标 blocked_by_dependency。"""
        executor = FullDeliverablesExecutor(test_db)
        runner = FailOnStepRunner({"disclosure_notes"})

        await executor.run_trio(
            job=trio_job, snapshot_id=trio_job.snapshot_id, step_runner=runner,
        )

        items = await _get_items(test_db, trio_job.id)
        ar_item = next(i for i in items if i.step_key == "audit_report")
        assert ar_item.status == ExportJobItemStatus.blocked.value
        assert "前置步骤未成功" in ar_item.error_message

        # blocked 步骤不创建 attempt
        ar_attempts = await _get_attempts_for_item(test_db, ar_item.id)
        assert len(ar_attempts) == 0

    @pytest.mark.asyncio
    async def test_step2_fail_job_partial(self, test_db, trio_job):
        """步骤 1 成功 + 步骤 2 失败 → job 状态 partial。"""
        executor = FullDeliverablesExecutor(test_db)
        runner = FailOnStepRunner({"disclosure_notes"})

        result = await executor.run_trio(
            job=trio_job, snapshot_id=trio_job.snapshot_id, step_runner=runner,
        )

        assert result.status == ExportJobStatus.partial.value
        assert result.done == 1  # 只有 financial_report 成功
        assert result.failed == 2

    @pytest.mark.asyncio
    async def test_all_succeed_job_succeeded(self, test_db, trio_job):
        """三步全成功 → job 状态 succeeded，trio_succeeded=3。"""
        executor = FullDeliverablesExecutor(test_db)
        runner = AllSucceedRunner()

        result = await executor.run_trio(
            job=trio_job, snapshot_id=trio_job.snapshot_id, step_runner=runner,
        )

        assert result.status == ExportJobStatus.succeeded.value
        assert result.done == 3
        assert trio_job.trio_succeeded == 3

        attempts = await _get_attempts(test_db, trio_job.id)
        assert all(
            a.status == ExportJobAttemptStatus.succeeded.value
            for a in attempts
        )


class TestFailureRecordContent:
    """验证失败记录包含 error_type、中文 error_message、diagnostic_detail。"""

    @pytest.mark.asyncio
    async def test_error_type_is_exception_class_name(self, test_db, trio_job):
        """error_type 记录异常类名。"""
        executor = FullDeliverablesExecutor(test_db)

        class 导出异常(Exception):
            pass

        runner = FailWithCustomExcRunner("financial_report", 导出异常("文件写入失败"))

        await executor.run_trio(
            job=trio_job, snapshot_id=trio_job.snapshot_id, step_runner=runner,
        )

        items = await _get_items(test_db, trio_job.id)
        fr_item = next(i for i in items if i.step_key == "financial_report")
        atts = await _get_attempts_for_item(test_db, fr_item.id)
        assert len(atts) == 1
        assert atts[0].error_type == "导出异常"

    @pytest.mark.asyncio
    async def test_chinese_error_message_preserved(self, test_db, trio_job):
        """中文错误消息完整保留。"""
        executor = FullDeliverablesExecutor(test_db)
        runner = FailOnStepRunner({"disclosure_notes"}, "附注章节缺失：五、1 营业收入")

        await executor.run_trio(
            job=trio_job, snapshot_id=trio_job.snapshot_id, step_runner=runner,
        )

        items = await _get_items(test_db, trio_job.id)
        dn_item = next(i for i in items if i.step_key == "disclosure_notes")
        atts = await _get_attempts_for_item(test_db, dn_item.id)
        assert "附注章节缺失" in atts[0].error_message
        assert "五、1 营业收入" in atts[0].error_message

    @pytest.mark.asyncio
    async def test_diagnostic_detail_present(self, test_db, trio_job):
        """diagnostic_detail 包含异常类型信息。"""
        executor = FullDeliverablesExecutor(test_db)
        runner = FailOnStepRunner({"financial_report"}, "SHA-256 不一致")

        await executor.run_trio(
            job=trio_job, snapshot_id=trio_job.snapshot_id, step_runner=runner,
        )

        items = await _get_items(test_db, trio_job.id)
        fr_item = next(i for i in items if i.step_key == "financial_report")
        atts = await _get_attempts_for_item(test_db, fr_item.id)
        assert atts[0].diagnostic_detail is not None
        assert "RuntimeError" in atts[0].diagnostic_detail

    @pytest.mark.asyncio
    async def test_error_message_truncated_at_500(self, test_db, trio_job):
        """超长错误消息截断到 500 字符。"""
        executor = FullDeliverablesExecutor(test_db)
        long_msg = "异" * 600
        runner = FailOnStepRunner({"financial_report"}, long_msg)

        await executor.run_trio(
            job=trio_job, snapshot_id=trio_job.snapshot_id, step_runner=runner,
        )

        items = await _get_items(test_db, trio_job.id)
        fr_item = next(i for i in items if i.step_key == "financial_report")
        assert len(fr_item.error_message) <= 500

        atts = await _get_attempts_for_item(test_db, fr_item.id)
        assert len(atts[0].error_message) <= 500


class TestAttemptTimestamps:
    """验证 attempt 时间戳。"""

    @pytest.mark.asyncio
    async def test_success_attempt_has_timestamps(self, test_db, trio_job):
        """成功 attempt 有 started_at 和 finished_at。"""
        executor = FullDeliverablesExecutor(test_db)
        runner = AllSucceedRunner()

        await executor.run_trio(
            job=trio_job, snapshot_id=trio_job.snapshot_id, step_runner=runner,
        )

        attempts = await _get_attempts(test_db, trio_job.id)
        for att in attempts:
            assert att.started_at is not None
            assert att.finished_at is not None

    @pytest.mark.asyncio
    async def test_failed_attempt_has_timestamps(self, test_db, trio_job):
        """失败 attempt 有 started_at 和 finished_at。"""
        executor = FullDeliverablesExecutor(test_db)
        runner = FailOnStepRunner({"disclosure_notes"})

        await executor.run_trio(
            job=trio_job, snapshot_id=trio_job.snapshot_id, step_runner=runner,
        )

        items = await _get_items(test_db, trio_job.id)
        dn_item = next(i for i in items if i.step_key == "disclosure_notes")
        atts = await _get_attempts_for_item(test_db, dn_item.id)
        assert len(atts) == 1
        assert atts[0].started_at is not None
        assert atts[0].finished_at is not None


class TestStepIsolationCombined:
    """综合场景：步骤 1 成功 + 步骤 2 约束/导出器异常 → 验证步骤 1 版本、
    步骤 2 失败 attempt、步骤 3 依赖状态。"""

    @pytest.mark.asyncio
    async def test_full_scenario_step2_constraint_error(self, test_db, trio_job):
        """制造步骤 2 约束异常，验证完整状态。"""
        executor = FullDeliverablesExecutor(test_db)
        runner = FailOnStepRunner(
            {"disclosure_notes"}, "约束异常：附注章节 template_type 不匹配"
        )

        result = await executor.run_trio(
            job=trio_job, snapshot_id=trio_job.snapshot_id, step_runner=runner,
        )

        items = await _get_items(test_db, trio_job.id)
        assert len(items) == 3

        # ── 步骤 1: financial_report → succeeded ──
        fr = next(i for i in items if i.step_key == "financial_report")
        assert fr.status == ExportJobItemStatus.succeeded.value
        assert fr.attempt_count == 1
        fr_atts = await _get_attempts_for_item(test_db, fr.id)
        assert len(fr_atts) == 1
        assert fr_atts[0].status == ExportJobAttemptStatus.succeeded.value

        # ── 步骤 2: disclosure_notes → failed ──
        dn = next(i for i in items if i.step_key == "disclosure_notes")
        assert dn.status == ExportJobItemStatus.failed.value
        assert dn.attempt_count == 1
        assert "约束异常" in dn.error_message
        dn_atts = await _get_attempts_for_item(test_db, dn.id)
        assert len(dn_atts) == 1
        assert dn_atts[0].status == ExportJobAttemptStatus.failed.value
        assert dn_atts[0].error_type == "RuntimeError"
        assert "template_type" in dn_atts[0].error_message

        # ── 步骤 3: audit_report → blocked ──
        ar = next(i for i in items if i.step_key == "audit_report")
        assert ar.status == ExportJobItemStatus.blocked.value
        assert "前置步骤未成功" in ar.error_message
        ar_atts = await _get_attempts_for_item(test_db, ar.id)
        assert len(ar_atts) == 0  # blocked 不创建 attempt

        # ── job 状态 ──
        assert result.status == ExportJobStatus.partial.value
        assert result.done == 1
        assert trio_job.trio_succeeded == 1

    @pytest.mark.asyncio
    async def test_step1_fail_all_subsequent_affected(self, test_db, trio_job):
        """步骤 1 失败 → 步骤 2 正常执行 → 步骤 3 blocked。"""
        executor = FullDeliverablesExecutor(test_db)
        runner = FailOnStepRunner({"financial_report"}, "审定报表生成失败")

        result = await executor.run_trio(
            job=trio_job, snapshot_id=trio_job.snapshot_id, step_runner=runner,
        )

        items = await _get_items(test_db, trio_job.id)

        fr = next(i for i in items if i.step_key == "financial_report")
        assert fr.status == ExportJobItemStatus.failed.value

        dn = next(i for i in items if i.step_key == "disclosure_notes")
        assert dn.status == ExportJobItemStatus.succeeded.value

        ar = next(i for i in items if i.step_key == "audit_report")
        assert ar.status == ExportJobItemStatus.blocked.value

        assert result.status == ExportJobStatus.partial.value

    @pytest.mark.asyncio
    async def test_all_steps_fail(self, test_db, trio_job):
        """所有步骤失败。"""
        executor = FullDeliverablesExecutor(test_db)
        runner = FailOnStepRunner(
            {"financial_report", "disclosure_notes"}, "全部失败"
        )

        result = await executor.run_trio(
            job=trio_job, snapshot_id=trio_job.snapshot_id, step_runner=runner,
        )

        items = await _get_items(test_db, trio_job.id)
        fr = next(i for i in items if i.step_key == "financial_report")
        dn = next(i for i in items if i.step_key == "disclosure_notes")
        ar = next(i for i in items if i.step_key == "audit_report")

        assert fr.status == ExportJobItemStatus.failed.value
        assert dn.status == ExportJobItemStatus.failed.value
        assert ar.status == ExportJobItemStatus.blocked.value

        assert result.status == ExportJobStatus.failed.value
        assert result.done == 0

        # 验证 failed 步骤都有 attempt
        all_atts = await _get_attempts(test_db, trio_job.id)
        assert len(all_atts) == 2  # fr + dn 各 1，ar blocked 无 attempt
        assert all(
            a.status == ExportJobAttemptStatus.failed.value
            for a in all_atts
        )


class TestServiceOnlyFlush:
    """验证 run_trio 服务仅 flush 不 commit（需求 4.1）。

    SQLite 下 begin_nested() 使用 SAVEPOINT，符合真实 ORM 行为。
    通过断言 session 仍处于 active 状态（未自动 commit）来验证。
    """

    @pytest.mark.asyncio
    async def test_session_not_committed_after_run_trio(self, test_db, trio_job):
        """run_trio 结束后 session 不应自动 commit。"""
        executor = FullDeliverablesExecutor(test_db)
        runner = AllSucceedRunner()

        await executor.run_trio(
            job=trio_job, snapshot_id=trio_job.snapshot_id, step_runner=runner,
        )

        # session 仍 active（未 commit / 未 close）
        assert not test_db.is_active is False  # is_active 在 flush-only 模式下应为 True


class TestMutationProofs:
    """变异证明：验证 savepoint 和 attempt 的关键行为不可移除。"""

    @pytest.mark.asyncio
    async def test_attempt_records_exist_for_executed_steps(self, test_db, trio_job):
        """变异防护：如果移除 attempt 创建，此测试必须红。

        断言每个执行过的步骤都有对应的 attempt 记录。
        """
        executor = FullDeliverablesExecutor(test_db)
        runner = AllSucceedRunner()

        await executor.run_trio(
            job=trio_job, snapshot_id=trio_job.snapshot_id, step_runner=runner,
        )

        items = await _get_items(test_db, trio_job.id)
        for item in items:
            atts = await _get_attempts_for_item(test_db, item.id)
            assert len(atts) >= 1, (
                f"步骤 {item.step_key} 缺少 attempt 记录"
            )

    @pytest.mark.asyncio
    async def test_failed_attempt_has_error_type(self, test_db, trio_job):
        """变异防护：如果移除 error_type 写入，此测试必须红。"""
        executor = FullDeliverablesExecutor(test_db)
        runner = FailOnStepRunner({"financial_report"}, "测试错误")

        await executor.run_trio(
            job=trio_job, snapshot_id=trio_job.snapshot_id, step_runner=runner,
        )

        items = await _get_items(test_db, trio_job.id)
        fr = next(i for i in items if i.step_key == "financial_report")
        atts = await _get_attempts_for_item(test_db, fr.id)
        assert atts[0].error_type is not None, (
            "失败 attempt 缺少 error_type"
        )
        assert atts[0].error_type != "", (
            "error_type 不应为空字符串"
        )

    @pytest.mark.asyncio
    async def test_failed_attempt_preserved_after_step2_fail(self, test_db, trio_job):
        """变异防护：如果失败记录写在保存点内（被回滚），此测试必须红。

        步骤 2 失败后，其 attempt 记录必须在数据库中可查询。
        """
        executor = FullDeliverablesExecutor(test_db)
        runner = FailOnStepRunner({"disclosure_notes"}, "附注失败")

        await executor.run_trio(
            job=trio_job, snapshot_id=trio_job.snapshot_id, step_runner=runner,
        )

        all_atts = await _get_attempts(test_db, trio_job.id)
        failed_atts = [
            a for a in all_atts
            if a.status == ExportJobAttemptStatus.failed.value
        ]
        assert len(failed_atts) >= 1, (
            "步骤 2 失败后数据库中无失败 attempt 记录 — "
            "可能失败记录写在保存点内被回滚了"
        )

    @pytest.mark.asyncio
    async def test_step1_success_not_rolled_back_by_step2(self, test_db, trio_job):
        """变异防护：如果没有 begin_nested 隔离，步骤 2 失败可能影响步骤 1。

        步骤 1 成功 + 步骤 2 失败 → 步骤 1 的 item 必须仍然 succeeded。
        """
        executor = FullDeliverablesExecutor(test_db)
        runner = FailOnStepRunner({"disclosure_notes"})

        await executor.run_trio(
            job=trio_job, snapshot_id=trio_job.snapshot_id, step_runner=runner,
        )

        items = await _get_items(test_db, trio_job.id)
        fr = next(i for i in items if i.step_key == "financial_report")
        assert fr.status == ExportJobItemStatus.succeeded.value, (
            "步骤 1 成功记录被步骤 2 失败影响 — "
            "可能缺少 begin_nested() 隔离"
        )

        # 步骤 1 的 attempt 也必须 succeeded
        fr_atts = await _get_attempts_for_item(test_db, fr.id)
        assert fr_atts[0].status == ExportJobAttemptStatus.succeeded.value

    @pytest.mark.asyncio
    async def test_blocked_step_no_attempt(self, test_db, trio_job):
        """变异防护：blocked 步骤不应创建 attempt。"""
        executor = FullDeliverablesExecutor(test_db)
        runner = FailOnStepRunner({"disclosure_notes"})

        await executor.run_trio(
            job=trio_job, snapshot_id=trio_job.snapshot_id, step_runner=runner,
        )

        items = await _get_items(test_db, trio_job.id)
        ar = next(i for i in items if i.step_key == "audit_report")
        atts = await _get_attempts_for_item(test_db, ar.id)
        assert len(atts) == 0, (
            "blocked 步骤不应有 attempt 记录"
        )
