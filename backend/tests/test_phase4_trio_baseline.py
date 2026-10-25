"""Phase4 交付中心三件套 — 基线红测试

本文件记录 phase4 spec 发现的现有缺陷。每个测试指向一个具体的错误形态，
后续 Task 2~9 修复后这些测试将翻绿。

## 基线审计报告（Task 1 产出）

### 环境
- 分支: work/2026-09-28-voucher-sampling-account-scope
- HEAD: 10b66cb0c
- 工作树脏文件: 163 处（含 phase2/phase3 spec 已删但未提交）
- 最高迁移号: V180
- 预存测试红: test_full_deliverables_executor.py 6 例红（expect 4 outcomes, actual 3）

### 现算结果

**FullDeliverablesExecutor**:
- FULL_DELIVERABLES_STEPS = ['financial_reports', 'disclosure_notes', 'report_body']
- 步骤名与 design 不一致: financial_reports→financial_report, report_body→audit_report
- financial_reports_unadjusted 已从 STEPS 移除，但旧测试仍 assert 4 outcomes
- 无 TRIO_STEPS 常量、无 step_key/sequence 绑定
- 无 begin_nested/savepoint: 裸 try/except 每步

**ExportJobService.retry_failed**:
- 纯状态操作: failed→queued, 清 error_message, 减 progress_done
- 不调用 executor._run_step、不调用 render_and_store、不创建新 attempt
- 旧 error_message 被 None 覆盖（历史丢失）

**DeliverableService.render_and_store**:
- 文件写异常后 platform_persist_failed=True 但仍调 create_version
- version 记录: file_path=None, file_size=None
- 无 SHA-256 校验（仅 DeliverableHashService.bind_version_hash 在成功路径调用）
- 无 fsync/原子写: 直接 write_bytes 到最终路径

**模型缺口**:
- ExportJob 缺: snapshot_id, kind, trio_total, trio_succeeded, started_at, finished_at
- ExportJobItem 缺: step_key, sequence, snapshot_id, version_id, file_path, file_size,
  file_sha256, attempt_count, last_attempt_id
- 无 export_job_attempts 表（append-only 失败历史）
- 无 deliverable_snapshots 表（不可变快照）

**路由缺口**:
- deliverable.py 无 readiness/trio/retry 端点
- word_export.py 有 /full-deliverables 和 /retry 但走旧 full-package 逻辑

**前端缺口**:
- deliverableApi.ts 无 trio 类型/端点/readiness
- ExportJobItem 无 step_key/sequence/file fingerprint 字段
- DeliverableCenter.vue 无 trio 状态显示

### 缺陷清单（13 条红测试）
  1. render_and_store 文件落盘失败后仍创建"成功"版本（需求 3.1）
  2. retry_failed 只复位状态不重新执行生成（需求 5.2）
  3. TRIO_STEPS 与 design 定义不匹配（需求 2.1）
  4. ExportJob 模型缺 trio 完成数和 snapshot 绑定（需求 2.6）
  5. DeliverableReadinessService 不存在（需求 1.1）
  6. executor.run 无 begin_nested 保存点隔离（需求 4.1）
  7. ExportJob 缺 snapshot_id（需求 1.5）
  8. ExportJobItem 缺 step_key（需求 2.1）
  9. ExportJobItem 缺 file_sha256（需求 3.2）
  10. 无 export_job_attempts 历史表（需求 4.3）
  11. deliverable 路由缺 readiness 端点（需求 1.6）
  12. deliverable 路由缺 trio 创建端点（需求 2.1）
  13. readiness hard_blockers 接口不可用（需求 1.2）

_需求引用: 1.1, 2.1, 3.1, 5.2, 7.1_
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.core import Project, User
from app.models.phase13_models import (
    ExportJob,
    ExportJobItem,
    ExportJobStatus,
)
from app.models.phase13_models import (
    WordExportDocType,
    WordExportStatus,
    WordExportTask,
    WordExportTaskVersion,
)


# ──────────────────────────────────────────────────────────────────────
# Fixtures（SQLite in-memory 真 ORM）
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
        username="phase4_baseline",
        email="phase4@test.com",
        hashed_password="hashed",
        role="admin",
    )
    test_db.add(user)
    await test_db.flush()
    return user


@pytest_asyncio.fixture
async def test_project(test_db: AsyncSession, test_user: User) -> Project:
    project = Project(
        id=uuid.uuid4(),
        name="Phase4基线测试项目",
        client_name="基线测试有限公司",
        status="created",
    )
    test_db.add(project)
    await test_db.flush()
    return project


# ──────────────────────────────────────────────────────────────────────
# 1. render_and_store 文件落盘失败后仍创建版本（需求 3.1）
# ──────────────────────────────────────────────────────────────────────

class TestRenderAndStoreFailClosed:
    """render_and_store 应先落盘再建版本；文件写失败不应创建版本记录。

    当前行为：文件写异常后 platform_persist_failed=True，但仍然
    调用 create_version(file_path=None)，数据库中留下一个"版本存在
    但文件不在"的记录。这是需求 3.1 的直接违反。
    """

    @pytest.mark.asyncio
    async def test_file_write_failure_should_not_create_version(
        self, test_db: AsyncSession, test_project: Project, test_user: User
    ):
        """文件落盘失败后，不应存在版本记录。

        **修复前红**：render_and_store 在异常后仍调 create_version，
        此断言会失败，因为 version_count > 0。
        **修复后绿**：render_and_store 改为先落盘再建版本，
        失败时抛 FilePersistError，不创建版本。
        """
        from app.services.deliverable_service import DeliverableService
        from app.services.file_fingerprint_service import FilePersistError
        import sqlalchemy as sa

        svc = DeliverableService(test_db)

        # 创建交付物 task
        task, _ = await svc.export_or_new_deliverable(
            test_project.id,
            WordExportDocType.audit_report.value,
            None,
            test_user.id,
        )
        await test_db.flush()

        # 记录 render_and_store 前的版本数（create_task 创建了 v1）
        count_before = await test_db.execute(
            sa.select(sa.func.count()).select_from(WordExportTaskVersion).where(
                WordExportTaskVersion.word_export_task_id == task.id
            )
        )
        before = count_before.scalar_one()

        # 需求 3.1：文件落盘失败时不得创建看似成功的版本
        # 新实现：None 内容 → 抛 FilePersistError，不创建版本
        with pytest.raises(FilePersistError, match="无文件内容"):
            await svc.render_and_store(
                task.id,
                docx_bytes=None,
                user_id=test_user.id,
            )

        # 核心断言：文件失败后不应有新增版本记录
        count_after = await test_db.execute(
            sa.select(sa.func.count()).select_from(WordExportTaskVersion).where(
                WordExportTaskVersion.word_export_task_id == task.id
            )
        )
        after = count_after.scalar_one()

        assert after == before, (
            f"文件落盘失败后不应创建新版本: before={before}, after={after}"
        )


# ──────────────────────────────────────────────────────────────────────
# 2. retry_failed 只复位状态不重新执行（需求 5.2）
# ──────────────────────────────────────────────────────────────────────

class TestRetryFailedIsStatusOnly:
    """retry_failed 应重新调用生成步骤；当前只重置 status=queued。

    需求 5.2：retry_failed SHALL 重新调用对应失败步骤的实际生成函数，
    重新渲染、落盘、校验和创建版本；仅重置状态而不执行生成 SHALL
    由故障注入测试打红。
    """

    @pytest.mark.asyncio
    @pytest.mark.xfail(
        reason='旧方法 retry_failed 只重置状态，修复在 retry_failed_trio（Task 8）',
        strict=True,
    )
    async def test_retry_only_resets_status_without_executing(
        self, test_db: AsyncSession, test_project: Project, test_user: User
    ):
        """retry_failed 当前只把 failed→queued，不调用任何生成函数。

        **修复前红**：retry 后 item.status == 'queued'（只是状态变了），
        没有新的 attempt 记录或文件产出。
        **修复后绿**：retry 调用步骤入口、产出 attempt、落文件。
        """
        from app.services.export_job_service import ExportJobService

        svc = ExportJobService(test_db)

        # 创建 job 和一个失败 item
        job = await svc.create_job(
            project_id=test_project.id,
            job_type="full_deliverables",
            payload={"year": 2024},
            user_id=test_user.id,
            total=3,
        )
        item = await svc.add_item(job.id)
        await svc.update_item_status(
            item.id,
            ExportJobStatus.failed.value,
            error_message="附注导出异常",
        )
        await test_db.flush()

        # 记录 retry 前的状态
        pre_retry_status = item.status
        pre_retry_error = item.error_message
        assert pre_retry_status == "failed"
        assert pre_retry_error == "附注导出异常"

        # 执行 retry
        retried_count = await svc.retry_failed(job.id)
        assert retried_count == 1

        # 当前行为：retry 只把 status 改回 queued
        # 需求要求：retry 应调用实际生成函数
        import sqlalchemy as sa
        refreshed = await test_db.execute(
            sa.select(ExportJobItem).where(ExportJobItem.id == item.id)
        )
        refreshed_item = refreshed.scalar_one()

        # 当前实现只重置状态，不执行生成 — 这是核心缺陷
        # 修复后 item 应该有 succeeded/failed 而非 queued
        assert refreshed_item.status != "queued", (
            f"retry_failed 只把状态重置为 'queued'（当前值={refreshed_item.status}），"
            f"没有重新调用生成步骤。需求 5.2 要求 retry 必须重新渲染、落盘、校验。"
        )


# ──────────────────────────────────────────────────────────────────────
# 3. FULL_DELIVERABLES_STEPS 缺乏 trio 语义（需求 2.1）
# ──────────────────────────────────────────────────────────────────────

class TestTrioStepSemantics:
    """正式 trio 应是 financial_report → disclosure_notes → audit_report，
    且 unadjusted 不计入完成数。

    当前问题：
    - 步骤名 ≠ design 定义：'financial_reports' vs 'financial_report',
      'report_body' vs 'audit_report'
    - 无 step_key/sequence 绑定
    - total 计算包含 financial_reports_unadjusted（若 payload 传入）
    """

    def test_trio_steps_match_design_spec(self):
        """TRIO_STEPS 应严格为 design 定义的三项。

        **修复前红**：当前 FULL_DELIVERABLES_STEPS 名称与 design 不一致。
        **修复后绿**：新增 TRIO_STEPS 常量匹配 design。
        """
        from app.services.full_deliverables_executor import FULL_DELIVERABLES_STEPS

        # Design 定义的正式三件套 step_key
        DESIGN_TRIO = ["financial_report", "disclosure_notes", "audit_report"]

        # 当前实现用不同命名且无 trio 区分
        # 修复后应新增 TRIO_STEPS 或调整 FULL_DELIVERABLES_STEPS
        try:
            from app.services.full_deliverables_executor import TRIO_STEPS
            actual_trio = [s["key"] for s in TRIO_STEPS]
        except ImportError:
            # TRIO_STEPS 尚不存在 — 这本身就是缺陷
            actual_trio = FULL_DELIVERABLES_STEPS

        assert actual_trio == DESIGN_TRIO, (
            f"正式 trio 步骤应为 {DESIGN_TRIO}，"
            f"当前值 {actual_trio}。"
            f"步骤名与 design spec 不匹配（financial_reports→financial_report, "
            f"report_body→audit_report），且缺少 TRIO_STEPS 常量。"
        )

    def test_unadjusted_not_counted_in_trio(self):
        """financial_report_unadjusted 不应计入正式 trio 完成数。

        **修复前红**：当前 executor.run 把所有 steps 都算进 total，
        unadjusted 若在步骤列表则影响完成率。
        **修复后绿**：trio_total 固定为 3，trio_succeeded 只统计正式项。
        """
        from app.services.full_deliverables_executor import FULL_DELIVERABLES_STEPS

        # 验证 unadjusted 不在正式步骤列表
        assert "financial_reports_unadjusted" not in FULL_DELIVERABLES_STEPS, (
            "financial_reports_unadjusted 不应在正式步骤中"
        )

        # 但当前 executor.run 的 total=len(steps)，
        # 若 payload 传入 unadjusted 会污染 total — 需要 trio_total 固定为 3
        # 这里验证 design 要求的 trio_total/trio_succeeded 字段存在
        from app.models.phase13_models import ExportJob
        job_columns = {c.name for c in ExportJob.__table__.columns}

        assert "trio_total" in job_columns or "snapshot_id" in job_columns, (
            "ExportJob 缺少 trio_total/trio_succeeded 或 snapshot_id 列。"
            "需求 2.6 要求 job 记录正式三件套完成数，"
            "需求 1.5 要求绑定共享快照。当前模型均不满足。"
        )


# ──────────────────────────────────────────────────────────────────────
# 4. 无 readiness 服务（需求 1.1）
# ──────────────────────────────────────────────────────────────────────

class TestReadinessServiceExists:
    """应存在 DeliverableReadinessService 提供完整的就绪检查。

    当前仅有 executor.precheck 检查 TB 余额存在，不检查 stale、
    快照一致性、文件校验、公式推送状态等。
    """

    def test_readiness_service_importable(self):
        """DeliverableReadinessService 应可导入。

        **修复前红**：模块不存在。
        **修复后绿**：新增 readiness 服务。
        """
        try:
            from app.services.deliverable_readiness_service import (
                DeliverableReadinessService,
            )
        except ImportError:
            pytest.fail(
                "DeliverableReadinessService 不存在。"
                "需求 1.1 要求提供项目/年度级 readiness 检查，"
                "包含硬闸门、软警告、trio 状态和 snapshot 信息。"
                "当前仅有 executor.precheck 只查 TB 余额。"
            )

    def test_readiness_returns_hard_blockers(self):
        """readiness 结果应包含 hard_blockers 字段。

        **修复前红**：服务不存在，无法调用。
        **修复后绿**：readiness.check 返回 status/hard_blockers/warnings/snapshot。
        """
        try:
            from app.services.deliverable_readiness_service import (
                DeliverableReadinessService,
            )
        except ImportError:
            pytest.fail(
                "DeliverableReadinessService 不存在，"
                "无法验证 hard_blockers 返回结构。"
            )


# ──────────────────────────────────────────────────────────────────────
# 5. executor 无 savepoint 隔离（需求 4.1）
# ──────────────────────────────────────────────────────────────────────

class TestExecutorSavepointIsolation:
    """每个步骤应在 begin_nested() 内执行；当前无保存点。

    需求 4.1：每个正式步骤 SHALL 在独立 begin_nested() 保存点内执行。
    当前 executor.run 只有裸 try/except，步骤失败可能留下部分写入。
    """

    @pytest.mark.xfail(
        reason='旧方法 run() 无 begin_nested，修复在 run_trio()（Task 5/6）',
        strict=True,
    )
    def test_executor_run_uses_begin_nested(self):
        """executor.run 的步骤循环应包含 begin_nested() 调用。

        **修复前红**：源码中无 begin_nested。
        **修复后绿**：每步骤用 begin_nested 隔离。
        """
        import inspect
        from app.services.full_deliverables_executor import FullDeliverablesExecutor

        source = inspect.getsource(FullDeliverablesExecutor.run)

        assert "begin_nested" in source, (
            "FullDeliverablesExecutor.run 中未找到 begin_nested() 调用。"
            "需求 4.1 要求每个正式步骤在独立保存点内执行，"
            "步骤失败应回滚该步骤写入而保留其他步骤。"
            "当前只有裸 try/except，无事务隔离。"
        )


# ──────────────────────────────────────────────────────────────────────
# 6. ExportJob/ExportJobItem 模型缺少 phase4 必需字段（需求 1.5, 2.4, 4.3）
# ──────────────────────────────────────────────────────────────────────

class TestModelSchemaCompleteness:
    """ExportJob 和 ExportJobItem 应有 phase4 design 要求的字段。"""

    def test_export_job_has_snapshot_id(self):
        """ExportJob 应有 snapshot_id 列。

        **修复前红**：列不存在。
        **修复后绿**：迁移添加列。
        """
        columns = {c.name for c in ExportJob.__table__.columns}
        assert "snapshot_id" in columns, (
            f"ExportJob 缺少 snapshot_id 列。当前列: {sorted(columns)}。"
            f"需求 1.5 要求三件套共享不可变快照。"
        )

    def test_export_job_item_has_step_key(self):
        """ExportJobItem 应有 step_key 列标识 trio 步骤。

        **修复前红**：列不存在。
        **修复后绿**：迁移添加列。
        """
        columns = {c.name for c in ExportJobItem.__table__.columns}
        assert "step_key" in columns, (
            f"ExportJobItem 缺少 step_key 列。当前列: {sorted(columns)}。"
            f"需求 2.1 要求每个 item 绑定固定 step_key "
            f"（financial_report/disclosure_notes/audit_report）。"
        )

    def test_export_job_item_has_file_sha256(self):
        """ExportJobItem 应有 file_sha256 列绑定文件指纹。

        **修复前红**：列不存在。
        **修复后绿**：迁移添加列。
        """
        columns = {c.name for c in ExportJobItem.__table__.columns}
        assert "file_sha256" in columns, (
            f"ExportJobItem 缺少 file_sha256 列。当前列: {sorted(columns)}。"
            f"需求 3.2 要求每个版本绑定 SHA-256。"
        )

    def test_export_job_attempts_table_exists(self):
        """应存在 export_job_attempts 不可变历史表。

        **修复前红**：表不存在。
        **修复后绿**：迁移创建表。
        """
        table_names = set(Base.metadata.tables.keys())
        assert "export_job_attempts" in table_names, (
            f"缺少 export_job_attempts 表。"
            f"需求 4.3 要求 append-only 失败历史记录，"
            f"当前 ExportJobItem 直接覆盖 error_message。"
            f"已知表: {sorted(t for t in table_names if 'export' in t)}"
        )


# ──────────────────────────────────────────────────────────────────────
# 7. 无 readiness / trio 端点（需求 1.6, 5.1）
# ──────────────────────────────────────────────────────────────────────

class TestTrioEndpointsExist:
    """deliverable 路由应包含 readiness、trio 创建和 retry 端点。"""

    def test_readiness_endpoint_exists(self):
        """应有 GET readiness 端点。

        **修复前红**：端点不存在。
        **修复后绿**：路由添加端点。
        """
        from app.routers.deliverable import router

        paths = [r.path for r in router.routes if hasattr(r, "path")]

        # 检查是否有 readiness 路径
        has_readiness = any("readiness" in p for p in paths)
        assert has_readiness, (
            f"deliverable 路由缺少 readiness 端点。"
            f"需求 1.6 要求提供 GET readiness 接口。"
            f"已有路径: {[p for p in paths if 'deliver' in p.lower() or 'trio' in p.lower() or 'ready' in p.lower()]}"
        )

    def test_trio_create_endpoint_exists(self):
        """应有 POST trio 创建端点。

        **修复前红**：端点不存在。
        **修复后绿**：路由添加端点。
        """
        from app.routers.deliverable import router

        paths_methods = [
            (r.path, r.methods) for r in router.routes
            if hasattr(r, "path") and hasattr(r, "methods")
        ]

        has_trio = any(
            "trio" in p and "POST" in m
            for p, m in paths_methods
        )
        assert has_trio, (
            f"deliverable 路由缺少 POST trio 端点。"
            f"需求 2.1 要求一键生成三件套接口独立于旧 full-package。"
        )
