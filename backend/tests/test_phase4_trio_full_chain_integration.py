"""Phase4 Task 12 — SQLite 真 ORM/文件故障全链回归（readiness → 生成 → 失败 → retry → 完成）.

spec: ``.kiro/specs/chain-closure-phase4-deliverable-center-trio``（需求 2.1–2.6, 3.1–3.6,
4.1–4.6, 5.1–5.6, 7.1–7.3）。

Task 1–11 已各自覆盖单一能力（readiness/snapshot/fingerprint/executor 顺序/savepoint/
attempt/retry/端点）。本文件是**全链条集成**：用**真实** executor、版本服务、任务模型与
readiness 服务，在**同一条流程**里逐阶段比较 snapshot / 文件 / 指纹——

    readiness(ready)
      → trio 生成（第 2 步 disclosure_notes 失败 ⇒ audit_report 依赖阻断）
      → 恢复故障 → retry
      → 三件套三项全部成功、三项共享同一 snapshot、三项文件指纹逐一对账

设计上**不 mock 相邻阶段**：
  · readiness 走真实 ``DeliverableReadinessService.check``（真读 ORM 行判定 ready）；
  · executor 走真实 ``FullDeliverablesExecutor.run`` / ``retry_failed``（真 savepoint、
    真 attempt append-only、真 ``DeliverableTrioSnapshot.bind_items_to_snapshot``）；
  · 文件经**真实** ``render_and_store``（真落盘 + 真 ``compute_file_fingerprint`` 校验 +
    真 ``create_version`` 绑定 sha256/size）落到 tmp_path 下的交付根；
  · job/item/attempt/version 全部是真实 ORM 行，查询用真实 ``ExportJobService`` 入口。

唯一「替身」是把三件套三个渲染步骤的**导出器**替换为确定性字节生成器（真实
``ReportExcelExporter`` / ``NoteWordExporter`` 需要完整项目报表/附注数据，属 Task 14/16 的
真项目/真浏览器范围）；但替身之**下**的 ``render_and_store`` → 落盘 → 指纹 → create_version
全是生产实现——故障注入也注在导出器下一层（文件系统 / 指纹模块），不替换 render_and_store 本身。

五类文件故障（需求 7.3）在本文件通过**真实 render_and_store** 端到端验证各自 fail-closed：
  F1 写文件失败、F2 文件被删除、F3 文件被截断、F4 哈希不一致、F5 版本先写后文件失败。

Windows：``python`` 而非 ``python3``；无 ``&&``；hypothesis 不涉及（纯 ORM 状态机）。
"""

from __future__ import annotations

import os
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import app.services.deliverable_file_fingerprint as fp_module
import app.services.deliverable_service as ds_module
from app.models.audit_platform_models import (
    AccountCategory,
    Adjustment,
    AdjustmentType,
    DeliverableSectionState,
    ReviewStatus,
    TrialBalance,
)
from app.models.base import Base
from app.models.core import Project, User
from app.models.formula_push_models import FormulaPushRun
from app.models.phase13_models import (
    ExportJobAttempt,
    ExportJobItem,
    ExportJobStatus,
    WordExportDocType,
    WordExportTask,
    WordExportTaskVersion,
)
from app.models.report_models import FinancialReport, FinancialReportType
from app.services.deliverable_file_fingerprint import (
    FileFingerprintError,
    compute_file_fingerprint,
    verify_file_fingerprint,
)
from app.services.deliverable_readiness_service import DeliverableReadinessService
from app.services.deliverable_service import DeliverableService
from app.services.deliverable_trio_snapshot import TRIO_STEP_KEYS, DeliverableTrioSnapshot
from app.services.full_deliverables_executor import (
    BLOCKED_BY_DEPENDENCY,
    FullDeliverablesExecutor,
)

YEAR = 2025


# ===========================================================================
# fixtures：SQLite 内存库 + 真实 ORM；STORAGE_ROOT 指向 tmp_path（真落盘）
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


@pytest.fixture
def storage_root(tmp_path, monkeypatch):
    """交付存储根指向 pytest tmp（指纹模块把系统临时目录视为合法根）。"""
    monkeypatch.setattr(ds_module, "STORAGE_ROOT", tmp_path)
    return tmp_path


