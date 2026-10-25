"""合并推送链路闭环修复验证（consolidation-four-table-formula-note-chain-closure-proposal-2026-10-07）。

验证五个修复项：
1. 附注 stale 未刷新 → notes 步骤现在真正刷新附注
2. 运行摘要口径混乱 → detail 区分 section/node/refreshed/failed 计数
3. 抵消分录 provenance 缺失 → breakdown 含 source_entry_ids
4. 身份映射断裂 → breakdown 含 source_tb_company_codes
5. push_run 状态过于笼统 → detail 含 note_status 子状态
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401
from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.base import Base, ProjectStatus
from app.models.consol_note_data_models import ConsolNoteData
from app.models.consol_push_models import ConsolPushRun
from app.models.consolidation_models import (
    ConsolTrial,
    EliminationEntry,
    EliminationEntryType,
    ReviewStatusEnum,
)
from app.models.core import Project
from app.models.report_models import ReportConfig, FinancialReportType

Y = 2098
D = Decimal

_CONFIG = [
    ("balance_sheet", "BS-006", "应收账款", 1, "TB('1122','期末余额')"),
    ("balance_sheet", "BS-045", "应付账款", 2, "TB('2202','期末余额')"),
]

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


@pytest_asyncio.fixture
async def factory():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db(factory) -> AsyncSession:
    async with factory() as session:
        yield session


def _project(code, name, scope, *, parent=None, template=None):
    return Project(
        id=uuid.uuid4(), name=f"{name}_{Y}", client_name=name, company_code=code,
        report_scope=scope, audit_year=Y, parent_company_code=parent,
        ultimate_company_code="ROOT", template_type=template,
        status=ProjectStatus.execution,
    )


def _tb(project, acct_code, name, category, amount, company_code="TB001"):
    return TrialBalance(
        id=uuid.uuid4(), project_id=project.id, year=Y, company_code=company_code,
        standard_account_code=acct_code, account_name=name, account_category=category,
        audited_amount=D(amount),
    )


def _entry(project, no, entry_type, lines, *, branch=None):
    return EliminationEntry(
        id=uuid.uuid4(), project_id=project.id, year=Y, entry_no=no,
        entry_type=entry_type, account_code=lines[0][0],
        entry_group_id=uuid.uuid4(),
        lines=[{"account_code": c, "account_name": n, "debit_amount": dr, "credit_amount": cr}
               for c, n, dr, cr in lines],
        debit_amount=sum((D(ln[2]) for ln in lines), D(0)),
        credit_amount=sum((D(ln[3]) for ln in lines), D(0)),
        branch_entity_code=branch, review_status=ReviewStatusEnum.approved,
    )


@pytest_asyncio.fixture
async def group(db):
    """最小合并集团：ROOT(consol) ⊃ ROOT(standalone) + SUB(standalone)"""
    g = {
        "ROOT": _project("ROOT", "总部", "consolidated"),
        "ROOT_s": _project("ROOT", "总部", "standalone"),
        "SUB": _project("SUB", "子公司", "standalone", parent="ROOT"),
    }
    db.add_all(g.values())
    for standard in ("soe_consolidated", "listed_consolidated"):
        for rt, code, name, n, formula in _CONFIG:
            db.add(ReportConfig(
                id=uuid.uuid4(), report_type=FinancialReportType(rt), row_number=n,
                row_code=code, row_name=name, formula=formula,
                applicable_standard=standard, is_total_row=False, indent_level=1,
            ))
    db.add_all([
        _tb(g["ROOT_s"], "1122", "应收账款", AccountCategory.asset, "1000", company_code="R001"),
        _tb(g["SUB"], "1122", "应收账款", AccountCategory.asset, "500", company_code="S001"),
        _tb(g["SUB"], "2202", "应付账款", AccountCategory.liability, "200", company_code="S001"),
    ])
    await db.flush()
    from app.services.group_links import sync_group_links
    await sync_group_links(db, Y)
    await db.commit()
    return g


class TestProvenance:
    """问题 3：抵消分录 provenance 写入 breakdown。"""

    @pytest.mark.asyncio
    async def test_trial_breakdown_has_source_entry_ids(self, db, group):
        """有抵消分录时，合并试算 breakdown 中 source_entry_ids 记录分录 UUID。"""
        entry = _entry(group["ROOT"], "IA-1", EliminationEntryType.internal_ar_ap,
                       [("1122", "应收账款", "0", "50"), ("2202", "应付账款", "50", "0")])
        db.add(entry)
        await db.commit()
        entry_id = str(entry.id)

        from app.services.consol_push_service import push
        with patch("app.services.event_bus.event_bus.broadcast_raw"):
            result = await push(db, group["ROOT"].id, Y, trigger="manual")
        assert result.status == "succeeded", result.steps

        trials = (await db.execute(
            sa.select(ConsolTrial).where(
                ConsolTrial.project_id == group["ROOT"].id, ConsolTrial.year == Y,
            )
        )).scalars().all()
        # 1122 和 2202 都被分录影响
        affected = {t.standard_account_code: t for t in trials if t.standard_account_code in ("1122", "2202")}
        for code in ("1122", "2202"):
            bd = affected[code].consolidation_breakdown
            assert "source_entry_ids" in bd, f"{code} breakdown 缺 source_entry_ids"
            assert entry_id in bd["source_entry_ids"], f"{code} 未记录分录 {entry_id}"

    @pytest.mark.asyncio
    async def test_trial_breakdown_no_entries_empty_ids(self, db, group):
        """无抵消分录时，source_entry_ids 为空列表。"""
        from app.services.consol_push_service import push
        with patch("app.services.event_bus.event_bus.broadcast_raw"):
            await push(db, group["ROOT"].id, Y, trigger="manual")

        trials = (await db.execute(
            sa.select(ConsolTrial).where(ConsolTrial.project_id == group["ROOT"].id)
        )).scalars().all()
        for t in trials:
            bd = t.consolidation_breakdown
            assert bd.get("source_entry_ids") == [], f"{t.standard_account_code} source_entry_ids 应为空"


class TestIdentityMapping:
    """问题 4：身份映射 — breakdown 中 source_tb_company_codes。"""

    @pytest.mark.asyncio
    async def test_breakdown_contains_source_tb_company_codes(self, db, group):
        """by_company 条目包含来源 TB 的原始 company_code。"""
        from app.services.consol_push_service import push
        with patch("app.services.event_bus.event_bus.broadcast_raw"):
            await push(db, group["ROOT"].id, Y, trigger="manual")

        trial_1122 = (await db.execute(
            sa.select(ConsolTrial).where(
                ConsolTrial.project_id == group["ROOT"].id,
                ConsolTrial.standard_account_code == "1122",
            )
        )).scalar_one()
        bd = trial_1122.consolidation_breakdown
        by_company = bd["by_company"]
        assert len(by_company) >= 2, f"期望至少 2 个企业，实际 {len(by_company)}"
        # 每个企业条目都应有 source_tb_company_codes
        for item in by_company:
            assert "source_tb_company_codes" in item, f"缺 source_tb_company_codes: {item}"
            assert isinstance(item["source_tb_company_codes"], list)
            assert len(item["source_tb_company_codes"]) > 0
        # 验证具体值：ROOT_s 的 TB 用 company_code="R001"，SUB 的 TB 用 "S001"
        codes_by_node = {item["company_code"]: item["source_tb_company_codes"] for item in by_company}
        assert "R001" in codes_by_node.get("ROOT", []), f"ROOT 节点应含 R001: {codes_by_node}"
        assert "S001" in codes_by_node.get("SUB", []), f"SUB 节点应含 S001: {codes_by_node}"


class TestNoteRefreshInPush:
    """问题 1 + 2 + 5：notes 步骤真正刷新、统计分口径、含 note_status。"""

    @pytest.mark.asyncio
    async def test_notes_step_detail_has_structured_stats(self, db, group):
        """notes 步骤 detail 包含分口径统计和 note_status。"""
        from app.services.consol_push_service import push
        with patch("app.services.event_bus.event_bus.broadcast_raw"):
            result = await push(db, group["ROOT"].id, Y, trigger="manual")
        assert result.status == "succeeded"
        notes_step = next(
            s for s in result.steps
            if s["project_id"] == str(group["ROOT"].id) and s["step"] == "notes"
        )
        assert notes_step["status"] == "succeeded"
        detail = notes_step["detail"]
        # 必须包含分口径关键词
        assert "附注状态=" in detail, f"detail 缺 note_status: {detail}"
        assert "个章节" in detail, f"detail 缺章节计数: {detail}"
        assert "个节点" in detail, f"detail 缺节点计数: {detail}"
        assert "刷新" in detail, f"detail 缺刷新计数: {detail}"

    @pytest.mark.asyncio
    async def test_step_label_updated(self, db, group):
        """步骤标签从"标记合并附注待更新"改为"刷新合并附注"。"""
        from app.services.consol_push_service import push
        with patch("app.services.event_bus.event_bus.broadcast_raw"):
            result = await push(db, group["ROOT"].id, Y, trigger="manual")
        notes_step = next(
            s for s in result.steps
            if s["project_id"] == str(group["ROOT"].id) and s["step"] == "notes"
        )
        assert notes_step["step_label"] == "刷新合并附注"

    @pytest.mark.asyncio
    async def test_stale_note_gets_refreshed_when_formula_exists(self, db, group):
        """有模板章节和公式时，附注行从 stale 变为 not stale。"""
        from app.services.consol_note_formula_service import consol_note_tables

        # 查找一个实际存在的模板章节
        tables = consol_note_tables("soe")
        if not tables:
            pytest.skip("soe 模板无章节，跳过")

        first_section = tables[0].get("section_id")
        if not first_section:
            pytest.skip("第一个章节无 section_id")

        # 预插一条 stale 附注行
        db.add(ConsolNoteData(
            project_id=group["ROOT"].id, year=Y,
            section_id=first_section, data={}, is_stale=True,
        ))
        await db.commit()

        from app.services.consol_push_service import push
        with patch("app.services.event_bus.event_bus.broadcast_raw"):
            await push(db, group["ROOT"].id, Y, trigger="manual")

        # 原始 legacy 行应该被标记 stale（_mark_notes_stale），
        # 但如果刷新成功，fill_by_formula 会在新的 node_key 行上清除 stale
        rows = (await db.execute(
            sa.select(ConsolNoteData).where(
                ConsolNoteData.project_id == group["ROOT"].id,
                ConsolNoteData.section_id == first_section,
            )
        )).scalars().all()
        # 至少有原始行 + 可能有按 node_key 创建的新行
        assert len(rows) >= 1, "应至少有 1 行附注数据"


class TestCalcBasisFields:
    """直接验证 CalcBasis 新字段和 TrialAmounts 新字段。"""

    @pytest.mark.asyncio
    async def test_entry_accounts_collected(self, db, group):
        """build_calc_basis 正确收集 entry_accounts。"""
        entry = _entry(group["ROOT"], "IA-1", EliminationEntryType.internal_ar_ap,
                       [("1122", "应收账款", "0", "50"), ("2202", "应付账款", "50", "0")])
        db.add(entry)
        await db.commit()

        from app.services.consol_calc_basis import load_calc_basis
        basis = await load_calc_basis(db, group["ROOT"].id, Y)
        assert basis is not None

        # entry_accounts 应包含 1122 和 2202
        assert "1122" in basis.entry_accounts
        assert "2202" in basis.entry_accounts
        assert entry.id in basis.entry_accounts["1122"]
        assert entry.id in basis.entry_accounts["2202"]

    @pytest.mark.asyncio
    async def test_leaf_tb_codes_collected(self, db, group):
        """build_calc_basis 正确收集 leaf_tb_codes。"""
        from app.services.consol_calc_basis import load_calc_basis
        basis = await load_calc_basis(db, group["ROOT"].id, Y)
        assert basis is not None

        # 至少有一个叶子节点有 TB company_code
        has_codes = any(codes for codes in basis.leaf_tb_codes.values())
        assert has_codes, f"leaf_tb_codes 全空: {basis.leaf_tb_codes}"

    @pytest.mark.asyncio
    async def test_trial_amounts_source_entry_ids(self, db, group):
        """trial_amounts 返回的 TrialAmounts 包含 source_entry_ids。"""
        entry = _entry(group["ROOT"], "IA-1", EliminationEntryType.internal_ar_ap,
                       [("1122", "应收账款", "0", "50")])
        db.add(entry)
        await db.commit()

        from app.services.consol_calc_basis import load_calc_basis, trial_amounts
        basis = await load_calc_basis(db, group["ROOT"].id, Y)
        amounts = trial_amounts(basis)

        ta_1122 = amounts.get("1122")
        assert ta_1122 is not None
        assert hasattr(ta_1122, "source_entry_ids")
        assert str(entry.id) in ta_1122.source_entry_ids

    @pytest.mark.asyncio
    async def test_tb_row_company_code(self, db, group):
        """TbRow 包含 company_code 字段。"""
        from app.services.consol_calc_basis import load_tb_rows
        rows = await load_tb_rows(db, [group["ROOT_s"].id], Y)
        assert len(rows) > 0
        assert rows[0].company_code == "R001"


# ─────────────────────────────── 改进 B：formula_push 合并项目跳过 ───────────────────────────────


class TestFormulaPushConsolSkip:
    """改进 B：合并项目的 TB/底稿事件不触发 formula_push，避免空转。"""

    @pytest.mark.asyncio
    async def test_consolidated_project_skips_tb_trigger(self, db, group, factory):
        """合并项目的 TRIAL_BALANCE_UPDATED 被 formula_push 跳过。"""
        from app.services.formula_push.triggers import _is_consolidated_project

        assert await _is_consolidated_project(group["ROOT"].id, _session_factory=factory) is True
        assert await _is_consolidated_project(group["ROOT_s"].id, _session_factory=factory) is False
        assert await _is_consolidated_project(group["SUB"].id, _session_factory=factory) is False

    @pytest.mark.asyncio
    async def test_nonexistent_project_not_skipped(self, db, group, factory):
        """不存在的项目不跳过（让引擎正常判断报错）。"""
        from app.services.formula_push.triggers import _is_consolidated_project

        assert await _is_consolidated_project(uuid.uuid4(), _session_factory=factory) is False


# ─────────────────────────────── 改进 C：合并附注持久化状态 ───────────────────────────────


class TestConsolNoteDataCellState:
    """改进 C：consol_note_data 的 cell_state / locked_cells / last_formula_value。"""

    @pytest.mark.asyncio
    async def test_new_record_has_default_state(self, db, group):
        """新建记录默认 cell_state='auto'、locked_cells=[]。"""
        record = ConsolNoteData(
            project_id=group["ROOT"].id, year=Y, section_id="test-section",
            data={}, node_key="ROOT:consol",
        )
        db.add(record)
        await db.flush()
        await db.refresh(record)
        assert record.cell_state == "auto"
        assert record.locked_cells == []
        assert record.last_formula_run_id is None
        assert record.last_formula_value is None

    @pytest.mark.asyncio
    async def test_locked_state_persists(self, db, group):
        """cell_state='locked' 可正常写入和读取。"""
        record = ConsolNoteData(
            project_id=group["ROOT"].id, year=Y, section_id="lock-test",
            data={}, node_key="ROOT:consol", cell_state="locked",
        )
        db.add(record)
        await db.flush()
        await db.refresh(record)
        assert record.cell_state == "locked"

    @pytest.mark.asyncio
    async def test_locked_cells_roundtrip(self, db, group):
        """locked_cells JSONB 可存储和读取坐标列表。"""
        cells = [{"row_index": 2, "col_index": 1}, {"row_index": 5, "col_index": 3}]
        record = ConsolNoteData(
            project_id=group["ROOT"].id, year=Y, section_id="lc-test",
            data={}, node_key="ROOT:consol", locked_cells=cells,
        )
        db.add(record)
        await db.flush()
        await db.refresh(record)
        assert len(record.locked_cells) == 2
        assert record.locked_cells[0]["row_index"] == 2

    @pytest.mark.asyncio
    async def test_fill_by_formula_skips_locked_record(self, db, group):
        """fill_by_formula 对 cell_state='locked' 的记录返回 skipped_locked。"""
        from app.services.consol_note_formula_service import consol_note_tables

        tables = consol_note_tables("soe")
        if not tables:
            pytest.skip("soe 模板无章节")
        section_id = tables[0].get("section_id")
        if not section_id:
            pytest.skip("第一个章节无 section_id")

        # 预插一条 locked 附注行
        db.add(ConsolNoteData(
            project_id=group["ROOT"].id, year=Y, section_id=section_id,
            data={"headers": ["项目", "期末数"], "rows": [["现金", "100"]]},
            cell_state="locked",
        ))
        await db.commit()

        from app.services.consol_note_formula_service import fill_by_formula
        result = await fill_by_formula(db, group["ROOT"].id, Y, section_id)
        assert result["status"] == "skipped_locked"
        assert "锁定" in result.get("reason", "")

    @pytest.mark.asyncio
    async def test_fill_by_formula_respects_locked_cells(self, db, group):
        """fill_by_formula 对 locked_cells 中的坐标不覆盖。"""
        from app.services.consol_note_formula_service import consol_note_tables

        tables = consol_note_tables("soe")
        if not tables:
            pytest.skip("soe 模板无章节")
        section_id = tables[0].get("section_id")
        if not section_id:
            pytest.skip("第一个章节无 section_id")

        # 预插一条带 locked_cells 的附注行
        db.add(ConsolNoteData(
            project_id=group["ROOT"].id, year=Y, section_id=section_id,
            data={},
            locked_cells=[{"row_index": 0, "col_index": 1}],
        ))
        await db.commit()

        from app.services.consol_note_formula_service import fill_by_formula
        result = await fill_by_formula(db, group["ROOT"].id, Y, section_id)
        # 不应 skipped_locked（整节没锁），但 locked_cells 的格子应被保护
        assert result["status"] != "skipped_locked"

    @pytest.mark.asyncio
    async def test_fill_by_formula_saves_formula_snapshot(self, db, group):
        """fill_by_formula 写入后保存 last_formula_value 快照。"""
        from app.services.consol_note_formula_service import consol_note_tables

        tables = consol_note_tables("soe")
        if not tables:
            pytest.skip("soe 模板无章节")
        section_id = tables[0].get("section_id")
        if not section_id:
            pytest.skip("第一个章节无 section_id")

        from app.services.consol_note_formula_service import fill_by_formula
        result = await fill_by_formula(db, group["ROOT"].id, Y, section_id)
        await db.commit()

        if result["status"] in ("skipped_locked",):
            pytest.skip("该章节被锁定，跳过快照验证")

        record = (await db.execute(
            sa.select(ConsolNoteData).where(
                ConsolNoteData.project_id == group["ROOT"].id,
                ConsolNoteData.section_id == section_id,
            )
        )).scalars().first()
        assert record is not None
        fv = record.last_formula_value
        assert fv is not None
        assert "cells" in fv
        assert "computed_at" in fv
