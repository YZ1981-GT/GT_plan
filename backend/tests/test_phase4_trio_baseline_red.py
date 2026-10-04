"""Phase4 交付中心三件套 — 基线「修复前红」证据（spec chain-closure-phase4-deliverable-center-trio Task 1）.

本文件是 **red-before 基线**：对当前 HEAD 的实现断言 phase4 需求所要求的
目标行为，当前实现尚未满足，因此这些用例**现在应当失败**，且失败断言指向
**实际错误形态**（而非"函数没被调用"的弱证据）。后续任务修复后，同一命令转绿。

覆盖 Task 1 要求的三个最小 red 用例：

1. 文件落盘失败后仍有成功版本（需求 3.1）
   —— ``DeliverableService.render_and_store`` 当前 fail-open：写盘失败时把
   ``file_path`` 置 None 后**仍调用 ``create_version``**，于是数据库里留下一个
   ``file_path IS NULL`` 的"成功"版本行。目标：写盘失败不得创建版本。

2. retry 只复位状态（需求 5.2）
   —— ``ExportJobService.retry_failed`` 当前只把 item 状态改回 ``queued`` 并
   清空 ``error_message``，**不重新渲染/落盘/建版本/建 attempt**。目标：retry
   必须真正重跑失败步骤并新增 attempt。

3. unadjusted 计入三件套 / 顺序与稳定键（需求 2.1, 2.5）
   —— 当前只有 ``FULL_DELIVERABLES_STEPS = [financial_reports, disclosure_notes,
   report_body]``，用的是非权威键（``financial_reports`` / ``report_body``），
   且没有正式 ``TRIO_STEPS`` 常量把 ``financial_report → disclosure_notes →
   audit_report`` 固定为稳定键，``financial_report_unadjusted`` 也没有被显式排除
   在正式三件套之外。目标：存在权威 ``TRIO_STEPS``，顺序固定、键稳定、unadjusted
   不计入正式三件套。

注意：``tests/test_full_deliverables_executor.py`` 另有 5 个**预存红**（断言旧的
4 步契约），那是 HEAD 既存失败，与本阶段引入无关；本文件只断言 phase4 目标行为。
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
    ExportJobStatus,
    WordExportDocType,
    WordExportTaskVersion,
)
import sqlalchemy as sa


# ===================================================================
# fixtures（SQLite 内存库 + 真实 ORM，与现有 executor 测试同款）
# ===================================================================


@pytest_asyncio.fixture
async def test_db():
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
        username="phase4_red",
        email="phase4red@test.com",
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
        name="phase4三件套项目",
        client_name="测试有限公司",
        status="created",
    )
    test_db.add(project)
    await test_db.flush()
    return project


# ===================================================================
# RED 1：文件落盘失败后仍有成功版本（需求 3.1）
# ===================================================================


class TestRenderAndStoreFailClosed:
    """写盘失败时不得创建版本（fail-closed）。"""

    @pytest.mark.asyncio
    async def test_write_failure_must_not_create_version(
        self, test_db, test_project, test_user, monkeypatch
    ):
        """注入写盘失败后，当前实现仍会 create_version（file_path IS NULL 的"成功"行）。

        red-before：断言写盘失败后 **没有任何版本行**。
        当前 HEAD fail-open ⇒ 实际会有 1 行 file_path 为 None 的版本 ⇒ 本断言失败。
        """
        from app.services.deliverable_service import DeliverableService

        dsvc = DeliverableService(test_db)
        task, _ = await dsvc.export_or_new_deliverable(
            test_project.id,
            WordExportDocType.financial_report.value,
            None,
            test_user.id,
        )
        await test_db.flush()

        # 注入落盘失败：让 Path.write_bytes 抛 OSError（磁盘满/权限等真实形态）
        def _boom(self, *args, **kwargs):  # noqa: ANN001
            raise OSError("磁盘写入失败（注入）")

        monkeypatch.setattr(Path, "write_bytes", _boom)

        store = await dsvc.render_and_store(
            task.id,
            docx_bytes=b"PK\x03\x04fake-xlsx-bytes",
            user_id=test_user.id,
            source_snapshot_refs={"tb_hash": "deadbeef"},
            file_name="financial_reports_2025.xlsx",
        )

        # 当前实现：platform_persist_failed=True 但仍建了版本 ⇒ 下面两条都会红
        versions = (
            await test_db.execute(
                sa.select(WordExportTaskVersion).where(
                    WordExportTaskVersion.word_export_task_id == task.id
                )
            )
        ).scalars().all()

        assert store.platform_persist_failed is True, (
            "前置：注入写盘失败应被识别为 platform_persist_failed"
        )
        # 目标行为（需求 3.1）：落盘失败不得创建"成功"版本。
        assert len(versions) == 0, (
            f"写盘失败后不应创建版本，但发现 {len(versions)} 个版本行："
            f"{[(v.version_no, v.file_path) for v in versions]}"
        )


# ===================================================================
# RED 2：retry 只复位状态，不重跑步骤（需求 5.2）
# ===================================================================


class TestRetryActuallyReExecutes:
    """retry 必须真正重跑失败步骤并新增 attempt，而非仅改状态。"""

    @pytest.mark.asyncio
    async def test_retry_must_create_attempt_and_regenerate(
        self, test_db, test_project, test_user
    ):
        """当前 retry_failed 只把 item 状态改回 queued，不建 attempt、不重渲染。

        red-before：断言 retry 后产生了"真实重执行"的可观测痕迹——这里以
        ``export_job_attempts`` 表存在且新增一条 attempt 作为稳定判据。
        当前 HEAD 没有 attempt 机制 ⇒ 本断言失败（找不到模型/表或计数为 0）。
        """
        from app.services.export_job_service import ExportJobService

        svc = ExportJobService(test_db)
        job = await svc.create_job(
            project_id=test_project.id,
            job_type="full_deliverables",
            payload={"year": 2025},
            user_id=test_user.id,
            total=3,
        )
        item = await svc.add_item(job.id)
        await svc.update_item_status(
            item.id,
            ExportJobStatus.failed.value,
            error_message="附注生成失败（桩）",
        )
        await test_db.flush()

        retried = await svc.retry_failed(job.id)
        assert retried == 1, "前置：应识别出 1 个失败项"

        # 目标行为（需求 5.2/5.4）：retry 必须新增 attempt 记录（append-only 历史）。
        # 当前 HEAD 无 ExportJobAttempt 模型 ⇒ import 失败即为 red-before 证据。
        from app.models.phase13_models import ExportJobAttempt  # type: ignore

        attempts = (
            await test_db.execute(
                sa.select(ExportJobAttempt).where(
                    ExportJobAttempt.item_id == item.id
                )
            )
        ).scalars().all()
        assert len(attempts) >= 1, (
            "retry 应为失败项新增 attempt，但 attempt 表为空 ⇒ retry 只复位了状态"
        )

    @pytest.mark.asyncio
    async def test_retry_preserves_original_failure_reason(
        self, test_db, test_project, test_user
    ):
        """retry 不得清空历史失败原因（需求 5.4：保留原始失败 attempt）。

        当前 HEAD：retry_failed 直接 ``item.error_message = None`` ⇒ 原因被洗掉。
        red-before：断言仍能查到原始失败原因文本。
        """
        from app.services.export_job_service import ExportJobService

        svc = ExportJobService(test_db)
        job = await svc.create_job(
            project_id=test_project.id,
            job_type="full_deliverables",
            payload={"year": 2025},
            user_id=test_user.id,
            total=3,
        )
        item = await svc.add_item(job.id)
        original_reason = "附注章节未交接（原始失败）"
        await svc.update_item_status(
            item.id, ExportJobStatus.failed.value, error_message=original_reason
        )
        await test_db.flush()

        await svc.retry_failed(job.id)

        from app.models.phase13_models import ExportJobAttempt  # type: ignore

        rows = (
            await test_db.execute(
                sa.select(ExportJobAttempt.error_message).where(
                    ExportJobAttempt.item_id == item.id
                )
            )
        ).scalars().all()
        assert original_reason in [r for r in rows if r], (
            "retry 后原始失败原因应保留在 attempt 历史中，但未找到"
        )


# ===================================================================
# RED 3：TRIO_STEPS 稳定键与顺序，unadjusted 不计入正式三件套（需求 2.1/2.5）
# ===================================================================


class TestTrioStepsAuthoritativeContract:
    """正式三件套必须由权威 TRIO_STEPS 固定顺序与稳定键。"""

    def test_trio_steps_canonical_keys_and_order(self):
        """red-before：当前无 TRIO_STEPS 常量，只有非权威的 FULL_DELIVERABLES_STEPS。

        目标：存在 ``TRIO_STEPS``，顺序固定为
        ``financial_report → disclosure_notes → audit_report``，键为稳定英文键。
        """
        import app.services.full_deliverables_executor as mod

        assert hasattr(mod, "TRIO_STEPS"), (
            "应存在权威常量 TRIO_STEPS（当前只有 FULL_DELIVERABLES_STEPS）"
        )
        step_keys = [
            s if isinstance(s, str) else getattr(s, "key", s)
            for s in mod.TRIO_STEPS  # type: ignore[attr-defined]
        ]
        assert step_keys == [
            "financial_report",
            "disclosure_notes",
            "audit_report",
        ], f"TRIO_STEPS 顺序/键不符合权威契约：{step_keys}"

    def test_unadjusted_not_in_trio(self):
        """red-before：unadjusted 不得出现在正式三件套中。

        目标：``financial_report_unadjusted`` 不在 TRIO_STEPS，且正式完成数固定为 3。
        """
        import app.services.full_deliverables_executor as mod

        assert hasattr(mod, "TRIO_STEPS"), "缺权威 TRIO_STEPS 常量"
        step_keys = [
            s if isinstance(s, str) else getattr(s, "key", s)
            for s in mod.TRIO_STEPS  # type: ignore[attr-defined]
        ]
        assert "financial_report_unadjusted" not in step_keys, (
            "财务报表（未审）是辅助项，不得计入正式三件套"
        )
        assert len(step_keys) == 3, f"正式三件套固定为 3 项，实际 {len(step_keys)}"