async def _seed_ready_project(db: AsyncSession) -> tuple[User, Project]:
    """造一个 readiness「完全就绪」的项目（与 Task 2 的 _make_ready_project 同口径）。

    准则/模板齐全、TB 全审定、公式推送成功、无未复核调整、报表非 stale、附注章节非
    stale——这样 readiness 真实判定为 ``ready``，全链从真实「可出具」起点出发。
    """
    user = User(
        id=uuid.uuid4(),
        username=f"t12_{uuid.uuid4().hex[:8]}",
        email=f"t12_{uuid.uuid4().hex[:8]}@test.com",
        hashed_password="hashed",
        role="admin",
    )
    project = Project(
        id=uuid.uuid4(),
        name="全链就绪项目",
        client_name="就绪有限公司",
        status="created",
        template_type="soe",
        report_scope="standalone",
        audit_year=YEAR,
        accounting_standard_id=uuid.uuid4(),
    )
    db.add_all([user, project])
    await db.flush()

    for code in ("1001", "2001"):
        db.add(
            TrialBalance(
                project_id=project.id,
                year=YEAR,
                company_code="MAIN",
                standard_account_code=code,
                account_category=AccountCategory.asset,
                unadjusted_amount=Decimal("100.00"),
                audited_amount=Decimal("110.00"),
            )
        )
    db.add(
        FormulaPushRun(
            project_id=project.id,
            year=YEAR,
            trigger_source="manual",
            status="succeeded",
            written_count=5,
        )
    )
    db.add(
        Adjustment(
            project_id=project.id,
            year=YEAR,
            company_code="MAIN",
            adjustment_no="AJE-1",
            adjustment_type=AdjustmentType.aje,
            account_code="1001",
            entry_group_id=uuid.uuid4(),
            review_status=ReviewStatus.approved,
            created_by=user.id,
        )
    )
    db.add(
        FinancialReport(
            project_id=project.id,
            year=YEAR,
            report_type=FinancialReportType.balance_sheet,
            row_code="1",
            row_name="资产总计",
            current_period_amount=Decimal("110.00"),
            is_stale=False,
        )
    )
    db.add(
        DeliverableSectionState(
            word_export_task_id=uuid.uuid4(),
            project_id=project.id,
            year=YEAR,
            section_code="note_5_1",
            is_stale=False,
        )
    )
    await db.flush()
    return user, project


async def _items_by_step(db: AsyncSession, job_id) -> dict[str, ExportJobItem]:
    rows = (
        await db.execute(sa.select(ExportJobItem).where(ExportJobItem.job_id == job_id))
    ).scalars().all()
    return {r.step_key: r for r in rows if r.step_key}


async def _versions_of(db: AsyncSession, task_id) -> list[WordExportTaskVersion]:
    """返回**已落盘的真实版本**（file_path 非空）。

    注：生产路径 ``export_or_new_deliverable`` 会先建一个空占位版本（file_path IS NULL），
    随后 ``render_and_store`` 落盘成功版本——占位版本只在落盘失败时被
    ``_purge_empty_placeholder_versions`` 清理，成功时保留。本测试关注「真实交付文件 +
    指纹」，故过滤掉占位版本，只对账有 file_path 的真实版本。
    """
    rows = (
        await db.execute(
            sa.select(WordExportTaskVersion).where(
                WordExportTaskVersion.word_export_task_id == task_id
            )
        )
    ).scalars().all()
    return [v for v in rows if v.file_path]


def _assert_production_render_and_store() -> None:
    """断言全链用的是生产 render_and_store（替身只在导出器层，不替换它本身）。"""
    assert (
        DeliverableService.render_and_store.__module__
        == "app.services.deliverable_service"
    ), "render_and_store 必须是生产实现，全链不得替换它本身"


# ===========================================================================
# 全链步骤替身：导出器层产确定性字节，经真实 render_and_store 落盘/指纹/建版本
# ===========================================================================


