"""真 PG 测试：report adapter 六枚举 + note adapter rows[].values 形状 + workpaper adapter 不新建工作表。

需求 1.8 / ADR-FHIC-06 第 6、8 点。
变异 #7：report adapter 枚举改回短码 → 测试红。
变异 #6：workpaper adapter 的 ``require_existing_sheet`` 改回默认（新建表）→ ``TestWorkpaperAdapterMissingSheetPg`` 红。
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.services.formula_runtime.adapters.report import (
    VALID_REPORT_TYPES,
    _validate_locator as report_validate_locator,
)
from app.services.formula_runtime.adapters.note import (
    _get_cell_value,
    _set_cell_value,
)
from app.services.formula_runtime.contracts import CanonicalFormulaTarget

# F41 六枚举——这是 VALID_REPORT_TYPES 应该恰好等于的集合（逐字抄 requirements F41，独立于 ORM 写死）
# 🔴 2026-10-30 勘误：原先这里写的是 equity_change_statement / trial_balance_audit / coverage_stats，
#    与 F41 原文及真库 `financial_report_type` 枚举都不符（实现照抄了同一份错值，两边互相掩盖）；
#    共享库只读现查六个标签与下式逐个相等，financial_report 六类都有真实行
F41_ENUM_VALUES = frozenset({
    "balance_sheet",
    "income_statement",
    "cash_flow_statement",
    "equity_statement",
    "cash_flow_supplement",
    "impairment_provision",
})

# 短码（旧值，应被拒绝）
SHORT_CODES = ["BS", "IS", "CFS", "EQ", "CFSS", "IMP"]


# =========================================================================
# report adapter 枚举校验（纯 Python，不需 PG）
# =========================================================================


class TestReportAdapterEnumValidation:
    """report adapter 枚举校验。

    变异 #7 目标：VALID_REPORT_TYPES 改回短码 → 本类全红。
    """

    def test_valid_report_types_equals_f41(self):
        """VALID_REPORT_TYPES 恰好等于 F41 六枚举值。"""
        assert VALID_REPORT_TYPES == F41_ENUM_VALUES

    @pytest.mark.parametrize("report_type", sorted(F41_ENUM_VALUES))
    def test_f41_values_accepted(self, report_type: str):
        """F41 六枚举值逐个通过校验。"""
        locator = {"report_type": report_type, "row_code": "1001", "period": "current"}
        report_validate_locator(locator)  # 不抛即通过

    @pytest.mark.parametrize("short_code", SHORT_CODES)
    def test_short_codes_rejected(self, short_code: str):
        """短码一律拒绝。"""
        locator = {"report_type": short_code, "row_code": "1001", "period": "current"}
        with pytest.raises(ValueError, match="Invalid report_type"):
            report_validate_locator(locator)


# =========================================================================
# report adapter 真 PG 行读取
# =========================================================================


# 需求 1.8「六枚举各一行」：F41 六个值都是 PG 真实枚举成员（原先只取了 3 个「交集」，另 3 个是错值）
_PG_AVAILABLE = sorted(F41_ENUM_VALUES)


async def _add_project(session, pid: uuid.UUID, name: str) -> None:
    """建【测试】项目（外键依赖）。按 ORM 带上非空列：原先裸 INSERT 只给 id/name/client_name，
    真 PG 上 ``projects.status`` 非空约束直接报错 —— 因为从未在 PG 上跑过，一直没暴露。"""
    from app.models.core import Project, ProjectStatus, ProjectType

    session.add(Project(id=pid, name=name, client_name="【测试】", project_type=ProjectType.annual,
                        status=ProjectStatus.planning, template_type="soe", report_scope="standalone"))
    await session.flush()


@pytest.mark.pg_only
class TestReportAdapterPgShape:
    """report adapter 真 PG 行读取：六枚举各一行端到端读取（插入→prepare_many）。

    🔴 2026-10-30 补 ``pg_only``：原先没标，非 PG 运行恒 skip、发布清单的 ``-m pg_only`` 运行又把它 deselect ⇒ 从未执行。
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("report_type", _PG_AVAILABLE)
    async def test_prepare_reads_pg_row(self, pg_tx, report_type: str):
        """adapter.prepare_many 能从真 PG 读到已插入的行。"""
        from app.models.report_models import FinancialReport
        from app.services.formula_runtime.adapters.report import ReportMutationAdapter

        pid = uuid.uuid4()
        year = 2025
        row_code = f"test_{report_type[:3]}"
        amount = Decimal("12345.67")

        # 建 project（外键依赖）
        await _add_project(pg_tx, pid, "【测试】PG形状")

        row = FinancialReport(
            project_id=pid,
            year=year,
            report_type=report_type,
            row_code=row_code,
            current_period_amount=amount,
        )
        pg_tx.add(row)
        await pg_tx.flush()

        adapter = ReportMutationAdapter(pg_tx)
        target = CanonicalFormulaTarget(
            domain="report",
            project_id=pid,
            year=year,
            addr_id=f"report/{report_type}/{row_code}/current",
            locator={
                "report_type": report_type,
                "row_code": row_code,
                "period": "current",
            },
        )
        mutations = await adapter.prepare_many([target], {target.addr_id: Decimal("99999")})
        assert len(mutations) == 1
        assert mutations[0].before_value == str(amount)


