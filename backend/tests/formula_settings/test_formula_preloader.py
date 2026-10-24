"""统一预载层测试（spec formula-execution-path-convergence Phase 1 · Task 8）。

验证：
1. _scan_refs 正确提取各类数据源引用
2. FormulaContext 新字段存在且 L1 handler 能从中取值
3. preload → execute 端到端（合成数据）
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.formula_engine import FormulaContext, execute
from app.services.formula_preloader import _scan_refs


class TestScanRefs:
    """_scan_refs 正确提取各类数据源引用。"""

    def test_tb(self):
        refs = _scan_refs(["TB('1001','期末余额')"])
        assert "1001" in refs["tb_codes"]

    def test_sum_tb(self):
        refs = _scan_refs(["SUM_TB('1001~1099','期末余额')"])
        assert "1001~1099" in refs["tb_codes"]

    def test_adj(self):
        refs = _scan_refs(["ADJ('1001','aje_net')"])
        assert "1001" in refs["adj_codes"]

    def test_ledger(self):
        refs = _scan_refs(["LEDGER('1001','借','全年')"])
        assert ("1001", "借", "全年") in refs["ledger_specs"]

    def test_count_ledger(self):
        """COUNT_LEDGER('科目','范围') 单独扫成（科目, 范围）。原先混进 LEDGER 扫：第二参被当成方向、
        期间恒按全年 ⇒ 非全年的笔数恒取不到（formula-fetch-followup 6.5 改）。"""
        refs = _scan_refs(["COUNT_LEDGER('1001','1-3月')", "COUNT_LEDGER('1002')"])
        assert refs["ledger_count_specs"] == {("1001", "1-3月"), ("1002", "全年")}
        assert refs["ledger_specs"] == set()

    def test_ledger_detail(self):
        refs = _scan_refs(["LEDGER_DETAIL('6001','12月','>=100000')", "LEDGER_DETAIL('6002')"])
        assert refs["ledger_detail_specs"] == {("6001", "12月", ">=100000"), ("6002", "全年", "*")}

    def test_wp(self):
        refs = _scan_refs(["WP('D1','审定表D1-1','合计')"])
        assert ("D1", "审定表D1-1", "合计") in refs["wp_refs"]

    def test_note(self):
        refs = _scan_refs(["NOTE('五、1','应收账款','value')"])
        assert ("五、1", "应收账款", "value") in refs["note_refs"]

    def test_prev(self):
        refs = _scan_refs(["PREV('1001','期末余额')"])
        assert "1001" in refs["prev_codes"]

    def test_tb_aux(self):
        refs = _scan_refs(["TB_AUX('1121','客户','期末余额')"])
        assert ("1121", "客户", "期末余额") in refs["tb_aux_specs"]

    def test_multiple_formulas(self):
        refs = _scan_refs([
            "TB('1001','期末余额')+TB('1002','期末余额')",
            "LEDGER('1001','借','全年')+NOTE('五、1','金额')",
        ])
        assert refs["tb_codes"] == {"1001", "1002"}
        assert len(refs["ledger_specs"]) == 1
        assert len(refs["note_refs"]) == 1

    def test_empty_formulas(self):
        refs = _scan_refs(["", None, "   "])
        assert all(not v for v in refs.values())


class TestL1HandlersWithContext:
    """L1 handler 从 FormulaContext 新字段取值。"""

    def test_ledger_handler(self):
        ctx = FormulaContext(ledger_data={"1001:借:全年": Decimal("12345.67")})
        result = execute("LEDGER('1001','借','全年')", ctx)
        assert result.value == Decimal("12345.67")
        assert result.ok

    def test_ledger_missing_key(self):
        """预载层没取的键报错、不代 0（原先返 0 且 ok，与「本期确实没有发生额」分不清；formula-fetch-followup 6.5 改）。"""
        result = execute("LEDGER('9999','借','全年')", FormulaContext())
        assert not result.ok
        assert "LEDGER('9999','借','全年')：未取数" in result.errors[0]

    def test_ledger_detail_handler(self):
        ctx = FormulaContext(ledger_detail_data={
            "6001:12月:>=100000": [{"voucher_no": "V001"}, {"voucher_no": "V002"}]
        })
        result = execute("LEDGER_DETAIL('6001','12月','>=100000')", ctx)
        assert result.value == Decimal("2")  # 2 rows

    def test_tb_aux_handler(self):
        ctx = FormulaContext(tb_aux_data={"1121:客户:期末余额": Decimal("999.99")})
        result = execute("TB_AUX('1121','客户','期末余额')", ctx)
        assert result.value == Decimal("999.99")

    def test_count_ledger_handler(self):
        ctx = FormulaContext(ledger_count_data={"1001:全年": 42})
        result = execute("COUNT_LEDGER('1001','全年')", ctx)
        assert result.value == Decimal("42")

    def test_combined_formula(self):
        """混合公式：TB + LEDGER 在同一表达式。"""
        ctx = FormulaContext(
            tb_data={"1001": {"期末余额": Decimal("100")}},
            ledger_data={"1001:借:全年": Decimal("50")},
        )
        result = execute("TB('1001','期末余额') + LEDGER('1001','借','全年')", ctx)
        assert result.value == Decimal("150")
        assert result.ok

    def test_placeholder_still_works(self):
        ctx = FormulaContext()
        result = execute("PLACEHOLDER()", ctx)
        assert result.value == Decimal("0")
        assert result.ok