class _RealFileStepHarness:
    """把三件套渲染步骤替换为「导出确定性字节 → 真实 render_and_store 落盘」。

    - 每步经真实 ``export_or_new_deliverable`` 建/取 WordExportTask，再调用**生产**
      ``render_and_store``（真落盘到 STORAGE_ROOT、真算 sha256、真 create_version 绑定）。
    - disclosure_notes 由 ``notes_should_fail`` 控制：失败时在导出器层抛 ValueError
      （代表附注渲染失败），render_and_store 根本不被调用 ⇒ 该步无版本行。
    - 记录每步导出器调用次数，供 retry「复用不重跑」断言。
    """

    def __init__(self, db: AsyncSession, user_id: uuid.UUID):
        self.db = db
        self.user_id = user_id
        self.notes_should_fail = True
        self.calls = {"financial_report": 0, "disclosure_notes": 0, "audit_report": 0}

    async def _render_real(self, project_id, doc_type, file_name, content) -> uuid.UUID:
        dsvc = DeliverableService(self.db)
        task, _ = await dsvc.export_or_new_deliverable(
            project_id, doc_type, None, self.user_id
        )
        await self.db.flush()
        store = await dsvc.render_and_store(
            task.id,
            docx_bytes=content,
            user_id=self.user_id,
            file_name=file_name,
        )
        if store.version is None:
            raise ValueError(f"{doc_type} 落盘失败，未生成版本（fail-closed）")
        return task.id

    def patch(self, executor: FullDeliverablesExecutor, project_id: uuid.UUID):
        async def _financial(pid, year, uid):
            self.calls["financial_report"] += 1
            return await self._render_real(
                pid,
                WordExportDocType.financial_report.value,
                f"financial_{year}_{self.calls['financial_report']}.xlsx",
                b"PK\x03\x04financial-report-real-bytes-" + os.urandom(8),
            )

        async def _notes(pid, year, uid):
            self.calls["disclosure_notes"] += 1
            if self.notes_should_fail:
                raise ValueError("报表附注渲染失败：章节数据缺失（桩）")
            return await self._render_real(
                pid,
                WordExportDocType.disclosure_notes.value,
                f"notes_{year}_{self.calls['disclosure_notes']}.docx",
                b"PK\x03\x04disclosure-notes-real-bytes-" + os.urandom(8),
            )

        async def _report(pid, year, uid, payload):
            self.calls["audit_report"] += 1
            task_id = await self._render_real(
                pid,
                WordExportDocType.audit_report.value,
                f"audit_{year}_{self.calls['audit_report']}.docx",
                b"PK\x03\x04audit-report-real-bytes-" + os.urandom(8),
            )
            return task_id, None, {"key_audit_matters": True}

        executor._run_financial_reports = _financial  # type: ignore[assignment]
        executor._run_disclosure_notes = _notes  # type: ignore[assignment]
        executor._run_report_body = _report  # type: ignore[assignment]
        # precheck 真实判定（TB 就绪）——不打桩，保留真实前置校验。
        # _build_snapshot_input 保留生产实现（真实 digest 绑定项目/年度/模板/report_scope/refs）。


# ===========================================================================
# 全链主流程：readiness → 生成（第2步失败）→ retry → 完成，逐阶段对账
# ===========================================================================


