"""Phase4 Task 5 — executor 固定顺序与步骤依赖

SQLite 真 ORM 测试。覆盖 TRIO_STEPS 常量、执行顺序、snapshot 共享、
依赖阻断和状态聚合，含变异证明。

需求引用: 2.1–2.6, 4.4
"""

from __future__ import annotations

import uuid
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.core import Project, User
from app.models.phase13_models import (
    ExportJob,
    ExportJobItem,
    ExportJobItemStatus,
    ExportJobStatus,
)
from app.services.full_deliverables_executor import (
    AUDIT_REPORT_DEPENDENCIES,
    TRIO_STEP_KEYS,
    TRIO_STEPS,
    FullDeliverablesExecutor,
    FullDeliverablesResult,
    StepOutcome,
    aggregate_trio_status,
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
        username="test_trio",
        email="trio@test.com",
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
        name="三件套测试项目",
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
    """所有步骤均成功。"""
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
    """记录每步收到的 snapshot_id。"""
    def __init__(self):
        self.snapshots: dict[str, UUID] = {}

    async def run_step(self, step_key: str, snapshot_id: UUID) -> UUID | None:
        self.snapshots[step_key] = snapshot_id
        return uuid.uuid4()


# ══════════════════════════════════════════════════════════════════════
# 1. TRIO_STEPS 常量正确性
# ══════════════════════════════════════════════════════════════════════

class TestTrioStepsConstant:
    """验证 TRIO_STEPS 常量严格匹配 design spec（需求 2.1）。"""

    def test_trio_steps_keys_match_design(self):
        """正式三件套 key 必须为 financial_report/disclosure_notes/audit_report。"""
        keys = [s["key"] for s in TRIO_STEPS]
        assert keys == ["financial_report", "disclosure_notes", "audit_report"]

    def test_trio_steps_sequences_match_design(self):
        """sequence 必须为 1/2/3。"""
        seqs = [s["sequence"] for s in TRIO_STEPS]
        assert seqs == [1, 2, 3]

    def test_trio_step_keys_frozenset(self):
        """TRIO_STEP_KEYS 应包含且只包含正式三项。"""
        assert TRIO_STEP_KEYS == {"financial_report", "disclosure_notes", "audit_report"}

    def test_unadjusted_not_in_trio_steps(self):
        """financial_report_unadjusted 不在 TRIO_STEPS（需求 2.5）。"""
        keys = {s["key"] for s in TRIO_STEPS}
        assert "financial_report_unadjusted" not in keys

    def test_audit_report_dependencies(self):
        """audit_report 前置依赖为 financial_report 和 disclosure_notes。"""
        assert AUDIT_REPORT_DEPENDENCIES == {"financial_report", "disclosure_notes"}

    def test_trio_total_is_three(self):
        """正式三件套固定为 3 项。"""
        assert len(TRIO_STEPS) == 3


# ══════════════════════════════════════════════════════════════════════
# 2. 执行顺序（需求 2.1）
# ══════════════════════════════════════════════════════════════════════

class TestTrioExecutionOrder:
    """验证 run_trio 按 TRIO_STEPS 固定顺序执行。"""

    @pytest.mark.asyncio
    async def test_execution_order_is_fixed(self, test_db, trio_job):
        """步骤必须按 financial_report → disclosure_notes → audit_report 执行。"""
        runner = AllSucceedRunner()
        executor = FullDeliverablesExecutor(test_db)
        snapshot_id = trio_job.snapshot_id

        result = await executor.run_trio(
            job=trio_job,
            snapshot_id=snapshot_id,
            step_runner=runner,
        )

        assert runner.call_order == [
            "financial_report",
            "disclosure_notes",
            "audit_report",
        ], f"执行顺序应为 design 固定顺序，实际: {runner.call_order}"

    @pytest.mark.asyncio
    async def test_outcomes_match_step_order(self, test_db, trio_job):
        """outcomes 列表的 step 顺序应与 TRIO_STEPS 一致。"""
        runner = AllSucceedRunner()
        executor = FullDeliverablesExecutor(test_db)

        result = await executor.run_trio(
            job=trio_job,
            snapshot_id=trio_job.snapshot_id,
            step_runner=runner,
        )

        outcome_steps = [o.step for o in result.outcomes]
        assert outcome_steps == ["financial_report", "disclosure_notes", "audit_report"]


# ══════════════════════════════════════════════════════════════════════
# 3. Snapshot 共享（需求 1.5 / 2.4）
# ══════════════════════════════════════════════════════════════════════

class TestTrioSnapshotSharing:
    """三件套所有 item 共享同一 snapshot_id。"""

    @pytest.mark.asyncio
    async def test_all_items_share_snapshot(self, test_db, trio_job):
        """每个 step_runner.run_step 接收同一 snapshot_id。"""
        runner = RecordSnapshotRunner()
        executor = FullDeliverablesExecutor(test_db)
        snapshot_id = trio_job.snapshot_id

        await executor.run_trio(
            job=trio_job,
            snapshot_id=snapshot_id,
            step_runner=runner,
        )

        for step_key, sid in runner.snapshots.items():
            assert sid == snapshot_id, (
                f"步骤 {step_key} 的 snapshot_id={sid} ≠ job snapshot={snapshot_id}"
            )

    @pytest.mark.asyncio
    async def test_items_have_snapshot_in_db(self, test_db, trio_job):
        """数据库中的 ExportJobItem.snapshot_id 均等于 job 的 snapshot_id。"""
        runner = AllSucceedRunner()
        executor = FullDeliverablesExecutor(test_db)
        snapshot_id = trio_job.snapshot_id

        await executor.run_trio(
            job=trio_job,
            snapshot_id=snapshot_id,
            step_runner=runner,
        )

        import sqlalchemy as sa
        items = (await test_db.execute(
            sa.select(ExportJobItem)
            .where(ExportJobItem.job_id == trio_job.id)
            .order_by(ExportJobItem.sequence)
        )).scalars().all()

        assert len(items) == 3
        for item in items:
            assert item.snapshot_id == snapshot_id


# ══════════════════════════════════════════════════════════════════════
# 4. audit_report 依赖阻断（需求 2.1 / 4.4）
# ══════════════════════════════════════════════════════════════════════

class TestAuditReportDependency:
    """audit_report 在前置失败时标 blocked_by_dependency。"""

    @pytest.mark.asyncio
    async def test_audit_report_blocked_when_financial_report_fails(self, test_db, trio_job):
        """financial_report 失败 → audit_report 标 blocked。"""
        runner = FailOnStepRunner({"financial_report"})
        executor = FullDeliverablesExecutor(test_db)

        result = await executor.run_trio(
            job=trio_job,
            snapshot_id=trio_job.snapshot_id,
            step_runner=runner,
        )

        # audit_report 不应被调用
        assert "audit_report" not in runner.call_order, (
            "audit_report 不应在 financial_report 失败后执行"
        )

        # 验证 outcome
        audit_outcome = next(o for o in result.outcomes if o.step == "audit_report")
        assert not audit_outcome.succeeded
        assert "前置步骤未成功" in audit_outcome.error_message

    @pytest.mark.asyncio
    async def test_audit_report_blocked_when_disclosure_notes_fails(self, test_db, trio_job):
        """disclosure_notes 失败 → audit_report 标 blocked。"""
        runner = FailOnStepRunner({"disclosure_notes"})
        executor = FullDeliverablesExecutor(test_db)

        result = await executor.run_trio(
            job=trio_job,
            snapshot_id=trio_job.snapshot_id,
            step_runner=runner,
        )

        assert "audit_report" not in runner.call_order
        audit_outcome = next(o for o in result.outcomes if o.step == "audit_report")
        assert not audit_outcome.succeeded
        assert "前置步骤未成功" in audit_outcome.error_message

    @pytest.mark.asyncio
    async def test_audit_report_blocked_when_both_predecessors_fail(self, test_db, trio_job):
        """两个前置都失败 → audit_report 同样 blocked。"""
        runner = FailOnStepRunner({"financial_report", "disclosure_notes"})
        executor = FullDeliverablesExecutor(test_db)

        result = await executor.run_trio(
            job=trio_job,
            snapshot_id=trio_job.snapshot_id,
            step_runner=runner,
        )

        assert "audit_report" not in runner.call_order
        audit_outcome = next(o for o in result.outcomes if o.step == "audit_report")
        assert not audit_outcome.succeeded

    @pytest.mark.asyncio
    async def test_audit_report_runs_when_predecessors_succeed(self, test_db, trio_job):
        """前置均成功 → audit_report 正常执行。"""
        runner = AllSucceedRunner()
        executor = FullDeliverablesExecutor(test_db)

        result = await executor.run_trio(
            job=trio_job,
            snapshot_id=trio_job.snapshot_id,
            step_runner=runner,
        )

        assert "audit_report" in runner.call_order
        audit_outcome = next(o for o in result.outcomes if o.step == "audit_report")
        assert audit_outcome.succeeded

    @pytest.mark.asyncio
    async def test_blocked_item_status_in_db(self, test_db, trio_job):
        """blocked 的 item 在数据库中 status=blocked。"""
        runner = FailOnStepRunner({"financial_report"})
        executor = FullDeliverablesExecutor(test_db)

        await executor.run_trio(
            job=trio_job,
            snapshot_id=trio_job.snapshot_id,
            step_runner=runner,
        )

        import sqlalchemy as sa
        audit_item = (await test_db.execute(
            sa.select(ExportJobItem).where(
                ExportJobItem.job_id == trio_job.id,
                ExportJobItem.step_key == "audit_report",
            )
        )).scalar_one()

        assert audit_item.status == ExportJobItemStatus.blocked.value


# ══════════════════════════════════════════════════════════════════════
# 5. 状态聚合（需求 4.4 / design §六）
# ══════════════════════════════════════════════════════════════════════

class TestAggregateTrioStatus:
    """aggregate_trio_status 纯函数测试。"""

    def test_all_succeeded(self):
        statuses = ["succeeded", "succeeded", "succeeded"]
        assert aggregate_trio_status(statuses) == "succeeded"

    def test_all_failed(self):
        statuses = ["failed", "failed", "failed"]
        assert aggregate_trio_status(statuses) == "failed"

    def test_partial_one_failed(self):
        statuses = ["succeeded", "failed", "blocked"]
        assert aggregate_trio_status(statuses) == "partial"

    def test_partial_two_succeeded(self):
        statuses = ["succeeded", "succeeded", "failed"]
        assert aggregate_trio_status(statuses) == "partial"

    def test_blocked_overrides(self):
        statuses = ["succeeded", "succeeded", "succeeded"]
        assert aggregate_trio_status(statuses, has_blockers=True) == "blocked"

    def test_all_blocked_items(self):
        statuses = ["blocked", "blocked", "blocked"]
        assert aggregate_trio_status(statuses) == "failed"

    def test_empty_statuses(self):
        assert aggregate_trio_status([]) == "failed"

    def test_mixed_failed_and_blocked(self):
        statuses = ["failed", "blocked", "failed"]
        assert aggregate_trio_status(statuses) == "failed"


class TestTrioStatusAggregationInRunTrio:
    """run_trio 的 job 状态和 trio_succeeded 聚合。"""

    @pytest.mark.asyncio
    async def test_all_succeed_job_succeeded(self, test_db, trio_job):
        runner = AllSucceedRunner()
        executor = FullDeliverablesExecutor(test_db)

        result = await executor.run_trio(
            job=trio_job,
            snapshot_id=trio_job.snapshot_id,
            step_runner=runner,
        )

        assert result.status == "succeeded"
        assert result.done == 3
        assert result.failed == 0
        assert trio_job.trio_succeeded == 3
        assert trio_job.trio_total == 3

    @pytest.mark.asyncio
    async def test_one_fail_job_partial(self, test_db, trio_job):
        """一步失败 → job partial（disclosure_notes 失败还会级联 audit_report blocked）。"""
        runner = FailOnStepRunner({"disclosure_notes"})
        executor = FullDeliverablesExecutor(test_db)

        result = await executor.run_trio(
            job=trio_job,
            snapshot_id=trio_job.snapshot_id,
            step_runner=runner,
        )

        # disclosure_notes 失败 + audit_report blocked = 只有 financial_report 成功
        assert result.status == "partial"
        assert result.done == 1
        assert trio_job.trio_succeeded == 1

    @pytest.mark.asyncio
    async def test_all_fail_job_failed(self, test_db, trio_job):
        """所有步骤失败 → job failed。"""
        runner = FailOnStepRunner({"financial_report", "disclosure_notes", "audit_report"})
        executor = FullDeliverablesExecutor(test_db)

        result = await executor.run_trio(
            job=trio_job,
            snapshot_id=trio_job.snapshot_id,
            step_runner=runner,
        )

        # financial_report 失败, disclosure_notes 失败, audit_report blocked
        assert result.status == "failed"
        assert result.done == 0
        assert trio_job.trio_succeeded == 0


# ══════════════════════════════════════════════════════════════════════
# 6. 辅助步骤不计入 trio（需求 2.5）
# ══════════════════════════════════════════════════════════════════════

class TestAuxiliaryNotCounted:
    """financial_report_unadjusted 等辅助步骤不进入 TRIO_STEPS。"""

    def test_unadjusted_not_in_trio_step_keys(self):
        assert "financial_report_unadjusted" not in TRIO_STEP_KEYS

    def test_trio_total_always_three(self):
        """无论外部传入什么，TRIO_STEPS 长度固定为 3。"""
        assert len(TRIO_STEPS) == 3

    @pytest.mark.asyncio
    async def test_trio_succeeded_only_counts_formal(self, test_db, trio_job):
        """即使有辅助步骤存在，trio_succeeded 只统计正式三项。"""
        runner = AllSucceedRunner()
        executor = FullDeliverablesExecutor(test_db)

        result = await executor.run_trio(
            job=trio_job,
            snapshot_id=trio_job.snapshot_id,
            step_runner=runner,
        )

        # run_trio 只执行 TRIO_STEPS 中的 3 项
        assert len(result.outcomes) == 3
        assert all(
            o.step in TRIO_STEP_KEYS for o in result.outcomes
        ), "outcomes 应只包含正式三件套步骤"


# ══════════════════════════════════════════════════════════════════════
# 7. 变异证明（mutation tests）
# ══════════════════════════════════════════════════════════════════════

class TestMutationProofs:
    """关键不变量的变异证明。"""

    def test_mutation_swap_step_order(self):
        """变异：调换步骤顺序应被检测到。

        如果有人把 TRIO_STEPS 改成 disclosure_notes → financial_report → audit_report，
        本测试必须红。
        """
        keys = [s["key"] for s in TRIO_STEPS]
        seqs = [s["sequence"] for s in TRIO_STEPS]

        # 验证 key 和 sequence 严格对应
        assert keys[0] == "financial_report" and seqs[0] == 1
        assert keys[1] == "disclosure_notes" and seqs[1] == 2
        assert keys[2] == "audit_report" and seqs[2] == 3

        # 验证 sequence 严格递增
        for i in range(len(seqs) - 1):
            assert seqs[i] < seqs[i + 1], (
                f"sequence 必须严格递增：{seqs[i]} 不小于 {seqs[i + 1]}"
            )

    def test_mutation_auxiliary_counted_as_formal(self):
        """变异：把 financial_report_unadjusted 加入 TRIO_STEPS 应被检测到。"""
        assert len(TRIO_STEPS) == 3, (
            f"TRIO_STEPS 应恰好有 3 项，当前 {len(TRIO_STEPS)} 项"
        )
        assert "financial_report_unadjusted" not in TRIO_STEP_KEYS, (
            "辅助步骤不应在 TRIO_STEP_KEYS 中"
        )

    @pytest.mark.asyncio
    async def test_mutation_audit_report_runs_despite_dependency_failure(
        self, test_db, trio_job
    ):
        """变异：如果去掉依赖检查，audit_report 会在前置失败后仍被执行。

        本测试验证 audit_report 在 financial_report 失败后不应被调用。
        """
        runner = FailOnStepRunner({"financial_report"})
        executor = FullDeliverablesExecutor(test_db)

        result = await executor.run_trio(
            job=trio_job,
            snapshot_id=trio_job.snapshot_id,
            step_runner=runner,
        )

        # 如果去掉依赖检查，runner.call_order 会包含 "audit_report"
        assert "audit_report" not in runner.call_order, (
            "变异检测：audit_report 不应在 financial_report 失败后执行。"
            "如果本测试红，说明依赖检查被移除。"
        )

        # 进一步验证：audit_report 的 item 状态应为 blocked
        audit_outcome = next(o for o in result.outcomes if o.step == "audit_report")
        assert not audit_outcome.succeeded
        assert "前置步骤未成功" in audit_outcome.error_message

    def test_mutation_aggregate_miscount(self):
        """变异：如果 aggregate_trio_status 把 blocked 算成 succeeded。

        把三个 blocked 传入应得 failed 而非 succeeded。
        """
        result = aggregate_trio_status(["blocked", "blocked", "blocked"])
        assert result != "succeeded", (
            "变异检测：全 blocked 不应聚合为 succeeded"
        )
        assert result == "failed"

    @pytest.mark.asyncio
    async def test_mutation_trio_succeeded_includes_auxiliary(self, test_db, trio_job):
        """变异：trio_succeeded 不应统计非 TRIO_STEPS 中的步骤。

        run_trio 只执行正式三项，outcomes 中不应出现辅助步骤。
        """
        runner = AllSucceedRunner()
        executor = FullDeliverablesExecutor(test_db)

        result = await executor.run_trio(
            job=trio_job,
            snapshot_id=trio_job.snapshot_id,
            step_runner=runner,
        )

        # 如果有人偷偷把 unadjusted 加进去，done 会大于 3
        assert result.done <= 3, (
            f"trio_succeeded 不应超过 3，当前 {result.done}"
        )
        assert trio_job.trio_total == 3


# ══════════════════════════════════════════════════════════════════════
# 8. ORM item 字段验证
# ══════════════════════════════════════════════════════════════════════

class TestItemFieldsInDB:
    """run_trio 创建的 ExportJobItem 在数据库中字段正确。"""

    @pytest.mark.asyncio
    async def test_items_have_step_key_and_sequence(self, test_db, trio_job):
        """每个 item 的 step_key 和 sequence 与 TRIO_STEPS 对应。"""
        runner = AllSucceedRunner()
        executor = FullDeliverablesExecutor(test_db)

        await executor.run_trio(
            job=trio_job,
            snapshot_id=trio_job.snapshot_id,
            step_runner=runner,
        )

        import sqlalchemy as sa
        items = (await test_db.execute(
            sa.select(ExportJobItem)
            .where(ExportJobItem.job_id == trio_job.id)
            .order_by(ExportJobItem.sequence)
        )).scalars().all()

        assert len(items) == 3
        for i, item in enumerate(items):
            expected = TRIO_STEPS[i]
            assert item.step_key == expected["key"], (
                f"item[{i}].step_key={item.step_key} ≠ {expected['key']}"
            )
            assert item.sequence == expected["sequence"], (
                f"item[{i}].sequence={item.sequence} ≠ {expected['sequence']}"
            )

    @pytest.mark.asyncio
    async def test_succeeded_items_status_correct(self, test_db, trio_job):
        """成功的 item 在 DB 中 status=succeeded。"""
        runner = AllSucceedRunner()
        executor = FullDeliverablesExecutor(test_db)

        await executor.run_trio(
            job=trio_job,
            snapshot_id=trio_job.snapshot_id,
            step_runner=runner,
        )

        import sqlalchemy as sa
        items = (await test_db.execute(
            sa.select(ExportJobItem)
            .where(ExportJobItem.job_id == trio_job.id)
        )).scalars().all()

        for item in items:
            assert item.status == ExportJobItemStatus.succeeded.value

    @pytest.mark.asyncio
    async def test_failed_item_has_error_message(self, test_db, trio_job):
        """失败的 item 在 DB 中有 error_message。"""
        runner = FailOnStepRunner({"disclosure_notes"})
        executor = FullDeliverablesExecutor(test_db)

        await executor.run_trio(
            job=trio_job,
            snapshot_id=trio_job.snapshot_id,
            step_runner=runner,
        )

        import sqlalchemy as sa
        note_item = (await test_db.execute(
            sa.select(ExportJobItem).where(
                ExportJobItem.job_id == trio_job.id,
                ExportJobItem.step_key == "disclosure_notes",
            )
        )).scalar_one()

        assert note_item.status == ExportJobItemStatus.failed.value
        assert note_item.error_message is not None
        assert "disclosure_notes" in note_item.error_message
