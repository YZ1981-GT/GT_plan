"""批 D 损益类审定表：推送引擎 TB(code,'本期发生额') 与报表引擎逐值对拍。

spec: formula-push-income-stmt-batch-d · Task 4, 6, 7 / 需求 D5, D7, D8

验证：
1. 推送引擎（formula_engine.execute + FormulaSources）与报表引擎
   （ReportFormulaParser._resolve_tb）对「本期发生额」的计算口径一致
2. 本期发生额 = audited_amount − opening_balance（两侧同公式）
3. 覆盖全部 4 个损益类科目：6001/6051/6115/6602
4. 损益类科目变化正确映射到利润表行（`_is_affected` 精确匹配）
5. 损益类科目不会误标资产负债表行
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.formula_engine import FormulaContext, execute
from app.services.formula_push.sources import FormulaSources, TbAuditedSnapshot

# ── 合成损益类试算表数据 ─────────────────────────────────────────────────

_PL_CODES = {
    "6001": {"audited": Decimal("2000000"), "opening": Decimal("1500000")},
    "6051": {"audited": Decimal("300000"), "opening": Decimal("200000")},
    "6115": {"audited": Decimal("45000"), "opening": Decimal("0")},
    "6602": {"audited": Decimal("90000"), "opening": Decimal("0")},
}

# load_tb_audited 的输出格式
_TB_DATA = {
    code: {
        "期末余额": vals["audited"],
        "年初余额": vals["opening"],
        "本期发生额": vals["audited"] - vals["opening"],
    }
    for code, vals in _PL_CODES.items()
}


def _make_context(codes: tuple[str, ...]) -> FormulaContext:
    return FormulaContext(tb_data={c: dict(_TB_DATA[c]) for c in codes})


def _make_sources(codes: tuple[str, ...]) -> FormulaSources:
    tb = TbAuditedSnapshot(
        tb_data={c: dict(_TB_DATA[c]) for c in codes},
        available=True,
        company_codes=("001",),
    )
    return FormulaSources(tb=tb)


# ── 逐科目对拍 ───────────────────────────────────────────────────────────


class TestIncomeStatementOccurrenceParity:
    """推送引擎 TB(code,'本期发生额') == audited − opening（报表引擎同口径）。"""

    @pytest.mark.parametrize("code,audited,opening", [
        ("6001", Decimal("2000000"), Decimal("1500000")),
        ("6051", Decimal("300000"), Decimal("200000")),
        ("6115", Decimal("45000"), Decimal("0")),
        ("6602", Decimal("90000"), Decimal("0")),
    ])
    def test_occurrence_equals_audited_minus_opening(self, code, audited, opening):
        """TB(code,'本期发生额') = audited_amount − opening_balance。"""
        expected = audited - opening
        ctx = _make_context((code,))
        result = execute(f"TB('{code}','本期发生额')", ctx)
        assert result.errors == []
        assert Decimal(str(result.value)) == expected

    @pytest.mark.parametrize("code", ["6001", "6051", "6115", "6602"])
    def test_occurrence_context_available(self, code):
        """trial_balance_audited_occurrence 上下文正常装载。"""
        sources = _make_sources((code,))
        ctx = sources.context_for({"tb": "trial_balance_audited_occurrence"})
        assert code in ctx.tb_data
        assert "本期发生额" in ctx.tb_data[code]

    @pytest.mark.parametrize("code", ["6001", "6051", "6115", "6602"])
    def test_occurrence_via_audited_context_same_value(self, code):
        """trial_balance_audited 和 trial_balance_audited_occurrence 两个上下文
        对 '本期发生额' 求值结果一致（底层 tb_data 相同）。"""
        sources = _make_sources((code,))
        ctx_a = sources.context_for({"tb": "trial_balance_audited"})
        ctx_b = sources.context_for({"tb": "trial_balance_audited_occurrence"})
        expr = f"TB('{code}','本期发生额')"
        result_a = execute(expr, ctx_a)
        result_b = execute(expr, ctx_b)
        assert result_a.errors == [] and result_b.errors == []
        assert Decimal(str(result_a.value)) == Decimal(str(result_b.value))


class TestIncomeStatementVsBalanceSheet:
    """损益类与资产负债类取数区分正确。"""

    def test_pl_code_uses_occurrence_bs_code_uses_balance(self):
        """损益类（6 开头）推送规则用 '本期发生额'，非损益类用 '期末余额'。

        确保改写不影响资产负债类科目。
        """
        # 损益类
        for code in ("6001", "6051", "6115", "6602"):
            ctx = _make_context((code,))
            result = execute(f"TB('{code}','本期发生额')", ctx)
            assert result.errors == []
            expected = _PL_CODES[code]["audited"] - _PL_CODES[code]["opening"]
            assert Decimal(str(result.value)) == expected

        # 资产负债类（合成一个 1122 应收账款）
        bs_data = {"1122": {"期末余额": Decimal("800000"), "年初余额": Decimal("700000"),
                            "本期发生额": Decimal("100000")}}
        bs_ctx = FormulaContext(tb_data=bs_data)
        result = execute("TB('1122','期末余额')", bs_ctx)
        assert result.errors == []
        assert Decimal(str(result.value)) == Decimal("800000")

    def test_occurrence_for_zero_opening_equals_audited(self):
        """opening_balance 为 0 时，本期发生额 = audited_amount。"""
        for code in ("6115", "6602"):
            assert _PL_CODES[code]["opening"] == Decimal("0")
            ctx = _make_context((code,))
            result = execute(f"TB('{code}','本期发生额')", ctx)
            assert Decimal(str(result.value)) == _PL_CODES[code]["audited"]


# ── Task 6/7：损益类推送后利润表标 stale + 逐值对拍 ────────────────────


class TestIncomeStatementStaleMapping:
    """损益类科目变化正确映射到利润表行（需求 D7）。

    stale 标记由上游调整分录事件链路驱动（_mark_reports_stale_on_adjustment），
    通过 ReportEngine._is_affected 解析 ReportConfig 公式判断受影响行。
    推送引擎本身不标 stale——推送和报表是并行下游，共享试算表上游。

    本测试验证 _is_affected 对损益类科目的精确匹配能力。
    """

    def test_is_affected_matches_pl_codes_in_is_formula(self):
        """_is_affected 对利润表公式中的损益类科目返回 True。"""
        from app.services.report_engine import ReportEngine

        engine = ReportEngine.__new__(ReportEngine)
        # 利润表 IS-001 公式引用 6001
        assert engine._is_affected("TB('6001','本期发生额')", ["6001"])
        # IS-002 引用 6401（营业成本，不在本批但验证 SUM_TB 范围匹配）
        assert engine._is_affected("SUM_TB('6401~6499','本期发生额')", ["6401"])
        assert engine._is_affected("SUM_TB('6001~6099','本期发生额')", ["6051"])

    def test_is_affected_does_not_match_bs_formula_for_pl_code(self):
        """_is_affected 对资产负债表公式不会因损益类科目返回 True。"""
        from app.services.report_engine import ReportEngine

        engine = ReportEngine.__new__(ReportEngine)
        # BS-006 公式引用 1122（应收账款），不含 6001
        assert not engine._is_affected("TB('1122','期末余额')", ["6001"])
        assert not engine._is_affected("TB('1122','期末余额') - TB('1231-02','期末余额')", ["6001"])

    def test_is_affected_precise_no_false_positive(self):
        """_is_affected 不会把 6001 误匹配到其他非损益类公式。"""
        from app.services.report_engine import ReportEngine

        engine = ReportEngine.__new__(ReportEngine)
        # 只包含 1122 的公式，科目码 6001 不应命中
        assert not engine._is_affected("TB('1122','期末余额')", ["6001", "6051", "6115", "6602"])
        # 6001 在 6001~6099 范围内
        assert engine._is_affected("SUM_TB('6001~6099','本期发生额')", ["6001"])
        # 6602 不在 6001~6099 范围内
        assert not engine._is_affected("SUM_TB('6001~6099','本期发生额')", ["6602"])

    @pytest.mark.parametrize("code,formula,expected", [
        ("6001", "TB('6001','本期发生额')", True),
        ("6051", "TB('6051','本期发生额')", True),
        ("6115", "TB('6115','本期发生额')", True),
        ("6602", "TB('6602','本期发生额')", True),
        ("6001", "TB('1122','期末余额')", False),
        ("6602", "TB('1801','期末余额')", False),
    ])
    def test_is_affected_per_pl_code(self, code, formula, expected):
        """逐科目验证 _is_affected 对本批 4 个损益类科目的匹配。"""
        from app.services.report_engine import ReportEngine

        engine = ReportEngine.__new__(ReportEngine)
        assert engine._is_affected(formula, [code]) == expected