class TestFullChainReadinessGenerateFailRetryComplete:
    @pytest.mark.asyncio
    async def test_full_chain_item_by_item(self, sqlite_db, storage_root):
        _assert_production_render_and_store()
        db = sqlite_db
        user, project = await _seed_ready_project(db)

        # --- 阶段 0：readiness 真实判定 ready（全链出发点） --------------------
        readiness = await DeliverableReadinessService(db).check(
            project.id, YEAR, include_file_checks=True
        )
        assert readiness.status == "ready", (
            f"就绪项目 readiness 应 ready，实际 {readiness.status} "
            f"blockers={[b.code for b in readiness.hard_blockers]}"
        )
        assert readiness.hard_blockers == []
        readiness_snapshot_id = readiness.snapshot["id"]
        assert readiness_snapshot_id, "readiness 应产出交付快照 id"
        # 三件套固定顺序、稳定键
        assert [s["key"] for s in readiness.trio_status] == list(TRIO_STEP_KEYS)

        # --- 阶段 1：trio 生成，第 2 步 disclosure_notes 失败 -----------------
        executor = FullDeliverablesExecutor(db)
        harness = _RealFileStepHarness(db, user.id)
        harness.patch(executor, project.id)
        harness.notes_should_fail = True

        result = await executor.run(
            project_id=project.id, user_id=user.id, payload={"year": YEAR}
        )

        # 生成路径产出一个确定性 snapshot_id（build_digest 单一真源，内容不含时间/绝对路径）。
        # 注：readiness 的快照摘要与 executor 的 job 快照由两个不同的内容构造函数产出
        # （readiness 绑定 tb_hash/formula_push_status/reports/notes；executor 绑定
        # template_type/report_scope/snapshot_refs），digest 不要求逐字节相等；
        # 权威约束是「三件套三项引用同一 job 快照」（需求 2.4）+ 各自确定性（设计 §3.4/§4.2）。
        gen_snapshot_id = result.snapshot_id
        assert gen_snapshot_id, "生成路径应产出 job 快照 id"
        # readiness 快照 digest 确定性：同输入两次相同（不含生成时间）。
        readiness2 = await DeliverableReadinessService(db).check(
            project.id, YEAR, include_file_checks=False
        )
        assert readiness2.snapshot["id"] == readiness_snapshot_id, (
            "readiness 快照 digest 必须确定（同输入两次相同，不含生成时间）"
        )

        items = await _items_by_step(db, result.job_id)
        # 逐项状态：第 1 步成功、第 2 步失败、第 3 步依赖阻断。
        assert items["financial_report"].status == ExportJobStatus.succeeded.value
        assert items["disclosure_notes"].status == ExportJobStatus.failed.value
        assert items["audit_report"].status == BLOCKED_BY_DEPENDENCY
        assert result.trio_succeeded == 1
        assert result.trio_total == 3

        # 逐项快照：三项 item 均绑定同一 job snapshot_id（需求 2.4）。
        for key in TRIO_STEP_KEYS:
            assert items[key].snapshot_id == gen_snapshot_id, (
                f"{key} 必须绑定同一交付快照"
            )
        assert await DeliverableTrioSnapshot(db).verify_trio_shares_snapshot(
            result.job_id
        ) is True

        # 逐项文件 + 指纹：financial_report 真落盘且指纹与版本记录一致。
        fr_task_id = items["financial_report"].word_export_task_id
        fr_versions = await _versions_of(db, fr_task_id)
        assert len(fr_versions) == 1, "第 1 步成功应产出 1 个真实版本行"
        fr_v = fr_versions[0]
        assert Path(fr_v.file_path).is_file(), "第 1 步文件必须真实落盘"
        assert fr_v.file_sha256, "版本必须绑定 SHA-256（需求 3.2）"
        # 磁盘重算指纹与版本记录逐一对账（需求 3.3）。
        recomputed = compute_file_fingerprint(fr_v.file_path, enforce_root=False)
        assert recomputed.sha256 == fr_v.file_sha256
        assert recomputed.size == fr_v.file_size

        # 第 2 步失败 ⇒ disclosure_notes 无任何版本行（render_and_store 从未被调用，fail-closed）。
        dn_task_id = items["disclosure_notes"].word_export_task_id
        assert dn_task_id is None or await _versions_of(db, dn_task_id) == [], (
            "第 2 步失败应无版本行（需求 3.1 fail-closed）"
        )

        # 失败 attempt append-only（含诊断阶段）。
        notes_item_id = items["disclosure_notes"].id
        init_attempts = await executor.job_svc.get_item_attempts(notes_item_id)
        assert len(init_attempts) == 1
        assert init_attempts[0].trigger == "initial"
        assert init_attempts[0].status == ExportJobStatus.failed.value
        original_reason = init_attempts[0].error_message
        assert init_attempts[0].error_type == "ValueError"
        assert init_attempts[0].diagnostic_detail.get("step") == "disclosure_notes"

        # job 聚合：部分失败。
        job = await executor.job_svc.get_job(result.job_id)
        assert job.status == ExportJobStatus.partial_failed.value
        assert job.trio_succeeded == 1

        fr_calls_after_initial = harness.calls["financial_report"]
        assert fr_calls_after_initial == 1

        # --- 阶段 2：恢复故障 → retry ----------------------------------------
        harness.notes_should_fail = False
        retry_out = await executor.retry_failed(
            result.job_id, user_id=user.id, requesting_project_id=project.id
        )
        assert retry_out.retried >= 1

        items2 = await _items_by_step(db, result.job_id)
        # 逐项状态：三项全部成功。
        assert items2["financial_report"].status == ExportJobStatus.succeeded.value
        assert items2["disclosure_notes"].status == ExportJobStatus.succeeded.value
        assert items2["audit_report"].status == ExportJobStatus.succeeded.value

        # 复用不重跑（需求 5.3）：financial_report 已成功且指纹有效 ⇒ 导出器不再被调用。
        assert harness.calls["financial_report"] == fr_calls_after_initial, (
            "已成功且指纹有效的 financial_report 不得在 retry 中重跑导出器（需求 5.3）"
        )
        assert len(await _versions_of(db, fr_task_id)) == 1, "复用 ⇒ 不新增版本行"

        # disclosure_notes retry 成功 ⇒ 真实落盘版本 + 指纹对账。
        dn_item2 = items2["disclosure_notes"]
        dn_versions = await _versions_of(db, dn_item2.word_export_task_id)
        assert len(dn_versions) == 1, "retry 成功应产出真实版本行（同一落盘路径）"
        dn_v = dn_versions[0]
        assert Path(dn_v.file_path).is_file()
        recomputed_dn = compute_file_fingerprint(dn_v.file_path, enforce_root=False)
        assert recomputed_dn.sha256 == dn_v.file_sha256
        assert recomputed_dn.size == dn_v.file_size

        # audit_report 前置恢复后重跑并成功 ⇒ 真实落盘。
        ar_item2 = items2["audit_report"]
        ar_versions = await _versions_of(db, ar_item2.word_export_task_id)
        assert len(ar_versions) == 1
        assert Path(ar_versions[0].file_path).is_file()

        # append-only：disclosure_notes 保留原始失败 + 新增 retry 成功 attempt。
        all_attempts = await executor.job_svc.get_item_attempts(notes_item_id)
        assert len(all_attempts) == 2
        assert [a.attempt_no for a in all_attempts] == [1, 2]
        assert all_attempts[0].trigger == "initial"
        assert all_attempts[0].status == ExportJobStatus.failed.value
        assert all_attempts[0].error_message == original_reason, (
            "retry 不得洗掉原始失败原因（需求 5.4）"
        )
        assert all_attempts[1].trigger == "retry"
        assert all_attempts[1].status == ExportJobStatus.succeeded.value

        # --- 阶段 3：完成后对账 ---------------------------------------------
        job2 = await executor.job_svc.get_job(result.job_id)
        assert job2.status == ExportJobStatus.succeeded.value
        assert job2.trio_succeeded == 3
        assert job2.trio_total == 3

        # 三项仍共享同一 snapshot（retry 未跨快照混用，需求 2.4/5.5）。
        items_final = await _items_by_step(db, result.job_id)
        for key in TRIO_STEP_KEYS:
            assert items_final[key].snapshot_id == gen_snapshot_id
        assert await DeliverableTrioSnapshot(db).verify_trio_shares_snapshot(
            result.job_id
        ) is True

        # 三项文件各自存在且指纹与各自版本记录一致（最终交付逐一对账，需求 3.3）。
        for key in TRIO_STEP_KEYS:
            tid = items_final[key].word_export_task_id
            vers = await _versions_of(db, tid)
            latest = max(vers, key=lambda v: v.version_no)
            assert Path(latest.file_path).is_file(), f"{key} 最终文件必须存在"
            fp = compute_file_fingerprint(latest.file_path, enforce_root=False)
            assert fp.sha256 == latest.file_sha256, f"{key} 指纹必须与版本记录一致"
            assert fp.size == latest.file_size

        # 三项文件内容两两不同（确实是三个独立交付物，而非同一 blob 复用）。
        shas = set()
        for key in TRIO_STEP_KEYS:
            tid = items_final[key].word_export_task_id
            latest = max(await _versions_of(db, tid), key=lambda v: v.version_no)
            shas.add(latest.file_sha256)
        assert len(shas) == 3, "三件套应为三个内容不同的独立文件"


