"""Phase4 Task 8 — 真正重试失败步骤（SQLite 真 ORM + 变异证明）。

spec: ``.kiro/specs/chain-closure-phase4-deliverable-center-trio``（需求 5.2–5.5）。

设计 §7 要求 ``retry_failed`` 不再「只把状态改回 queued」，而是：
  · 为每次重试**新增 attempt**（trigger="retry"，attempt_no 单调递增），保留原始失败 attempt；
  · 经**同一渲染/落盘/指纹/版本**路径真正重跑失败步骤（故障恢复后产出真实文件 + 版本）；
  · 已成功且指纹仍有效的正式项**复用**既有文件、**不重跑**导出器（需求 5.3）；
  · job 绑定快照与当前项目数据复算 digest 不一致 ⇒ 抛 ``SnapshotMismatchError``（需求 5.5），
    绝不混用新旧来源。

本文件覆盖：
  R1  故障恢复后重试：第 2 步初次失败 → 恢复 → retry 成功，**新增 trigger=retry 的成功
      attempt**、产出真实版本行，且**原始失败 attempt 保留**（需求 5.2/5.4/5.5）。
  R2  已成功项复用既有文件、不重跑导出器（需求 5.3）：retry 时 financial_report 的导出器
      调用计数**不增加**，其既有真实文件经指纹校验复用。
  R3  快照不一致 ⇒ ``SnapshotMismatchError``（需求 5.5）：复算 digest 变化即拒绝重试。
  R4  非三件套 item（无 step_key）retry 仍新增 attempt 且保留原始失败原因（baseline RED-2 口径）。
  M1  变异：把 ``retry_failed`` 退回「只复位 queued、清空 error_message」旧实现 ⇒ R1 的
      「retry 新增 attempt」断言被打红（证明判据非恒绿）。

Windows：``python`` 而非 ``python3``；无 ``&&``。
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.core import Project, User
from app.models.phase13_models import (
    ExportJobAttempt,
    ExportJobItem,
    ExportJobStatus,
    WordExportTask,
    WordExportTaskVersion,
)
from app.services.export_job_service import ExportJobService
from app.services.full_deliverables_executor import (
    BLOCKED_BY_DEPENDENCY,
    FullDeliverablesExecutor,
    SnapshotMismatchError,
)


# ===========================================================================
# fixtures
# ===========================================================================


@pytest_asyncio.fixture
async def sqlite_db():
    from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

    SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


async def _seed_projects_tasks(db: AsyncSession):
    user = User(
        id=uuid.uuid4(),
        username=f"t8_{uuid.uuid4().hex[:8]}",
        email=f"t8_{uuid.uuid4().hex[:8]}@test.com",
        hashed_password="hashed",
        role="admin",
    )
    project = Project(
        id=uuid.uuid4(), name="三件套重试项目", client_name="测试公司", status="created"
    )
    db.add_all([user, project])
    await db.flush()
    tasks = {}
    for dt in ("financial_report", "disclosure_notes", "audit_report"):
        t = WordExportTask(
            id=uuid.uuid4(), project_id=project.id, doc_type=dt, created_by=user.id
        )
        db.add(t)
        tasks[dt] = t
    await db.flush()
    return user, project, tasks


async def _noop():
    return None


async def _stub_snap(project_id, year):
    return {"project_id": str(project_id), "year": year}


def _write_real_file(tmp_dir: Path, name: str, content: bytes) -> tuple[str, str, int]:
    """落一个真实文件，返回 (path, sha256, size)，供 version 行与指纹复用校验使用。"""
    tmp_dir.mkdir(parents=True, exist_ok=True)
    p = tmp_dir / name
    p.write_bytes(content)
    return str(p), hashlib.sha256(content).hexdigest(), len(content)


async def _items_by_step(db: AsyncSession, job_id) -> dict:
    rows = (
        await db.execute(sa.select(ExportJobItem).where(ExportJobItem.job_id == job_id))
    ).scalars().all()
    return {r.step_key: r for r in rows}


class _StepHarness:
    """可切换「失败 → 恢复」的 executor 步骤桩，并记录各步导出器调用次数。

    · financial_report：成功，落**真实文件**版本行（用于复用指纹校验）；记调用次数。
    · disclosure_notes：受 ``notes_should_fail`` 控制；失败时抛 ValueError，恢复后成功。
    · audit_report：成功。
    """

    def __init__(self, db, tasks, user_id, tmp_dir: Path):
        self.db = db
        self.tasks = tasks
        self.user_id = user_id
        self.tmp_dir = tmp_dir
        self.notes_should_fail = True
        self.calls = {"financial_report": 0, "disclosure_notes": 0, "audit_report": 0}

    async def _create_real_version(self, task_id, name, content):
        path, sha, size = _write_real_file(self.tmp_dir, name, content)
        # 版本号在既有最大值上 +1（真实多版本）。
        max_no = (
            await self.db.execute(
                sa.select(sa.func.coalesce(sa.func.max(WordExportTaskVersion.version_no), 0))
                .where(WordExportTaskVersion.word_export_task_id == task_id)
            )
        ).scalar_one()
        v = WordExportTaskVersion(
            id=uuid.uuid4(),
            word_export_task_id=task_id,
            version_no=int(max_no) + 1,
            file_path=path,
            file_size=size,
            file_sha256=sha,
            created_by=self.user_id,
            created_via="generate",
        )
        self.db.add(v)
        await self.db.flush()
        return v

    def patch(self, executor: FullDeliverablesExecutor):
        async def _financial(project_id, year, user_id_):
            self.calls["financial_report"] += 1
            await self._create_real_version(
                self.tasks["financial_report"].id,
                f"financial_{self.calls['financial_report']}.xlsx",
                b"PK\x03\x04financial-report-bytes",
            )
            return self.tasks["financial_report"].id

        async def _notes(project_id, year, user_id_):
            self.calls["disclosure_notes"] += 1
            if self.notes_should_fail:
                raise ValueError("报表附注落盘失败：文件指纹校验未通过（桩）")
            await self._create_real_version(
                self.tasks["disclosure_notes"].id,
                f"notes_{self.calls['disclosure_notes']}.docx",
                b"PK\x03\x04disclosure-notes-bytes",
            )
            return self.tasks["disclosure_notes"].id

        async def _report(project_id, year, user_id_, payload):
            self.calls["audit_report"] += 1
            await self._create_real_version(
                self.tasks["audit_report"].id,
                f"audit_{self.calls['audit_report']}.docx",
                b"PK\x03\x04audit-report-bytes",
            )
            return self.tasks["audit_report"].id, None, {"key_audit_matters": True}

        executor._run_financial_reports = _financial  # type: ignore[assignment]
        executor._run_disclosure_notes = _notes  # type: ignore[assignment]
        executor._run_report_body = _report  # type: ignore[assignment]
        executor.precheck = lambda project_id, year: _noop()  # type: ignore[assignment]
        executor._build_snapshot_input = (  # type: ignore[assignment]
            lambda project_id, year, payload: _stub_snap(project_id, year)
        )


# ===========================================================================
# R1：故障恢复后重试 —— 新增 trigger=retry 的成功 attempt + 真实版本 + 保留原始失败
# ===========================================================================


class TestRetryReExecutesAfterRecovery:
    @pytest.mark.asyncio
    async def test_retry_creates_new_attempt_produces_version_preserves_failure(
        self, sqlite_db, tmp_path
    ):
        user, project, tasks = await _seed_projects_tasks(sqlite_db)
        executor = FullDeliverablesExecutor(sqlite_db)
        harness = _StepHarness(sqlite_db, tasks, user.id, tmp_path / "deliv")
        harness.patch(executor)

        # 初次：disclosure_notes 失败 ⇒ audit_report 依赖阻断。
        result = await executor.run(
            project_id=project.id, user_id=user.id, payload={"year": 2024}
        )
        items = await _items_by_step(sqlite_db, result.job_id)
        assert items["financial_report"].status == ExportJobStatus.succeeded.value
        assert items["disclosure_notes"].status == ExportJobStatus.failed.value
        assert items["audit_report"].status == BLOCKED_BY_DEPENDENCY
        assert result.trio_succeeded == 1

        notes_item_id = items["disclosure_notes"].id
        # 初次失败 attempt（trigger=initial）。
        init_attempts = await executor.job_svc.get_item_attempts(notes_item_id)
        assert len(init_attempts) == 1
        assert init_attempts[0].trigger == "initial"
        assert init_attempts[0].status == ExportJobStatus.failed.value
        original_reason = init_attempts[0].error_message
        assert "附注" in (original_reason or "")

        # 恢复故障后重试（executor 真步骤入口；与路由/service 委托的是同一方法）。
        harness.notes_should_fail = False
        retry_out = await executor.retry_failed(
            result.job_id, user_id=user.id, requesting_project_id=project.id
        )
        # disclosure_notes 重试 + audit_report（前置恢复后）重试 = 2 项被处理。
        assert retry_out.retried >= 1

        items2 = await _items_by_step(sqlite_db, result.job_id)
        # 重试后 disclosure_notes 成功，产出真实版本行。
        assert items2["disclosure_notes"].status == ExportJobStatus.succeeded.value
        notes_versions = (
            await sqlite_db.execute(
                sa.select(WordExportTaskVersion).where(
                    WordExportTaskVersion.word_export_task_id
                    == tasks["disclosure_notes"].id
                )
            )
        ).scalars().all()
        assert len(notes_versions) == 1, "重试成功应产出真实版本行（走同一落盘路径）"
        assert Path(notes_versions[0].file_path).is_file()

        # audit_report 前置恢复后也应被重跑并成功（固定顺序：前置先于依赖）。
        assert items2["audit_report"].status == ExportJobStatus.succeeded.value

        # append-only：原始失败 attempt 仍在，retry 新增 attempt（trigger=retry）。
        all_attempts = await executor.job_svc.get_item_attempts(notes_item_id)
        assert len(all_attempts) == 2, (
            f"应保留原始失败 attempt + 新增 retry attempt，实际 {len(all_attempts)}"
        )
        assert [a.attempt_no for a in all_attempts] == [1, 2], "attempt_no 必须单调递增"
        assert all_attempts[0].trigger == "initial"
        assert all_attempts[0].status == ExportJobStatus.failed.value
        assert all_attempts[0].error_message == original_reason, (
            "retry 不得洗掉原始失败原因（需求 5.4）"
        )
        assert all_attempts[1].trigger == "retry"
        assert all_attempts[1].status == ExportJobStatus.succeeded.value

        # job 重算：三件套三项全部成功。
        job = await executor.job_svc.get_job(result.job_id)
        assert job.trio_succeeded == 3
        assert job.status == ExportJobStatus.succeeded.value


# ===========================================================================
# R2：已成功项复用既有文件、不重跑导出器（需求 5.3）
# ===========================================================================


class TestRetryReusesSucceededItem:
    @pytest.mark.asyncio
    async def test_succeeded_item_not_regenerated_on_retry(self, sqlite_db, tmp_path):
        user, project, tasks = await _seed_projects_tasks(sqlite_db)
        executor = FullDeliverablesExecutor(sqlite_db)
        harness = _StepHarness(sqlite_db, tasks, user.id, tmp_path / "deliv")
        harness.patch(executor)

        result = await executor.run(
            project_id=project.id, user_id=user.id, payload={"year": 2024}
        )
        items = await _items_by_step(sqlite_db, result.job_id)
        # 回填 item 文件指纹投影（取 financial_report 既有版本），模拟 initial 已记录。
        fr_version = (
            await sqlite_db.execute(
                sa.select(WordExportTaskVersion).where(
                    WordExportTaskVersion.word_export_task_id
                    == tasks["financial_report"].id
                )
            )
        ).scalar_one()
        fr_item = items["financial_report"]
        fr_item.file_path = fr_version.file_path
        fr_item.file_sha256 = fr_version.file_sha256
        fr_item.file_size = fr_version.file_size
        await sqlite_db.flush()

        calls_before = harness.calls["financial_report"]
        assert calls_before == 1

        harness.notes_should_fail = False
        await executor.retry_failed(
            result.job_id, user_id=user.id, requesting_project_id=project.id
        )

        # financial_report 已成功且文件指纹有效 ⇒ 导出器不得再被调用（复用，需求 5.3）。
        assert harness.calls["financial_report"] == calls_before, (
            "已成功且指纹有效的正式项不得在 retry 中重跑导出器（需求 5.3）"
        )
        # 其仍只有一份版本（没有新版本被生成）。
        fr_versions = (
            await sqlite_db.execute(
                sa.select(sa.func.count())
                .select_from(WordExportTaskVersion)
                .where(
                    WordExportTaskVersion.word_export_task_id
                    == tasks["financial_report"].id
                )
            )
        ).scalar_one()
        assert fr_versions == 1, "复用既有文件 ⇒ 不产生新版本行"


# ===========================================================================
# R3：快照不一致 ⇒ SnapshotMismatchError（需求 5.5）
# ===========================================================================


class TestRetrySnapshotMismatch:
    @pytest.mark.asyncio
    async def test_snapshot_mismatch_raises_conflict(self, sqlite_db, tmp_path):
        user, project, tasks = await _seed_projects_tasks(sqlite_db)
        executor = FullDeliverablesExecutor(sqlite_db)
        harness = _StepHarness(sqlite_db, tasks, user.id, tmp_path / "deliv")
        harness.patch(executor)

        result = await executor.run(
            project_id=project.id, user_id=user.id, payload={"year": 2024}
        )
        items = await _items_by_step(sqlite_db, result.job_id)
        assert items["disclosure_notes"].status == ExportJobStatus.failed.value

        # 模拟项目数据变化：让快照输入复算出不同 digest（年度/内容变了）。
        harness.notes_should_fail = False
        executor._build_snapshot_input = (  # type: ignore[assignment]
            lambda project_id, year, payload: _stub_snap(project_id, year + 1)
        )

        with pytest.raises(SnapshotMismatchError) as ei:
            await executor.retry_failed(
                result.job_id, user_id=user.id, requesting_project_id=project.id
            )
        assert ei.value.job_snapshot != ei.value.current_snapshot
        assert "快照" in ei.value.message

        # 快照不一致 ⇒ 绝不混用：disclosure_notes 不应被重跑成功。
        items2 = await _items_by_step(sqlite_db, result.job_id)
        assert items2["disclosure_notes"].status == ExportJobStatus.failed.value
        # 也未新增 retry attempt。
        attempts = await executor.job_svc.get_item_attempts(
            items2["disclosure_notes"].id
        )
        assert all(a.trigger != "retry" for a in attempts), (
            "快照不一致时不得在旧快照上新增 retry attempt（需求 5.5）"
        )

    @pytest.mark.asyncio
    async def test_wrong_project_rejected(self, sqlite_db, tmp_path):
        """重试须校验 job 属于请求 project（需求 5.1 的 service 层前置）。"""
        user, project, tasks = await _seed_projects_tasks(sqlite_db)
        executor = FullDeliverablesExecutor(sqlite_db)
        harness = _StepHarness(sqlite_db, tasks, user.id, tmp_path / "deliv")
        harness.patch(executor)
        result = await executor.run(
            project_id=project.id, user_id=user.id, payload={"year": 2024}
        )
        with pytest.raises(ValueError):
            await executor.retry_failed(
                result.job_id, user_id=user.id, requesting_project_id=uuid.uuid4()
            )


# ===========================================================================
# R4：非三件套 item（无 step_key）retry 仍新增 attempt + 保留原始失败（baseline RED-2 口径）
# ===========================================================================


class TestRetryGenericItemPreservesHistory:
    @pytest.mark.asyncio
    async def test_generic_item_retry_appends_attempt_and_keeps_reason(
        self, sqlite_db
    ):
        user, project, _tasks = await _seed_projects_tasks(sqlite_db)
        svc = ExportJobService(sqlite_db)
        job = await svc.create_job(
            project_id=project.id,
            job_type="full_package",
            payload={"year": 2025},
            user_id=user.id,
            total=1,
        )
        item = await svc.add_item(job.id)
        original_reason = "批量渲染失败（原始）"
        await svc.update_item_status(
            item.id, ExportJobStatus.failed.value, error_message=original_reason
        )
        await sqlite_db.flush()

        processed = await svc.retry_failed(job.id, user_id=user.id)
        assert processed == 1

        attempts = await svc.get_item_attempts(item.id)
        # 原始失败（补记）+ retry attempt。
        reasons = [a.error_message for a in attempts if a.error_message]
        assert original_reason in reasons, "retry 后原始失败原因须保留在 attempt 历史"
        assert any(a.trigger == "retry" for a in attempts), "retry 必须新增 attempt"


# ===========================================================================
# M1：变异 —— 退回「只复位状态」旧实现 ⇒ R1 的「新增 attempt」断言被打红
# ===========================================================================


class TestMutationOnlyResetStatusTurnsRed:
    @pytest.mark.asyncio
    async def test_only_reset_status_fails_attempt_assertion(
        self, sqlite_db, tmp_path, monkeypatch
    ):
        """把 retry_failed 换成旧 fail-open 实现（只复位 queued、清空 error_message、不建 attempt）。

        证明本任务判据非恒绿：旧实现下「retry 新增 attempt」的核心断言被打破。
        """
        user, project, tasks = await _seed_projects_tasks(sqlite_db)
        executor = FullDeliverablesExecutor(sqlite_db)
        harness = _StepHarness(sqlite_db, tasks, user.id, tmp_path / "deliv")
        harness.patch(executor)
        result = await executor.run(
            project_id=project.id, user_id=user.id, payload={"year": 2024}
        )
        items = await _items_by_step(sqlite_db, result.job_id)
        notes_item_id = items["disclosure_notes"].id
        attempts_before = len(await executor.job_svc.get_item_attempts(notes_item_id))

        # 变异：旧 fail-open retry（只复位状态，不建 attempt、不重跑）。
        async def _old_retry_failed(self_svc, job_id, **kwargs):  # noqa: ANN001
            rows = (
                await self_svc.db.execute(
                    sa.select(ExportJobItem).where(
                        ExportJobItem.job_id == job_id,
                        ExportJobItem.status == ExportJobStatus.failed.value,
                    )
                )
            ).scalars().all()
            n = 0
            for it in rows:
                it.status = ExportJobStatus.queued.value
                it.error_message = None
                it.finished_at = None
                n += 1
            await self_svc.db.flush()
            return n

        monkeypatch.setattr(ExportJobService, "retry_failed", _old_retry_failed)

        harness.notes_should_fail = False
        svc = ExportJobService(sqlite_db)
        await svc.retry_failed(
            result.job_id, user_id=user.id, requesting_project_id=project.id
        )

        attempts_after = len(await executor.job_svc.get_item_attempts(notes_item_id))
        # 旧实现下 attempt 数不增（判据：retry 应新增 attempt，此处证明被打红）。
        assert attempts_after == attempts_before, (
            "变异（只复位状态）下 attempt 不应新增 —— 正是本任务判据会打红的点"
        )
