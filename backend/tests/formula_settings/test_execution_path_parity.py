"""执行路径一致性守卫（spec formula-execution-path-convergence Step 3）。

三条路径对同一个纯 TB/ROW/ADJ 报表公式应给出同一结果：
A. report_engine.evaluate_formula_result（L2 regex 预替换 → L1）
B. formula_preloader.preload → formula_engine.execute（统一预载 → L1）
C. formula_engine.FormulaContext.from_simple_map → execute（公式管理页）

守卫使用合成 FormulaContext 避免 DB 依赖，验证 L1 内核求值的一致性。
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.formula_engine import FormulaContext, execute


# ── 合成数据 ──────────────────────────────────────────────────────────────────

_TB = {"1001": {"期末余额": Decimal("100"), "审定数": Decimal("100"), "未审数": Decimal("100"),
                "年初余额": Decimal("80"), "AJE调整": Decimal("5"), "RJE调整": Decimal("2")},
       "1002": {"期末余额": Decimal("200"), "审定数": Decimal("200"), "未审数": Decimal("200"),
                "年初余额": Decimal("150")}}

_ADJ = {"1001": {"aje_net": Decimal("5"), "rje_net": Decimal("2")}}

_ROW_CACHE = {"BS-001": Decimal("100"), "BS-002": Decimal("300")}


def _ctx(**overrides) -> FormulaContext:
    return FormulaContext(
        tb_data=_TB,
        row_cache=dict(_ROW_CACHE),
        adj_data=_ADJ,
        **overrides,
    )


# ── 一致性测试 ────────────────────────────────────────────────────────────────

class TestExecutionPathParity:
    """三条路径对同一公式给出同一结果。"""

    @pytest.mark.parametrize("formula,expected", [
        ("TB('1001','期末余额')", Decimal("100")),
        ("TB('1001','期末余额') + TB('1002','期末余额')", Decimal("300")),
        ("ROW('BS-001')", Decimal("100")),
        ("ROW('BS-001') + ROW('BS-002')", Decimal("400")),
        ("TB('1001','期末余额') + ROW('BS-001')", Decimal("200")),
        ("ADJ('1001','aje_net')", Decimal("5")),
        ("ABS(TB('1001','期末余额') - TB('1002','期末余额'))", Decimal("100")),
        ("ROUND(TB('1001','期末余额') / 3, 2)", Decimal("33.33")),
        ("IF(TB('1001','期末余额'), ROW('BS-001'), 0)", Decimal("100")),
    ], ids=lambda x: str(x)[:40])
    def test_l1_kernel_parity(self, formula, expected):
        """L1 内核 execute 对给定 ctx 应返回 expected 值。

        三条路径最终都委托 L1 execute()，只要 ctx 一致，结果必须一致。
        本守卫直接验证 L1 层。
        """
        ctx = _ctx()
        result = execute(formula, ctx)
        assert result.value == expected, f"{formula} → {result.value}, expected {expected}"
        assert result.ok

    def test_ledger_in_ctx(self):
        """preloader 路径特有：LEDGER 从 ctx.ledger_data 取值。"""
        ctx = _ctx(ledger_data={"1001:借:全年": Decimal("999")})
        result = execute("LEDGER('1001','借','全年')", ctx)
        assert result.value == Decimal("999")

    def test_tb_aux_in_ctx(self):
        """preloader 路径特有：TB_AUX 从 ctx.tb_aux_data 取值。"""
        ctx = _ctx(tb_aux_data={"1121:客户:期末余额": Decimal("888")})
        result = execute("TB_AUX('1121','客户','期末余额')", ctx)
        assert result.value == Decimal("888")

    def test_from_simple_map_parity(self):
        """路径 C（from_simple_map）构建的 ctx 与手工 ctx 对同一公式结果一致。"""
        simple_ctx = FormulaContext.from_simple_map(
            {"1001": Decimal("100"), "1002": Decimal("200")},
            row_cache={"BS-001": Decimal("100")},
            adj_map={"1001": {"aje_net": Decimal("5"), "rje_net": Decimal("2")}},
        )
        r1 = execute("TB('1001','期末余额') + ROW('BS-001')", simple_ctx)
        r2 = execute("TB('1001','期末余额') + ROW('BS-001')", _ctx())
        assert r1.value == r2.value == Decimal("200")


class TestFormulaBlockedDetection:
    """三条路径的 blocked 检测一致（都走 L1 的 _is_blocked_formula）。"""

    def test_known_function_not_blocked(self):
        # LEDGER 带上预载数据：预载层没取的序时账键报错不代 0（formula-fetch-followup 6.5），与「是否拦截」无关
        ctx = _ctx(ledger_data={"1001:借:全年": Decimal("1")})
        for fn in ["TB('1001','期末余额')", "ROW('BS-001')", "LEDGER('1001','借','全年')",
                    "ABS(1)", "PLACEHOLDER()"]:
            result = execute(fn, ctx)
            assert not result.blocked and result.ok, f"{fn} should not be blocked"
        unloaded = execute("LEDGER('9999','借','全年')", _ctx())
        assert not unloaded.blocked and not unloaded.ok, "未预载的序时账键应报错（不是拦截，也不是 0）"

    def test_unknown_function_blocked(self):
        ctx = _ctx()
        result = execute("EVIL('1001')", ctx)
        assert result.blocked, "unknown function should be blocked"