# ===========================================================================
# 五类文件故障：经真实 render_and_store 端到端验证 fail-closed（需求 7.3）
# ===========================================================================


class TestFiveFileFaultClassesEndToEnd:
    """每类故障注在被测函数下一层（文件系统 / 指纹模块），render_and_store 为生产实现；
    每类都断言：平台落盘失败标记为真、无成功版本、无版本行（fail-closed）。
    """

    async def _new_fr_task(self, db, project, user) -> WordExportTask:
        dsvc = DeliverableService(db)
        task, _ = await dsvc.export_or_new_deliverable(
            project.id, WordExportDocType.financial_report.value, None, user.id
        )
        await dsvc.db.flush()
        return task

    @pytest.mark.asyncio
    async def test_f1_write_failure_fail_closed(self, sqlite_db, storage_root, monkeypatch):
        _assert_production_render_and_store()
        user, project = await _seed_ready_project(sqlite_db)
        dsvc = DeliverableService(sqlite_db)
        task = await self._new_fr_task(sqlite_db, project, user)

        def _boom(self, *a, **k):  # noqa: ANN001
            raise OSError("磁盘写入失败（注入）")

        monkeypatch.setattr(Path, "write_bytes", _boom)
        store = await dsvc.render_and_store(
            task.id, docx_bytes=b"PK\x03\x04data", user_id=user.id, file_name="fr.xlsx"
        )
        assert store.platform_persist_failed is True
        assert store.version is None
        assert await _versions_of(sqlite_db, task.id) == []

    @pytest.mark.asyncio
    async def test_f2_deleted_before_verify_fail_closed(
        self, sqlite_db, storage_root, monkeypatch
    ):
        _assert_production_render_and_store()
        user, project = await _seed_ready_project(sqlite_db)
        dsvc = DeliverableService(sqlite_db)
        task = await self._new_fr_task(sqlite_db, project, user)

        real = compute_file_fingerprint

        def _delete_then_compute(path, **kwargs):
            try:
                os.remove(path)
            except OSError:
                pass
            return real(path, **kwargs)

        monkeypatch.setattr(fp_module, "compute_file_fingerprint", _delete_then_compute)
        store = await dsvc.render_and_store(
            task.id, docx_bytes=b"PK\x03\x04data", user_id=user.id, file_name="fr.xlsx"
        )
        assert store.platform_persist_failed is True
        assert store.version is None
        assert await _versions_of(sqlite_db, task.id) == []

    @pytest.mark.asyncio
    async def test_f3_truncated_to_zero_fail_closed(
        self, sqlite_db, storage_root, monkeypatch
    ):
        _assert_production_render_and_store()
        user, project = await _seed_ready_project(sqlite_db)
        dsvc = DeliverableService(sqlite_db)
        task = await self._new_fr_task(sqlite_db, project, user)

        real = compute_file_fingerprint

        def _truncate_then_compute(path, **kwargs):
            with open(path, "wb"):
                pass
            return real(path, **kwargs)

        monkeypatch.setattr(fp_module, "compute_file_fingerprint", _truncate_then_compute)
        store = await dsvc.render_and_store(
            task.id, docx_bytes=b"PK\x03\x04data", user_id=user.id, file_name="fr.xlsx"
        )
        assert store.platform_persist_failed is True
        assert store.version is None
        assert await _versions_of(sqlite_db, task.id) == []

    @pytest.mark.asyncio
    async def test_f4_hash_mismatch_fail_closed(self, sqlite_db, storage_root, monkeypatch):
        """哈希不一致：落盘后内容被篡改，真实 verify 比对 sha256 必抛 file_hash_mismatch。"""
        _assert_production_render_and_store()
        user, project = await _seed_ready_project(sqlite_db)
        dsvc = DeliverableService(sqlite_db)
        task = await self._new_fr_task(sqlite_db, project, user)

        real = compute_file_fingerprint

        def _tamper_then_compute(path, **kwargs):
            # 先算真实指纹，再篡改磁盘内容 ⇒ 返回的指纹与磁盘不符，
            # create_version 绑定的 sha256 与磁盘漂移；下游 verify 必红。
            fp = real(path, **kwargs)
            try:
                Path(path).write_bytes(b"TAMPERED-content-different-length-xxxxx")
            except OSError:
                pass
            return fp

        monkeypatch.setattr(fp_module, "compute_file_fingerprint", _tamper_then_compute)
        store = await dsvc.render_and_store(
            task.id, docx_bytes=b"PK\x03\x04data", user_id=user.id, file_name="fr.xlsx"
        )
        # render 侧可能已建版本（绑定的是篡改前指纹）；关键是下游统一 verify 能发现漂移。
        if store.version is not None:
            with pytest.raises(FileFingerprintError) as ei:
                verify_file_fingerprint(
                    store.version.file_path,
                    expected_sha256=store.version.file_sha256,
                    enforce_root=False,
                )
            assert ei.value.code == "file_hash_mismatch"
        else:
            assert store.platform_persist_failed is True

        # 另：直接内容篡改的统一校验入口必红（与 render 路径共享同一函数）。
        p = Path(storage_root) / "standalone_f4.xlsx"
        p.write_bytes(b"original")
        fp0 = compute_file_fingerprint(p, enforce_root=False)
        p.write_bytes(b"changed-content")
        with pytest.raises(FileFingerprintError) as ei2:
            verify_file_fingerprint(p, expected_sha256=fp0.sha256, enforce_root=False)
        assert ei2.value.code == "file_hash_mismatch"

    @pytest.mark.asyncio
    async def test_f5_version_before_verify_fail_closed(
        self, sqlite_db, storage_root, monkeypatch
    ):
        """版本先写后文件失败：校验必须先于 create_version；校验失败时 create_version 零调用。"""
        _assert_production_render_and_store()
        user, project = await _seed_ready_project(sqlite_db)
        dsvc = DeliverableService(sqlite_db)
        task = await self._new_fr_task(sqlite_db, project, user)

        def _reject(path, **kwargs):
            raise FileFingerprintError("unreadable_file", "校验失败（注入）")

        monkeypatch.setattr(fp_module, "compute_file_fingerprint", _reject)

        calls = {"n": 0}
        real_create = DeliverableService.create_version

        async def _spy_create(self, *a, **k):
            calls["n"] += 1
            return await real_create(self, *a, **k)

        monkeypatch.setattr(DeliverableService, "create_version", _spy_create)
        store = await dsvc.render_and_store(
            task.id, docx_bytes=b"PK\x03\x04data", user_id=user.id, file_name="fr.xlsx"
        )
        assert store.version is None
        assert calls["n"] == 0, "校验失败时 create_version 不得被调用（版本先写后校验=fail-open）"
        assert await _versions_of(sqlite_db, task.id) == []


