"""Phase4 交付中心 — readiness 硬/软闸门（spec chain-closure-phase4-deliverable-center-trio Task 2）.

覆盖 design §4 / 需求 1.1~1.6：

- ``DeliverableReadinessService.check`` 真读取 TB / 公式推送 / 调整确认 / 报表 / 附注
  的项目年度状态，产出稳定 code + 中文原因 + 证据；
- warning 与 blocker 分离：软 warning 不改变可出具（``ready_with_warnings`` 仍非 blocked）；
- phase3 未在 HEAD 的能力 fail-closed（探测模块缺失即 ``upstream_not_ready``）；
- **变异证明**：删掉任一硬闸门的触发条件 ⇒ 对应 blocker 消失（即该闸门确实在起作用，
  不是恒绿）；软 warning 的反向样本（只有 warning）必须保持非 blocked。

全部用 SQLite 内存库 + 真实 ORM 行（不 mock service 内部查询）。
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

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
from app.models.report_models import FinancialReport, FinancialReportType
from app.services.deliverable_readiness_service import DeliverableReadinessService


# ===================================================================
# fixtures
# ===================================================================

YEAR = 2025


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
async def user(test_db: AsyncSession) -> User:
    u = User(
        id=uuid.uuid4(),
        username="phase4_readiness",
        email="phase4ready@test.com",
        hashed_password="hashed",
        role="admin",
    )
    test_db.add(u)
    await test_db.flush()
    return u


async def _make_ready_project(db: AsyncSession, user: User) -> Project:
    """造一个「完全就绪」的项目：准则/模板齐全、TB 全审定、公式推送成功、
    无未复核调整、报表非 stale、附注章节已交接非 stale、无既有坏文件版本。
    """
    project = Project(
        id=uuid.uuid4(),
        name="就绪项目",
        client_name="就绪有限公司",
        status="created",
        template_type="soe",
        report_scope="standalone",
        audit_year=YEAR,
        accounting_standard_id=uuid.uuid4(),
    )
    db.add(project)
    await db.flush()

    # TB：两行，均有 audited_amount（审定数已发布）
    for i, code in enumerate(("1001", "2001")):
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

    # 公式推送：成功
    db.add(
        FormulaPushRun(
            project_id=project.id,
            year=YEAR,
            trigger_source="manual",
            status="succeeded",
            written_count=5,
        )
    )

    # 调整：均 approved（无未复核）
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

    # 报表：非 stale
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

    # 附注章节：已交接、非 stale
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
    return project


# ===================================================================
# 1. 完全就绪 → ready（基准绿）
# ===================================================================


class TestReadyBaseline:
    @pytest.mark.asyncio
    async def test_fully_ready_project_is_ready(self, test_db, user):
        project = await _make_ready_project(test_db, user)
        svc = DeliverableReadinessService(test_db)
        result = await svc.check(project.id, YEAR, include_file_checks=False)

        assert result.status == "ready", (
            f"完全就绪项目应 ready，实际 {result.status}，"
            f"blockers={[b.code for b in result.hard_blockers]}"
        )
        assert result.hard_blockers == []
        # 需求 1.1：至少包含 hard_blockers/warnings/trio_status/snapshot_id/逐项证据
        d = result.to_dict()
        assert "hard_blockers" in d and "warnings" in d
        assert "trio_status" in d and len(d["trio_status"]) == 3
        assert d["snapshot_id"], "就绪时应有交付快照摘要 id"
        assert d["sources"].get("tb") and d["sources"].get("formula_push")

    @pytest.mark.asyncio
    async def test_trio_status_fixed_order_and_keys(self, test_db, user):
        project = await _make_ready_project(test_db, user)
        svc = DeliverableReadinessService(test_db)
        result = await svc.check(project.id, YEAR, include_file_checks=False)
        keys = [s["key"] for s in result.trio_status]
        assert keys == ["financial_report", "disclosure_notes", "audit_report"]
        assert [s["sequence"] for s in result.trio_status] == [1, 2, 3]
        # 中文标签（需求 6.6 的后端来源）
        assert all(s["label"] for s in result.trio_status)

    @pytest.mark.asyncio
    async def test_snapshot_digest_excludes_time_and_abs_path(self, test_db, user):
        """两次 check digest 相同（不含生成时间）；content 不含绝对路径（design §3.4/§4.2）。"""
        project = await _make_ready_project(test_db, user)
        svc = DeliverableReadinessService(test_db)
        r1 = await svc.check(project.id, YEAR, include_file_checks=False)
        r2 = await svc.check(project.id, YEAR, include_file_checks=False)
        assert r1.snapshot["digest"] == r2.snapshot["digest"], (
            "同一输入两次 digest 必须相同（digest 不得含生成时间）"
        )
        content_str = str(r1.snapshot["content"])
        assert ":\\" not in content_str and "/home/" not in content_str, (
            "snapshot content 不得包含本机绝对路径"
        )


# ===================================================================
# 2. 硬闸门变异证明：删掉触发条件 ⇒ 对应 blocker 消失
# ===================================================================


class TestHardGateMutations:
    """每个硬闸门：先构造触发条件断言 blocker 出现（修复后红→变异打红的靶子），
    再移除触发条件断言 blocker 消失（闸门确实依条件判定，不是恒亮）。
    """

    async def _codes(self, db, project_id):
        svc = DeliverableReadinessService(db)
        result = await svc.check(project_id, YEAR, include_file_checks=False)
        return {b.code for b in result.hard_blockers}, result

    @pytest.mark.asyncio
    async def test_missing_audited_blocks_then_clears(self, test_db, user):
        project = await _make_ready_project(test_db, user)
        # 变异：把一行 audited_amount 清空 ⇒ 审定数未就绪
        row = (
            await test_db.execute(
                sa.select(TrialBalance).where(TrialBalance.project_id == project.id).limit(1)
            )
        ).scalar_one()
        row.audited_amount = None
        await test_db.flush()
        codes, _ = await self._codes(test_db, project.id)
        assert "upstream_not_ready" in codes

        # 复位 ⇒ blocker 应消失（证明闸门依 audited_amount 判定）
        row.audited_amount = Decimal("110.00")
        await test_db.flush()
        codes2, _ = await self._codes(test_db, project.id)
        assert "upstream_not_ready" not in codes2

    @pytest.mark.asyncio
    async def test_formula_push_failed_blocks(self, test_db, user):
        project = await _make_ready_project(test_db, user)
        run = (
            await test_db.execute(
                sa.select(FormulaPushRun).where(FormulaPushRun.project_id == project.id)
            )
        ).scalar_one()
        run.status = "failed"
        await test_db.flush()
        codes, _ = await self._codes(test_db, project.id)
        assert "upstream_not_ready" in codes

        run.status = "succeeded"
        await test_db.flush()
        codes2, _ = await self._codes(test_db, project.id)
        assert "upstream_not_ready" not in codes2

    @pytest.mark.asyncio
    async def test_unresolved_adjustment_blocks(self, test_db, user):
        project = await _make_ready_project(test_db, user)
        adj = (
            await test_db.execute(
                sa.select(Adjustment).where(Adjustment.project_id == project.id)
            )
        ).scalar_one()
        adj.review_status = ReviewStatus.pending_review
        await test_db.flush()
        codes, _ = await self._codes(test_db, project.id)
        assert "upstream_not_ready" in codes

        adj.review_status = ReviewStatus.approved
        await test_db.flush()
        codes2, _ = await self._codes(test_db, project.id)
        assert "upstream_not_ready" not in codes2

    @pytest.mark.asyncio
    async def test_stale_report_blocks(self, test_db, user):
        project = await _make_ready_project(test_db, user)
        rep = (
            await test_db.execute(
                sa.select(FinancialReport).where(FinancialReport.project_id == project.id)
            )
        ).scalar_one()
        rep.is_stale = True
        await test_db.flush()
        codes, result = await self._codes(test_db, project.id)
        assert "stale_source" in codes
        # 中文原因 + 证据存在
        gate = next(b for b in result.hard_blockers if b.code == "stale_source")
        assert "过期" in gate.message and gate.evidence.get("stale_count") == 1

        rep.is_stale = False
        await test_db.flush()
        codes2, _ = await self._codes(test_db, project.id)
        assert "stale_source" not in codes2

    @pytest.mark.asyncio
    async def test_stale_note_blocks(self, test_db, user):
        project = await _make_ready_project(test_db, user)
        note = (
            await test_db.execute(
                sa.select(DeliverableSectionState).where(
                    DeliverableSectionState.project_id == project.id
                )
            )
        ).scalar_one()
        note.is_stale = True
        await test_db.flush()
        codes, _ = await self._codes(test_db, project.id)
        assert "stale_source" in codes

        note.is_stale = False
        await test_db.flush()
        codes2, _ = await self._codes(test_db, project.id)
        assert "stale_source" not in codes2

    @pytest.mark.asyncio
    async def test_missing_template_or_standard_blocks(self, test_db, user):
        project = await _make_ready_project(test_db, user)
        project.accounting_standard_id = None
        project.template_type = None
        await test_db.flush()
        codes, result = await self._codes(test_db, project.id)
        assert "missing_template_or_standard" in codes
        gate = next(
            b for b in result.hard_blockers if b.code == "missing_template_or_standard"
        )
        assert "会计准则" in str(gate.evidence) or "模板类型" in str(gate.evidence)

    @pytest.mark.asyncio
    async def test_snapshot_inconsistent_blocks(self, test_db, user):
        """三件套绑定不同 tb_hash ⇒ snapshot_inconsistent 硬闸门。"""
        from app.models.phase13_models import WordExportDocType, WordExportTask

        project = await _make_ready_project(test_db, user)
        # 造两个 doc_type task 绑定不同 tb_hash
        for dt, h in (
            (WordExportDocType.financial_report.value, "hashAAA"),
            (WordExportDocType.disclosure_notes.value, "hashBBB"),
        ):
            test_db.add(
                WordExportTask(
                    id=uuid.uuid4(),
                    project_id=project.id,
                    doc_type=dt,
                    status="editing",
                    source_snapshot_refs={"tb_hash": h},
                    created_by=user.id,
                )
            )
        await test_db.flush()
        codes, _ = await self._codes(test_db, project.id)
        assert "snapshot_inconsistent" in codes


# ===================================================================
# 3. 软闸门：warning 不阻断（反向样本必须绿）
# ===================================================================


class TestSoftGateDoesNotBlock:
    @pytest.mark.asyncio
    async def test_partial_formula_push_is_warning_not_blocker(self, test_db, user):
        """公式推送 partial = 软 warning：status 为 ready_with_warnings，而非 blocked。"""
        project = await _make_ready_project(test_db, user)
        run = (
            await test_db.execute(
                sa.select(FormulaPushRun).where(FormulaPushRun.project_id == project.id)
            )
        ).scalar_one()
        run.status = "partial"
        run.skipped_count = 2
        await test_db.flush()

        svc = DeliverableReadinessService(test_db)
        result = await svc.check(project.id, YEAR, include_file_checks=False)

        assert result.status == "ready_with_warnings", (
            f"partial 推送应是软 warning，实际 {result.status}"
        )
        assert result.hard_blockers == [], "软 warning 不得进入 hard_blockers"
        assert any(w.code == "formula_push_partial" for w in result.warnings)
        # 软闸门带中文原因 + 证据
        w = next(w for w in result.warnings if w.code == "formula_push_partial")
        assert "部分成功" in w.message
        assert w.evidence.get("skipped_count") == 2

    @pytest.mark.asyncio
    async def test_warning_coexists_with_blocker_without_masking(self, test_db, user):
        """同时存在 blocker 与 warning 时：status=blocked，warning 不覆盖/不消失。"""
        project = await _make_ready_project(test_db, user)
        run = (
            await test_db.execute(
                sa.select(FormulaPushRun).where(FormulaPushRun.project_id == project.id)
            )
        ).scalar_one()
        run.status = "partial"  # warning
        await test_db.flush()
        rep = (
            await test_db.execute(
                sa.select(FinancialReport).where(FinancialReport.project_id == project.id)
            )
        ).scalar_one()
        rep.is_stale = True  # blocker
        await test_db.flush()

        svc = DeliverableReadinessService(test_db)
        result = await svc.check(project.id, YEAR, include_file_checks=False)
        assert result.status == "blocked"
        assert any(b.code == "stale_source" for b in result.hard_blockers)
        assert any(w.code == "formula_push_partial" for w in result.warnings), (
            "warning 不得被 blocker 覆盖"
        )


# ===================================================================
# 4. phase3 能力 fail-closed
# ===================================================================


class TestPhase3FailClosed:
    @pytest.mark.asyncio
    async def test_missing_phase3_capability_blocks(self, test_db, user, monkeypatch):
        """探测到 phase3 能力模块缺失 ⇒ upstream_not_ready（fail-closed，不默默放行）。"""
        import app.services.deliverable_readiness_service as mod

        def _fake_importable(dotted: str) -> bool:
            # 模拟附注交接能力未入库
            if dotted == "app.services.deliverable_section_state_service":
                return False
            return True

        monkeypatch.setattr(mod, "_module_importable", _fake_importable)

        project = await _make_ready_project(test_db, user)
        svc = DeliverableReadinessService(test_db)
        result = await svc.check(project.id, YEAR, include_file_checks=False)

        assert result.status == "blocked"
        gate = next(
            (b for b in result.hard_blockers if b.code == "upstream_not_ready"), None
        )
        assert gate is not None
        assert "附注章节交接" in str(gate.evidence) or "附注章节交接" in gate.message

    @pytest.mark.asyncio
    async def test_all_capabilities_present_no_capability_blocker(self, test_db, user):
        """能力齐全（HEAD 真实状态）时，不应因能力探测产生 blocker。"""
        project = await _make_ready_project(test_db, user)
        svc = DeliverableReadinessService(test_db)
        result = await svc.check(project.id, YEAR, include_file_checks=False)
        # 不断言 ready（可能有其它源问题），只断言没有「能力缺失」类证据
        for b in result.hard_blockers:
            assert "missing_capabilities" not in b.evidence


# ===================================================================
# 5. 空项目全链阻断 + code 去重
# ===================================================================


class TestEmptyProjectAndDedup:
    @pytest.mark.asyncio
    async def test_empty_project_blocks_with_deduped_codes(self, test_db, user):
        """全空项目：多个来源都触发 upstream_not_ready，但硬闸门按 code 去重为一条。"""
        project = Project(
            id=uuid.uuid4(),
            name="空项目",
            client_name="空公司",
            status="created",
            template_type="soe",
            report_scope="standalone",
            audit_year=YEAR,
            accounting_standard_id=uuid.uuid4(),
        )
        test_db.add(project)
        await test_db.flush()

        svc = DeliverableReadinessService(test_db)
        result = await svc.check(project.id, YEAR, include_file_checks=False)
        assert result.status == "blocked"
        codes = [b.code for b in result.hard_blockers]
        # upstream_not_ready 只出现一次（去重），duplicates 证据保留其余
        assert codes.count("upstream_not_ready") == 1
        gate = next(b for b in result.hard_blockers if b.code == "upstream_not_ready")
        assert gate.evidence.get("duplicates"), "去重后其余同 code 原因应进 duplicates 证据"

    @pytest.mark.asyncio
    async def test_nonexistent_project_blocks(self, test_db):
        svc = DeliverableReadinessService(test_db)
        result = await svc.check(uuid.uuid4(), YEAR, include_file_checks=False)
        assert result.status == "blocked"
        assert any(
            b.code == "missing_template_or_standard" for b in result.hard_blockers
        )
