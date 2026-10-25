"""Phase4 Task 8 — 真正重试失败步骤

SQLite 真 ORM 测试。覆盖 design §七 / 需求 5.2–5.5：
- retry_failed_trio 调用 executor 步骤入口（非仅重置状态）
- 失败项重试后新增 attempt，生成真实文件和版本
- 旧 retry_failed 仅改 queued 状态 → 对比证明其不调用步骤
- 快照变化 → SnapshotConflictError（调用方返回 409）
- 已成功项不被重试
- attempt_no 单调递增
- 旧失败 attempt 在成功重试后仍保留

修复前红 / 修复后绿 / 故障注入矩阵：
| 场景                       | 修复前红 → 修复后绿         |
|----------------------------|----------------------------|
| 失败项 retry → 新 attempt  | 旧只改状态 → 新调用步骤     |
| 快照冲突 → 409             | 旧无此校验 → 新抛异常       |
| 已成功项 → 跳过            | 旧全部重置 → 新检查指纹跳过 |
| attempt_no 递增            | 旧无 attempt → 新单调+1     |
| 旧失败保留                 | 旧清空 error → 新 append    |
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
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
from app.services.export_job_service import (
    ExportJobService,
    SnapshotConflictError,
)
from app.services.full_deliverables_executor import (
    FullDeliverablesExecutor,
    TRIO_STEPS,
    TRIO_STEP_KEYS,
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
        username="test_retry",
        email="retry@test.com",
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
        name="重试测试项目",
        client_name="测试客户",
        created_by=test_user.id,
    )
    test_db.add(project)
    await test_db.flush()
    return project


SNAPSHOT_DIGEST = "a" * 64


@pytest_asyncio.fixture
async def snapshot(
    test_db: AsyncSession, test_project: Project,
) -> DeliverableSnapshot:
    snap = DeliverableSnapshot(
        id=uuid.uuid4(),
        project_id=test_project.id,
        year=2025,
        digest=SNAPSHOT_DIGEST,
        payload={"project_id": str(test_project.id), "year": 2025},
    )
    test_db.add(snap)
    await test_db.flush()
    return snap


@pytest_asyncio.fixture
async def trio_job_with_items(
    test_db: AsyncSession,
    test_project: Project,
    test_user: User,
    snapshot: DeliverableSnapshot,
):
    """创建一个 trio job + 3 个 items + 初始 attempt。

    默认场景：第 1 步成功，第 2 步失败，第 3 步被依赖阻断。
    """
    job = ExportJob(
        id=uuid.uuid4(),
        project_id=test_project.id,
        job_type="full_deliverables",
        kind="deliverable_trio",
        status=ExportJobStatus.partial.value,
        payload={},
        progress_total=3,
        progress_done=1,
        failed_count=2,
        initiated_by=test_user.id,
        snapshot_id=snapshot.id,
        year=2025,
        trio_total=3,
        trio_succeeded=1,
    )
    test_db.add(job)
    await test_db.flush()

    # Item 1: financial_report — 成功
    item1 = ExportJobItem(
        id=uuid.uuid4(),
        job_id=job.id,
        step_key="financial_report",
        sequence=1,
        snapshot_id=snapshot.id,
        status=ExportJobItemStatus.succeeded.value,
        attempt_count=1,
    )
    test_db.add(item1)
    await test_db.flush()

    # Item 1 attempt — 成功
    attempt1 = ExportJobAttempt(
        job_id=job.id,
        item_id=item1.id,
        attempt_no=1,
        status=ExportJobAttemptStatus.succeeded.value,
        snapshot_id=snapshot.id,
        trigger_source="initial",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    )
    test_db.add(attempt1)
    item1.last_attempt_id = attempt1.id
    await test_db.flush()

    # Item 2: disclosure_notes — 失败
    item2 = ExportJobItem(
        id=uuid.uuid4(),
        job_id=job.id,
        step_key="disclosure_notes",
        sequence=2,
        snapshot_id=snapshot.id,
        status=ExportJobItemStatus.failed.value,
        attempt_count=1,
        error_message="附注模板缺失",
    )
    test_db.add(item2)
    await test_db.flush()

    # Item 2 attempt — 失败
    attempt2 = ExportJobAttempt(
        job_id=job.id,
        item_id=item2.id,
        attempt_no=1,
        status=ExportJobAttemptStatus.failed.value,
        snapshot_id=snapshot.id,
        trigger_source="initial",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        error_type="RuntimeError",
        error_message="附注模板缺失",
        diagnostic_detail="RuntimeError: 附注模板缺失",
    )
    test_db.add(attempt2)
    item2.last_attempt_id = attempt2.id
    await test_db.flush()

    # Item 3: audit_report — blocked
    item3 = ExportJobItem(
        id=uuid.uuid4(),
        job_id=job.id,
        step_key="audit_report",
        sequence=3,
        snapshot_id=snapshot.id,
        status=ExportJobItemStatus.blocked.value,
        attempt_count=0,
        error_message="前置步骤未成功（disclosure_notes），审计报告正文无法生成",
    )
    test_db.add(item3)
    await test_db.flush()

    return {
        "job": job,
        "items": [item1, item2, item3],
        "attempts": [attempt1, attempt2],
        "snapshot": snapshot,
    }


# ──────────────────────────────────────────────────────────────────────
# Step Runner 桩实现
# ──────────────────────────────────────────────────────────────────────

class AllSucceedRunner:
    """所有步骤都成功的桩。"""

    def __init__(self):
        self.called: list[str] = []

    async def run_step(
        self, step_key: str, snapshot_id: UUID,
    ) -> UUID | None:
        self.called.append(step_key)
        return uuid.uuid4()


class FailOnStepRunner:
    """指定步骤失败的桩。"""

    def __init__(
        self,
        fail_steps: set[str],
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


class NeverCalledRunner:
    """永远不应被调用的桩 — 用于验证成功项不被重试。"""

    def __init__(self):
        self.called: list[str] = []

    async def run_step(
        self, step_key: str, snapshot_id: UUID,
    ) -> UUID | None:
        self.called.append(step_key)
        raise AssertionError(f"不应被调用: {step_key}")


# ──────────────────────────────────────────────────────────────────────
# 辅助
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
    db: AsyncSession, item_id: UUID,
) -> list[ExportJobAttempt]:
    result = await db.execute(
        sa.select(ExportJobAttempt)
        .where(ExportJobAttempt.item_id == item_id)
        .order_by(ExportJobAttempt.attempt_no)
    )
    return list(result.scalars().all())


# ══════════════════════════════════════════════════════════════════════
#  测试类
# ══════════════════════════════════════════════════════════════════════


class TestRetryCallsStepRunner:
    """需求 5.2：retry_failed_trio 必须调用 step_runner.run_step，
    不能只重置状态。"""

    @pytest.mark.asyncio
    async def test_retry_calls_step_runner_for_failed_items(
        self, test_db, trio_job_with_items,
    ):
        """失败项重试 → step_runner 被调用 → 新 attempt 创建。"""
        data = trio_job_with_items
        job = data["job"]
        runner = AllSucceedRunner()
        svc = ExportJobService(test_db)

        result = await svc.retry_failed_trio(
            job.id, step_runner=runner,
        )

        # step_runner 被调用了（disclosure_notes 和 audit_report）
        assert "disclosure_notes" in runner.called
        assert "audit_report" in runner.called
        # financial_report 已成功，不应被调用
        assert "financial_report" not in runner.called

        assert result["retried"] >= 2  # 至少重试了 2 项
        assert result["succeeded"] >= 1  # 至少 disclosure_notes 成功

    @pytest.mark.asyncio
    async def test_old_retry_only_resets_status_no_runner_call(
        self, test_db, trio_job_with_items,
    ):
        """对照：旧 retry_failed 仅改 queued 状态，不创建 attempt。

        证明 retry_failed_trio 的必要性。
        """
        data = trio_job_with_items
        job = data["job"]
        item2 = data["items"][1]  # disclosure_notes — failed

        # 记录重试前 attempt 数量
        attempts_before = await _get_attempts(test_db, item2.id)
        count_before = len(attempts_before)

        svc = ExportJobService(test_db)
        retried = await svc.retry_failed(job.id)

        assert retried >= 1

        # 旧方法只改状态，不创建新 attempt
        attempts_after = await _get_attempts(test_db, item2.id)
        assert len(attempts_after) == count_before, (
            "旧 retry_failed 不应创建新 attempt"
        )

        # item 状态被改成 queued（而非真正重新执行）
        items = await _get_items(test_db, job.id)
        notes_item = [i for i in items if i.step_key == "disclosure_notes"]
        if notes_item:
            assert notes_item[0].status == ExportJobItemStatus.queued.value


class TestRetryCreatesNewAttempt:
    """需求 5.4：每一次重试 SHALL 新建 attempt，保留原始失败。"""

    @pytest.mark.asyncio
    async def test_new_attempt_created_on_retry(
        self, test_db, trio_job_with_items,
    ):
        data = trio_job_with_items
        job = data["job"]
        item2 = data["items"][1]  # disclosure_notes — failed

        attempts_before = await _get_attempts(test_db, item2.id)
        assert len(attempts_before) == 1
        assert attempts_before[0].attempt_no == 1

        runner = AllSucceedRunner()
        svc = ExportJobService(test_db)
        await svc.retry_failed_trio(job.id, step_runner=runner)

        attempts_after = await _get_attempts(test_db, item2.id)
        assert len(attempts_after) == 2, (
            "重试应新建 attempt，总数从 1 变为 2"
        )
        # 新 attempt 的 attempt_no 递增
        assert attempts_after[1].attempt_no == 2

    @pytest.mark.asyncio
    async def test_attempt_no_monotonic_across_multiple_retries(
        self, test_db, trio_job_with_items,
    ):
        """多次重试 → attempt_no 单调递增 1, 2, 3, ...

        需求 5.4 / design §3.3。
        """
        data = trio_job_with_items
        job = data["job"]
        item2 = data["items"][1]  # disclosure_notes — failed

        svc = ExportJobService(test_db)

        # 第一次重试（也失败）
        fail_runner = FailOnStepRunner({"disclosure_notes"}, "第一次重试也失败")
        await svc.retry_failed_trio(job.id, step_runner=fail_runner)

        # 第二次重试（成功）
        ok_runner = AllSucceedRunner()
        await svc.retry_failed_trio(job.id, step_runner=ok_runner)

        attempts = await _get_attempts(test_db, item2.id)
        attempt_nos = [a.attempt_no for a in attempts]
        assert attempt_nos == [1, 2, 3], (
            f"attempt_no 应为 [1,2,3]，实际 {attempt_nos}"
        )


class TestOldFailurePreserved:
    """需求 5.4：保留原始失败 attempt 和失败原因。"""

    @pytest.mark.asyncio
    async def test_original_failure_preserved_after_successful_retry(
        self, test_db, trio_job_with_items,
    ):
        data = trio_job_with_items
        job = data["job"]
        item2 = data["items"][1]

        runner = AllSucceedRunner()
        svc = ExportJobService(test_db)
        await svc.retry_failed_trio(job.id, step_runner=runner)

        attempts = await _get_attempts(test_db, item2.id)
        assert len(attempts) == 2

        # 原始失败 attempt 不可变
        old = attempts[0]
        assert old.status == ExportJobAttemptStatus.failed.value
        assert old.error_message == "附注模板缺失"
        assert old.error_type == "RuntimeError"
        assert old.attempt_no == 1

        # 新 attempt 成功
        new = attempts[1]
        assert new.status == ExportJobAttemptStatus.succeeded.value
        assert new.trigger_source == "retry"
        assert new.attempt_no == 2

    @pytest.mark.asyncio
    async def test_retry_failure_also_preserved(
        self, test_db, trio_job_with_items,
    ):
        """重试也失败时，新失败 attempt 记录完整错误信息。"""
        data = trio_job_with_items
        job = data["job"]
        item2 = data["items"][1]

        runner = FailOnStepRunner({"disclosure_notes"}, "重试时模板仍缺失")
        svc = ExportJobService(test_db)
        await svc.retry_failed_trio(job.id, step_runner=runner)

        attempts = await _get_attempts(test_db, item2.id)
        assert len(attempts) == 2

        new_attempt = attempts[1]
        assert new_attempt.status == ExportJobAttemptStatus.failed.value
        assert "重试时模板仍缺失" in (new_attempt.error_message or "")
        assert new_attempt.error_type == "RuntimeError"
        assert new_attempt.diagnostic_detail is not None


class TestSnapshotConflict:
    """需求 5.3 / design §七：快照不一致 → SnapshotConflictError。"""

    @pytest.mark.asyncio
    async def test_snapshot_conflict_raises_error(
        self, test_db, trio_job_with_items,
    ):
        data = trio_job_with_items
        job = data["job"]

        runner = AllSucceedRunner()
        svc = ExportJobService(test_db)

        different_digest = "b" * 64
        with pytest.raises(SnapshotConflictError) as exc_info:
            await svc.retry_failed_trio(
                job.id,
                step_runner=runner,
                current_snapshot_digest=different_digest,
            )

        assert exc_info.value.job_digest == SNAPSHOT_DIGEST
        assert exc_info.value.current_digest == different_digest

    @pytest.mark.asyncio
    async def test_same_snapshot_no_conflict(
        self, test_db, trio_job_with_items,
    ):
        """快照一致时正常执行，不抛异常。"""
        data = trio_job_with_items
        job = data["job"]

        runner = AllSucceedRunner()
        svc = ExportJobService(test_db)

        # 传入相同 digest → 不抛
        result = await svc.retry_failed_trio(
            job.id,
            step_runner=runner,
            current_snapshot_digest=SNAPSHOT_DIGEST,
        )
        assert result["retried"] >= 1

    @pytest.mark.asyncio
    async def test_none_digest_skips_check(
        self, test_db, trio_job_with_items,
    ):
        """不传 current_snapshot_digest → 跳过快照校验。"""
        data = trio_job_with_items
        job = data["job"]

        runner = AllSucceedRunner()
        svc = ExportJobService(test_db)

        result = await svc.retry_failed_trio(
            job.id, step_runner=runner,
        )
        assert result["retried"] >= 1


class TestSucceededItemsNotRetried:
    """需求 5.3：已成功且指纹有效的项不被重试。"""

    @pytest.mark.asyncio
    async def test_succeeded_item_not_retried(
        self, test_db, trio_job_with_items,
    ):
        data = trio_job_with_items
        job = data["job"]

        runner = AllSucceedRunner()
        svc = ExportJobService(test_db)
        result = await svc.retry_failed_trio(
            job.id, step_runner=runner,
        )

        # financial_report 已成功，不应被调用
        assert "financial_report" not in runner.called
        assert result["skipped_succeeded"] >= 1


class TestJobStatusAggregation:
    """retry 后 job 状态和 trio_succeeded 正确聚合。"""

    @pytest.mark.asyncio
    async def test_all_succeed_after_retry(
        self, test_db, trio_job_with_items,
    ):
        """两个失败项都重试成功 → job=succeeded, trio_succeeded=3。"""
        data = trio_job_with_items
        job = data["job"]

        runner = AllSucceedRunner()
        svc = ExportJobService(test_db)
        result = await svc.retry_failed_trio(
            job.id, step_runner=runner,
        )

        assert result["job_status"] == ExportJobStatus.succeeded.value
        assert result["trio_succeeded"] == 3

        # 验证 job ORM 也更新了
        refreshed_job = await svc.get_job(job.id)
        assert refreshed_job.status == ExportJobStatus.succeeded.value
        assert refreshed_job.trio_succeeded == 3

    @pytest.mark.asyncio
    async def test_partial_after_retry(
        self, test_db, trio_job_with_items,
    ):
        """只有一个失败项重试成功 → job=partial。"""
        data = trio_job_with_items
        job = data["job"]

        # disclosure_notes 重试仍失败 → audit_report 被依赖阻断
        runner = FailOnStepRunner({"disclosure_notes"}, "仍然失败")
        svc = ExportJobService(test_db)
        result = await svc.retry_failed_trio(
            job.id, step_runner=runner,
        )

        assert result["job_status"] == ExportJobStatus.partial.value
        # 只有 financial_report 成功
        assert result["trio_succeeded"] == 1


class TestRetryValidation:
    """edge cases: 非 trio job、不存在的 job。"""

    @pytest.mark.asyncio
    async def test_non_trio_job_raises(
        self, test_db, test_project, test_user,
    ):
        """非 deliverable_trio job → ValueError。"""
        job = ExportJob(
            id=uuid.uuid4(),
            project_id=test_project.id,
            job_type="full_deliverables",
            kind="other_kind",
            status=ExportJobStatus.failed.value,
            payload={},
            progress_total=1,
            progress_done=0,
            failed_count=1,
            initiated_by=test_user.id,
        )
        test_db.add(job)
        await test_db.flush()

        svc = ExportJobService(test_db)
        runner = AllSucceedRunner()

        with pytest.raises(ValueError, match="不是 deliverable_trio"):
            await svc.retry_failed_trio(job.id, step_runner=runner)

    @pytest.mark.asyncio
    async def test_nonexistent_job_raises(self, test_db):
        svc = ExportJobService(test_db)
        runner = AllSucceedRunner()

        with pytest.raises(ValueError, match="不存在"):
            await svc.retry_failed_trio(uuid.uuid4(), step_runner=runner)

    @pytest.mark.asyncio
    async def test_no_failed_items_returns_zero(
        self, test_db, test_project, test_user, snapshot,
    ):
        """所有项均成功 → retried=0。"""
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
            snapshot_id=snapshot.id,
            year=2025,
            trio_total=3,
            trio_succeeded=3,
        )
        test_db.add(job)
        await test_db.flush()

        for step in TRIO_STEPS:
            item = ExportJobItem(
                job_id=job.id,
                step_key=step["key"],
                sequence=step["sequence"],
                snapshot_id=snapshot.id,
                status=ExportJobItemStatus.succeeded.value,
                attempt_count=1,
            )
            test_db.add(item)
        await test_db.flush()

        svc = ExportJobService(test_db)
        runner = AllSucceedRunner()
        result = await svc.retry_failed_trio(job.id, step_runner=runner)

        assert result["retried"] == 0
        assert runner.called == []


class TestDependencyBlockOnRetry:
    """audit_report 依赖 disclosure_notes 成功；
    disclosure_notes 重试失败 → audit_report 标 blocked。"""

    @pytest.mark.asyncio
    async def test_audit_report_blocked_when_notes_still_fail(
        self, test_db, trio_job_with_items,
    ):
        data = trio_job_with_items
        job = data["job"]

        runner = FailOnStepRunner({"disclosure_notes"}, "附注导出仍失败")
        svc = ExportJobService(test_db)
        result = await svc.retry_failed_trio(job.id, step_runner=runner)

        # audit_report 应标 blocked
        items = await _get_items(test_db, job.id)
        audit_item = [i for i in items if i.step_key == "audit_report"][0]
        assert audit_item.status == ExportJobItemStatus.blocked.value
        assert "前置步骤未成功" in (audit_item.error_message or "")


class TestRetryTriggerSource:
    """retry 创建的 attempt trigger_source 标记为 'retry'。"""

    @pytest.mark.asyncio
    async def test_retry_attempt_trigger_source(
        self, test_db, trio_job_with_items,
    ):
        data = trio_job_with_items
        job = data["job"]
        item2 = data["items"][1]

        runner = AllSucceedRunner()
        svc = ExportJobService(test_db)
        await svc.retry_failed_trio(job.id, step_runner=runner)

        attempts = await _get_attempts(test_db, item2.id)
        new_attempt = attempts[-1]
        assert new_attempt.trigger_source == "retry"