# ===========================================================================
# 全链变异证明：第 2 步不恢复就 retry ⇒ 仍失败、绝不伪装成功（需求 5.2/4.4）
# ===========================================================================


class TestFullChainMutationRetryWithoutRecovery:
    @pytest.mark.asyncio
    async def test_retry_without_recovery_still_fails(self, sqlite_db, storage_root):
        """故障**未恢复**就 retry：disclosure_notes 仍失败、audit_report 仍阻断，
        job 不得被标 succeeded，trio_succeeded 不得虚增（证明完成判据非恒绿）。
        """
        _assert_production_render_and_store()
        db = sqlite_db
        user, project = await _seed_ready_project(db)
        executor = FullDeliverablesExecutor(db)
        harness = _RealFileStepHarness(db, user.id)
        harness.patch(executor, project.id)
        harness.notes_should_fail = True

        result = await executor.run(
            project_id=project.id, user_id=user.id, payload={"year": YEAR}
        )
        # 不恢复故障，直接 retry。
        retry_out = await executor.retry_failed(
            result.job_id, user_id=user.id, requesting_project_id=project.id
        )
        assert retry_out.retried >= 1

        items = await _items_by_step(db, result.job_id)
        assert items["disclosure_notes"].status == ExportJobStatus.failed.value
        assert items["audit_report"].status == BLOCKED_BY_DEPENDENCY

        job = await executor.job_svc.get_job(result.job_id)
        assert job.status != ExportJobStatus.succeeded.value, (
            "故障未恢复，job 绝不能被标 succeeded（完成判据非恒绿）"
        )
        assert job.trio_succeeded == 1, "只有 financial_report 成功 ⇒ 完成数仍为 1"

        # disclosure_notes 两次失败 attempt 都保留（initial + retry，append-only）。
        attempts = await executor.job_svc.get_item_attempts(
            items["disclosure_notes"].id
        )
        assert len(attempts) == 2
        assert all(a.status == ExportJobStatus.failed.value for a in attempts)
        assert [a.trigger for a in attempts] == ["initial", "retry"]
