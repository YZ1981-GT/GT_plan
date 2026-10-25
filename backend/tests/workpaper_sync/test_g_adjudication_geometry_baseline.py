# -*- coding: utf-8 -*-
"""G 循环 13 张审定表几何基线守卫（Task 1 · P1/P2）。

spec: `g-cycle-adjudication-sheets-coverage` · Task 1
      Requirements 1.2 / 1.3 / 2.1 / 4.1

═══ 判据面 ═══

P1：13 张公式总数 ≥ 2700（现算 2790，不写死精确值 —— 模板小修不应打红）。
P2：13 张全命中裸 IF（每张 ≥ 1）—— 这是 G 循环审定表最显著的结构特征。

🔴 本守卫**不依赖 `AdjudicationSheetSpec` 引擎**：纯 openpyxl 读模板逐格扫描，
   只要模板 xlsx 存在即可运行。

🔴 现算基线（2026-10-07 openpyxl 实测，与 tasks.md 表头有偏差 —— 以现算为准）：
   G1-1  98×11  504f  63 IF
   G2-1  41×11  132f  19 IF
   G3-1  48×22  120f  18 IF
   G4-1  46×11  176f  29 IF
   G5-1  87×13  501f  61 IF
   G6-1  76×11  340f  48 IF
   G8-1  29×11  100f  12 IF
   G9-1  74×15  390f  42 IF
   G10-1 63×12  178f  28 IF
   G11-1 79×11  161f  19 IF
   G12-1 23×11   38f   7 IF
   G13-1 35×11   78f  11 IF
   G14-1 36×11   72f  11 IF
   合计：2790 公式格 / 368 裸 IF
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import openpyxl
import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

TPL_G = _BACKEND / "wp_templates" / "G"

# ─── 13 张审定表的映射（wp_code → (workbook, sheet_name)） ───────────────
ADJUDICATION_SHEETS: dict[str, tuple[str, str]] = {
    "G1-1": ("G1 交易性金融资产.xlsx", "审定表G1-1"),
    "G2-1": ("G2 应收利息.xlsx", "审定表G2-1"),
    "G3-1": ("G3 应收股利.xlsx", "审定表G3-1"),
    "G4-1": ("G4 债权投资.xlsx", "审定表G4-1"),
    "G5-1": ("G5 长期应收款.xlsx", "审定表G5-1"),
    "G6-1": ("G6 其他债权投资.xlsx", "审定表G6-1"),
    "G8-1": ("G8 其他权益工具投资.xlsx", "审定表G8-1"),
    "G9-1": ("G9 其他非流动金融资产.xlsx", "审定表G9-1"),
    "G10-1": ("G10 交易性金融负债.xlsx", "审定表G10-1"),
    "G11-1": ("G11 投资收益.xlsx", "审定表G11-1"),
    "G12-1": ("G12 净敞口套期收益.xlsx", "审定表G12-1"),
    "G13-1": ("G13 公允价值变动收益.xlsx", "审定表G13-1"),
    "G14-1": ("G14 信用减值损失.xlsx", "审定表G14-1"),
}

# ─── 现算下限（2026-10-07 实测值的 ~95% 取整，容忍模板小修不打红） ──────
_TOTAL_FORMULA_FLOOR = 2700  # 现算 2790
_TOTAL_BARE_IF_FLOOR = 350   # 现算 368
# 每张审定表的公式下限（现算值 ×0.9 取整，防止单表漏检）
_PER_SHEET_FORMULA_FLOOR: dict[str, int] = {
    "G1-1": 450,   # 现算 504
    "G2-1": 115,   # 现算 132
    "G3-1": 105,   # 现算 120
    "G4-1": 155,   # 现算 176
    "G5-1": 450,   # 现算 501
    "G6-1": 300,   # 现算 340
    "G8-1": 85,    # 现算 100
    "G9-1": 350,   # 现算 390
    "G10-1": 155,  # 现算 178
    "G11-1": 140,  # 现算 161
    "G12-1": 30,   # 现算 38
    "G13-1": 65,   # 现算 78
    "G14-1": 60,   # 现算 72
}


def _scan_sheet(wb_name: str, sheet_name: str) -> tuple[int, int, int, int]:
    """扫描一张 sheet，返回 (rows, cols, formula_count, bare_if_count)。"""
    fp = TPL_G / wb_name
    assert fp.exists(), f"模板不存在：{fp}"
    wb = openpyxl.load_workbook(fp, read_only=True, data_only=False)
    assert sheet_name in wb.sheetnames, (
        f"{wb_name} 里没有 {sheet_name!r}（sheetnames={wb.sheetnames}）"
    )
    ws = wb[sheet_name]
    rows = ws.max_row
    cols = ws.max_column
    formula_count = 0
    bare_if = 0
    for row in ws.iter_rows(min_row=1, max_row=rows, max_col=cols):
        for cell in row:
            v = cell.value
            if isinstance(v, str) and v.startswith("="):
                formula_count += 1
                upper = v.upper()
                if (
                    upper.startswith("=IF(")
                    or ",IF(" in upper
                    or "+IF(" in upper
                    or "-IF(" in upper
                ):
                    bare_if += 1
    wb.close()
    return rows, cols, formula_count, bare_if


@pytest.fixture(scope="module")
def geometry() -> dict[str, tuple[int, int, int, int]]:
    """模块级 fixture：逐张扫描 13 张审定表，返回 {code: (rows, cols, formulas, bare_if)}。"""
    result = {}
    for code, (wb_name, sheet_name) in sorted(ADJUDICATION_SHEETS.items()):
        result[code] = _scan_sheet(wb_name, sheet_name)
    return result


# ═══════════════════════════════════════════════════════════════════════════
#  P1：13 张公式总数下限
# ═══════════════════════════════════════════════════════════════════════════


class TestP1TotalFormulaFloor:
    """P1：13 张审定表公式总数 ≥ {_TOTAL_FORMULA_FLOOR}（GC-10 判据）。"""

    def test_total_formula_count_above_floor(self, geometry) -> None:
        total = sum(g[2] for g in geometry.values())
        assert total >= _TOTAL_FORMULA_FLOOR, (
            f"13 张审定表公式总数 {total} < 下限 {_TOTAL_FORMULA_FLOOR}（模板被大幅简化？）"
        )

    @pytest.mark.parametrize("code", sorted(ADJUDICATION_SHEETS))
    def test_per_sheet_formula_above_floor(self, code: str, geometry) -> None:
        """每张审定表公式数 ≥ 各自下限。"""
        formula_count = geometry[code][2]
        floor = _PER_SHEET_FORMULA_FLOOR[code]
        assert formula_count >= floor, (
            f"{code} 公式数 {formula_count} < 下限 {floor}（模板变了？现算值可能需更新基线）"
        )


# ═══════════════════════════════════════════════════════════════════════════
#  P2：13 张全命中裸 IF
# ═══════════════════════════════════════════════════════════════════════════


class TestP2AllSheetsHaveBareIF:
    """P2：每张审定表都命中裸 IF（≥ 1）—— G 循环审定表的结构特征。"""

    def test_total_bare_if_above_floor(self, geometry) -> None:
        total = sum(g[3] for g in geometry.values())
        assert total >= _TOTAL_BARE_IF_FLOOR, (
            f"13 张审定表裸 IF 总数 {total} < 下限 {_TOTAL_BARE_IF_FLOOR}"
        )

    @pytest.mark.parametrize("code", sorted(ADJUDICATION_SHEETS))
    def test_each_sheet_has_at_least_one_bare_if(self, code: str, geometry) -> None:
        bare_if = geometry[code][3]
        assert bare_if >= 1, (
            f"{code} 裸 IF 数 = 0（该审定表的结构特征丢失——检查模板是否被清洗了）"
        )


# ═══════════════════════════════════════════════════════════════════════════
#  P3：13 张全存在于模板目录（前置完备性）
# ═══════════════════════════════════════════════════════════════════════════


class TestP3TemplateCompleteness:
    """所有 13 张审定表的模板和 sheet 都存在。"""

    @pytest.mark.parametrize("code", sorted(ADJUDICATION_SHEETS))
    def test_template_workbook_exists(self, code: str) -> None:
        wb_name, _ = ADJUDICATION_SHEETS[code]
        fp = TPL_G / wb_name
        assert fp.exists(), f"{code} 的模板不存在：{fp}"

    @pytest.mark.parametrize("code", sorted(ADJUDICATION_SHEETS))
    def test_sheet_exists_in_workbook(self, code: str) -> None:
        wb_name, sheet_name = ADJUDICATION_SHEETS[code]
        wb = openpyxl.load_workbook(TPL_G / wb_name, read_only=True)
        assert sheet_name in wb.sheetnames, (
            f"{code}: 模板 {wb_name} 里没有 {sheet_name!r}"
        )
        wb.close()

    def test_exactly_13_adjudication_sheets(self) -> None:
        """G7 无审定表（G7 循环走列结构对齐独立 spec），G0 不算，恰好 13 张。"""
        assert len(ADJUDICATION_SHEETS) == 13


# ═══════════════════════════════════════════════════════════════════════════
#  P4：阻塞项现算断言（引擎缺口钉死）
# ═══════════════════════════════════════════════════════════════════════════


class TestP4EngineNowExists:
    """✅ 引擎已就位断言——payload 生成器已实现（2026-10-07）。

    交叉引用 `test_deferred_imports_resolve.py::test_adjudication_sheet_spec_type_itself_does_exist`
    的同口径断言（那边也已翻面为「引擎已就位」）。
    """

    def test_payload_generator_exists(self) -> None:
        """契约 payload 生成器 `static_sheet_payload_for_adjudication` 已存在。"""
        from app.services.workpaper_sync import phase5_adjudication_sheet as A

        assert hasattr(A, "static_sheet_payload_for_adjudication"), (
            "payload 生成器消失了 —— 请恢复实现"
        )

    def test_payload_generator_returns_valid_dict(self) -> None:
        """payload 生成器对 D1-1 spec 返回合法的 sheet payload。"""
        from app.services.workpaper_sync.phase5_adjudication_sheet import (
            static_sheet_payload_for_adjudication,
        )
        from app.services.workpaper_sync.phase5_d1_01_adjudication import SPEC_D101

        result = static_sheet_payload_for_adjudication(SPEC_D101)
        assert isinstance(result, dict)
        assert "sheet_key" in result
        assert "excel_name" in result
        assert "tables" in result
        assert len(result["tables"]) == len(SPEC_D101.sections)

    def test_wired_providers_return_spec(self) -> None:
        """已接入审定表的 G provider 返回非 None。"""
        import importlib

        _WIRED = [
            "phase5_g1_trading_financial_assets",
            "phase5_g2_interest_receivable",
            "phase5_g3_dividend_receivable",
            "phase5_g4_bond_investment",
            "phase5_g5_long_term_receivable",
            "phase5_g6_other_bond",
            "phase5_g8_other_equity",
            "phase5_g9_other_noncurrent",
            "phase5_g10_trading_liabilities",
            "phase5_g11_investment_income",
            "phase5_g12_net_hedge_gains",
            "phase5_g13_fair_value_changes",
            "phase5_g14_credit_impairment",
        ]
        for mod_name in _WIRED:
            mod = importlib.import_module(f"app.services.workpaper_sync.{mod_name}")
            result = mod.adjudication_spec()
            assert result is not None, (
                f"{mod_name}.adjudication_spec() 返回 None —— "
                "灰度开关被关了？"
            )

    def test_pending_providers_still_return_none(self) -> None:
        """尚未接入审定表的 G provider 仍返回 None（全部已接入 ⇒ 空清单）。"""
        import importlib

        _PENDING: list[str] = []
        for mod_name in _PENDING:
            mod = importlib.import_module(f"app.services.workpaper_sync.{mod_name}")
            result = mod.adjudication_spec()
            assert result is None, (
                f"{mod_name}.adjudication_spec() 返回了非 None —— "
                "灰度开关翻了？请同步更新此处清单"
            )


# ═══════════════════════════════════════════════════════════════════════════
#  P5：G5-1!B35 越界缺陷登记（GC-9 / G5-H4 交棒）
# ═══════════════════════════════════════════════════════════════════════════


class TestP5G51OutOfBoundDefect:
    """G5-1!B35 的 `=B9-B225` 越界：B225 超出 max_row ⇒ 恒空 ⇒ B35 恒等于 B9。"""

    def test_b35_formula_references_beyond_max_row(self) -> None:
        """B35 公式引用 B225 而 max_row 远小于 225。"""
        wb = openpyxl.load_workbook(
            TPL_G / "G5 长期应收款.xlsx", read_only=True, data_only=False
        )
        ws = wb["审定表G5-1"]
        b35 = ws.cell(row=35, column=2).value
        assert b35 is not None and isinstance(b35, str), "B35 应是公式"
        assert "B225" in b35.upper(), (
            f"B35 公式不再引用 B225（公式={b35!r}）—— 越界已修？请翻面此判据"
        )
        assert ws.max_row < 225, (
            f"max_row={ws.max_row} ≥ 225 —— 模板扩行了？越界缺陷可能已不成立"
        )
        wb.close()