# =========================================================================
# note adapter rows[].values 形状（纯 Python）
# =========================================================================


class TestNoteAdapterRowsValues:
    """note adapter rows[].values 形状读写。"""

    def test_get_cell_from_rows_values_by_index(self):
        """按行序号 "0"/"1" 从 rows[].values 读取。"""
        table_data = {
            "rows": [
                {"values": {"期末余额": "100.00", "期初余额": "50.00"}},
                {"values": {"期末余额": "200.00", "期初余额": "80.00"}},
            ]
        }
        assert _get_cell_value(table_data, "0", "期末余额") == "100.00"
        assert _get_cell_value(table_data, "1", "期初余额") == "80.00"

    def test_set_cell_in_rows_values(self):
        """能向 rows[].values 形状写入值，不影响其他列。"""
        table_data = {
            "rows": [
                {"values": {"期末余额": "100.00", "期初余额": "50.00"}},
            ]
        }
        result = _set_cell_value(table_data, "0", "期末余额", "999.99")
        assert result["rows"][0]["values"]["期末余额"] == "999.99"
        assert result["rows"][0]["values"]["期初余额"] == "50.00"

    def test_get_cell_by_first_value_text(self):
        """按首格文本匹配行。"""
        table_data = {
            "rows": [
                {"values": {"科目": "应收账款", "金额": "100"}},
                {"values": {"科目": "应付账款", "金额": "200"}},
            ]
        }
        assert _get_cell_value(table_data, "应收账款", "金额") == "100"
        assert _get_cell_value(table_data, "应付账款", "金额") == "200"

    def test_set_cell_by_first_value_text(self):
        """按首格文本匹配行并写入。"""
        table_data = {
            "rows": [
                {"values": {"科目": "应收账款", "金额": "100"}},
            ]
        }
        result = _set_cell_value(table_data, "应收账款", "金额", "888")
        assert result["rows"][0]["values"]["金额"] == "888"

    def test_get_cell_returns_none_for_nonexistent_row(self):
        """不存在的行返回 None。"""
        table_data = {
            "rows": [
                {"values": {"期末余额": "100.00"}},
            ]
        }
        assert _get_cell_value(table_data, "99", "期末余额") is None


# =========================================================================
# note adapter 真 PG rows[].values 表
# =========================================================================


