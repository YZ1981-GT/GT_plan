# -*- coding: utf-8 -*-
"""D4-9 Task 9 守卫：用户公式运行时保护区 + 上下游血缘（行为级）。

spec: d4-9-customer-structure-bidirectional-writeback / Task 9
Requirements: 5.3, 5.4, 5.5, 5.6

用户公式的存储/ACNR 校验/写 xlsx 由平台级 WpFormulaService 承担（Req 5.1/5.2，不在此重测）。
本文件验证 D4-9 特有的运行时保护集与血缘。
"""

from __future__ import annotations

import pytest

from app.services.workpaper_sync import phase5_d4_customer_structure as M


@pytest.fixture(scope="module")
def contract():
    return M.assert_contract_file_matches_source()


class TestProtectedCells:
    def test_contract_mask_covers_ratio_columns(self, contract) -> None:
        cells = M.contract_protected_cells(contract)
        # 本期占比 D13-D22 / F13-F22。
        for r in range(13, 23):
            assert f"D{r}" in cells
            assert f"F{r}" in cells
        # 上期占比 D27-D36 / F27-F36。
        for r in range(27, 37):
            assert f"D{r}" in cells
            assert f"F{r}" in cells

    def test_footer_total_cells_protected(self, contract) -> None:
        prot = M.runtime_protected_cells(contract)
        assert "C23" in prot and "E23" in prot  # 本期合计
        assert "C37" in prot and "E37" in prot  # 上期合计

    def test_user_formula_cell_joins_protected_set(self, contract) -> None:
        # 审计师给 C24（本期销售总额）设了用户公式 ⇒ 必须纳入保护集。
        prot = M.runtime_protected_cells(contract, user_formula_cells=["C24"])
        assert "C24" in prot
        assert M.is_cell_protected("C24", contract, user_formula_cells=["C24"])
        # 未设用户公式时 C24 不在保护集（可编辑标量）。
        assert not M.is_cell_protected("C24", contract, user_formula_cells=[])

    def test_user_formula_cell_normalization(self, contract) -> None:
        # 带 $ 的绝对引用与小写都应归一化命中。
        assert M.is_cell_protected("$c$24", contract, user_formula_cells=["$C$24"])

    def test_editable_business_cell_not_protected(self, contract) -> None:
        # 客户金额 C13 是可编辑业务列，无用户公式时不受保护。
        assert not M.is_cell_protected("C13", contract, user_formula_cells=[])
        # 但一旦设了用户公式即受保护（Req 5.6）。
        assert M.is_cell_protected("C13", contract, user_formula_cells=["C13"])


class TestLineage:
    def test_ratio_lineage_references_total(self) -> None:
        lin = M.formula_lineage()
        cur_ratio = lin["ratio"]["current"]
        d13 = next(x for x in cur_ratio if x["target"] == "D13")
        assert "C13" in d13["refs"] and "C24" in d13["refs"]
        pri_ratio = lin["ratio"]["prior"]
        d27 = next(x for x in pri_ratio if x["target"] == "D27")
        assert "C38" in d27["refs"]

    def test_footer_lineage(self) -> None:
        lin = M.formula_lineage()
        c23 = next(x for x in lin["footer"] if x["target"] == "C23")
        assert c23["expr"] == "SUM(C13:C22)"

    def test_totals_source_is_d4_7(self) -> None:
        lin = M.formula_lineage()
        srcs = {x["target"]: x["source"] for x in lin["totals_source"]}
        assert srcs["C24"] == "D4-7!D26"
        assert srcs["C38"] == "D4-7!L26"