@pytest.mark.pg_only
class TestNoteAdapterPgRowsValues:
    """note adapter 真 PG：一张 rows[].values 附注表（2026-10-30 补 ``pg_only``，原因同上）。"""

    @pytest.mark.asyncio
    async def test_prepare_reads_rows_values_note(self, pg_tx):
        """adapter.prepare_many 能从真 PG 附注表读出 rows[].values 值。"""
        from app.models.report_models import DisclosureNote
        from app.services.formula_runtime.adapters.note import NoteMutationAdapter

        pid = uuid.uuid4()
        year = 2025
        section = "五、1"

        await _add_project(pg_tx, pid, "【测试】附注形状")

        note = DisclosureNote(
            project_id=pid,
            year=year,
            note_section=section,
            section_title="测试附注",
            table_data={
                "rows": [
                    {"values": {"期末余额": "123.45", "期初余额": "67.89"}},
                    {"values": {"期末余额": "200.00", "期初余额": "100.00"}},
                ]
            },
        )
        pg_tx.add(note)
        await pg_tx.flush()

        adapter = NoteMutationAdapter(pg_tx)
        target = CanonicalFormulaTarget(
            domain="note",
            project_id=pid,
            year=year,
            addr_id=f"note/{section}/0/期末余额",
            locator={
                "section": section,
                "row": "0",
                "column": "期末余额",
                "cell_type": "auto",
            },
        )
        mutations = await adapter.prepare_many(
            [target], {target.addr_id: "999.00"}
        )
        assert len(mutations) == 1
        assert mutations[0].before_value == "123.45"
        assert mutations[0].after_value == "999.00"


# =========================================================================
# workpaper adapter 真 PG：写不存在的工作表（ADR-FHIC-06 第 6 点「双重防线」的第二道）
# =========================================================================


@pytest.mark.pg_only
class TestWorkpaperAdapterMissingSheetPg:
    """``apply_many`` 写 parsed_data 时目标工作表不存在 ⇒ 抛错、不新建工作表（变异 #6 的判据）。

    计划阶段已把错 sheet 的公式判 blocked（``typed_eval._target_sheet_problem``），所以 29 行重放走不到这道防线；
    这里绕过计划阶段，直接把指向不存在工作表的 mutation 交给生产 adapter。
    """

    @pytest.mark.asyncio
    async def test_apply_refuses_missing_sheet_and_keeps_html_keys(self, pg_tx):
        from sqlalchemy import text

        from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType
        from app.services.formula_runtime.adapters.workpaper import WorkpaperMutationAdapter
        from app.services.formula_runtime.contracts import FormulaMutation

        pid = uuid.uuid4()
        await _add_project(pg_tx, pid, "【测试】底稿写入防线")
        idx = WpIndex(project_id=pid, wp_code="FHM6", wp_name="【测试】错 sheet 写入")
        pg_tx.add(idx)
        await pg_tx.flush()
        wp = WorkingPaper(project_id=pid, wp_index_id=idx.id, file_path="fhm6.xlsx", source_type=WpSourceType.template,
                          parsed_data={"html_data": {"审定表": {"cells": {"B5": "1"}, "max_row": 5, "max_col": 2}}})
        pg_tx.add(wp)
        await pg_tx.flush()

        def _mutation(sheet: str) -> FormulaMutation:
            locator = {"wp_id": str(wp.id), "storage_kind": "parsed_data", "sheet_name": sheet, "cell_ref": "B5"}
            return FormulaMutation(
                target=CanonicalFormulaTarget(domain="workpaper", project_id=pid, year=2025,
                                              addr_id=f"wp/{wp.id}/{sheet}/B5", locator=locator, wp_id=wp.id),
                before_value="1", after_value=Decimal("99"))

        async def _sheets() -> set[str]:
            raw = (await pg_tx.execute(text("SELECT parsed_data FROM working_paper WHERE id = :i"),
                                       {"i": wp.id})).scalar_one()
            return set((raw or {}).get("html_data") or {})

        adapter = WorkpaperMutationAdapter(pg_tx)
        with pytest.raises(ValueError, match="目标工作表不存在"):
            await adapter.apply_many([_mutation("不存在的表")])
        assert await _sheets() == {"审定表"}, "写不存在的工作表时新建了工作表"
        # 对照：同一 adapter 写已有工作表照常落库（判据不空转）
        assert len(await adapter.apply_many([_mutation("审定表")])) == 1
        raw = (await pg_tx.execute(text("SELECT parsed_data #>> '{html_data,审定表,cells,B5,value}' FROM working_paper "
                                        "WHERE id = :i"), {"i": wp.id})).scalar_one()
        assert raw == "99" and await _sheets() == {"审定表"}, raw
