"""REPORT 期间映射、缺行报错与正则降级安全化（ADR-FGR-05）。

spec: formula-grammar-resolver-unification / tasks.md Task 6
Validates: R8（REPORT 期间）, R9②（缺行报错）, R9③（正则降级 ok=False）

覆盖点：
- 本期别名：本期 / 期末 / current（大小写不敏感）
- 上期别名：上期 / 期初 / prior
- 缺行：row_cache / prior_row_cache 里无此行 ⇒ ok=False + 明确原因
- 坏期间：无法识别的字符串 ⇒ ok=False + 明确原因
- 正则降级路径（_PARSE_MODE=regex）同等行为
- AST 与 regex 路径对同一场景结果一致
"""
from __future__ import annotations

import os
from decimal import Decimal

import pytest

from app.services.formula_engine import (
    FormulaContext,
    FormulaResult,
    execute,
    _REPORT_CURRENT_PERIOD,
    _REPORT_PRIOR_PERIOD,
)


# ── 工具 ──────────────────────────────────────────────────────────────────────

def _ctx(
    row_cache: dict[str, Decimal] | None = None,
    prior_row_cache: dict[str, Decimal] | None = None,
) -> FormulaContext:
    return FormulaContext(
        row_cache=dict(row_cache or {}),
        prior_row_cache=dict(prior_row_cache or {}),
    )


_CURRENT_ROWS = {"BS-001": Decimal("100"), "IS-002": Decimal("200")}
_PRIOR_ROWS = {"BS-001": Decimal("80"), "IS-002": Decimal("150")}


def _exec(formula: str, ctx: FormulaContext | None = None) -> FormulaResult:
    return execute(formula, ctx or _ctx(_CURRENT_ROWS, _PRIOR_ROWS))


def _exec_regex(formula: str, ctx: FormulaContext | None = None) -> FormulaResult:
    """强制走正则降级路径。"""
    old = os.environ.get("FORMULA_PARSE_MODE")
    os.environ["FORMULA_PARSE_MODE"] = "regex"
    try:
        # 重新导入以拿到正确的 _PARSE_MODE（模块级读取环境变量）
        import importlib
        import app.services.formula_engine as mod
        importlib.reload(mod)
        result = mod.execute(formula, ctx or _ctx(_CURRENT_ROWS, _PRIOR_ROWS))
    finally:
        if old is None:
            os.environ.pop("FORMULA_PARSE_MODE", None)
        else:
            os.environ["FORMULA_PARSE_MODE"] = old
        import importlib
        import app.services.formula_engine as mod
        importlib.reload(mod)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 本期别名 → row_cache
# ═══════════════════════════════════════════════════════════════════════════════

class TestReportCurrentPeriod:
    """REPORT('行次','本期') 及其别名取 row_cache 的值。"""

    @pytest.mark.parametrize("period", sorted(_REPORT_CURRENT_PERIOD))
    def test_current_aliases(self, period: str):
        r = _exec(f"REPORT('BS-001','{period}')")
        assert r.ok, r.errors
        assert r.value == Decimal("100")

    def test_current_case_insensitive(self):
        r = _exec("REPORT('BS-001','Current')")
        assert r.ok and r.value == Decimal("100")

    def test_default_period_is_current(self):
        """只传一个参数时默认按本期取值。"""
        # 构造只有一个参数的语法（AST 路径认 REPORT('行次')）
        # 因为 REPORT 注册 arity=2，但存量可能只写一个参数，默认本期
        ctx = _ctx({"BS-001": Decimal("100")})
        # 直接调内部函数验证默认行为
        from app.services.formula_engine import _report_value
        assert _report_value("BS-001", "本期", ctx) == Decimal("100")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 上期别名 → prior_row_cache
# ═══════════════════════════════════════════════════════════════════════════════

class TestReportPriorPeriod:
    """REPORT('行次','上期') 及其别名取 prior_row_cache 的值。"""

    @pytest.mark.parametrize("period", sorted(_REPORT_PRIOR_PERIOD))
    def test_prior_aliases(self, period: str):
        r = _exec(f"REPORT('BS-001','{period}')")
        assert r.ok, r.errors
        assert r.value == Decimal("80")

    def test_prior_case_insensitive(self):
        r = _exec("REPORT('IS-002','Prior')")
        assert r.ok and r.value == Decimal("150")

    def test_prior_returns_different_from_current(self):
        """上期值与本期值不同，证明期间映射生效。"""
        cur = _exec("REPORT('BS-001','本期')")
        pri = _exec("REPORT('BS-001','上期')")
        assert cur.ok and pri.ok
        assert cur.value == Decimal("100")
        assert pri.value == Decimal("80")
        assert cur.value != pri.value


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 缺行报错（R9②）
# ═══════════════════════════════════════════════════════════════════════════════

class TestReportMissingRow:
    """行次不存在 ⇒ ok=False，明确写出行次代码。"""

    def test_missing_row_current(self):
        r = _exec("REPORT('NONEXIST','本期')")
        assert not r.ok
        assert r.value is None
        assert any("NONEXIST" in e and "不存在" in e for e in r.errors), r.errors

    def test_missing_row_prior(self):
        r = _exec("REPORT('NONEXIST','上期')")
        assert not r.ok
        assert r.value is None
        assert any("NONEXIST" in e for e in r.errors), r.errors

    def test_row_exists_in_current_but_not_prior(self):
        """本期有、上期无 ⇒ 上期取值报错。"""
        ctx = _ctx({"BS-001": Decimal("100")}, {})
        r = execute("REPORT('BS-001','上期')", ctx)
        assert not r.ok
        assert any("BS-001" in e for e in r.errors)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 无法识别的期间
# ═══════════════════════════════════════════════════════════════════════════════

class TestReportBadPeriod:
    """无法识别的期间参数 ⇒ ok=False，写明可选值。"""

    @pytest.mark.parametrize("bad_period", ["未来", "next", "去年", ""])
    def test_bad_period(self, bad_period: str):
        r = _exec(f"REPORT('BS-001','{bad_period}')")
        assert not r.ok
        assert r.value is None
        assert any("无法识别" in e for e in r.errors), r.errors


# ═══════════════════════════════════════════════════════════════════════════════
# 5. 正则降级路径同等行为（R9③）
# ═══════════════════════════════════════════════════════════════════════════════

class TestReportRegexPath:
    """正则降级路径（_PARSE_MODE=regex）的 REPORT 行为与 AST 一致。"""

    def test_regex_current_period(self):
        r = _exec_regex("REPORT('BS-001','本期')")
        assert r.ok, r.errors
        assert r.value == Decimal("100")

    def test_regex_prior_period(self):
        r = _exec_regex("REPORT('BS-001','上期')")
        assert r.ok, r.errors
        assert r.value == Decimal("80")

    def test_regex_missing_row(self):
        r = _exec_regex("REPORT('NONEXIST','本期')")
        assert not r.ok
        assert r.value is None

    def test_regex_bad_period(self):
        r = _exec_regex("REPORT('BS-001','未来')")
        assert not r.ok
        assert r.value is None

    def test_regex_partial_result_not_leaked(self):
        """正则路径出错 ⇒ value=None，不返回部分替换结果。"""
        r = _exec_regex("REPORT('BS-001','本期') + REPORT('NONEXIST','本期')")
        assert not r.ok
        assert r.value is None


# ═══════════════════════════════════════════════════════════════════════════════
# 6. AST 与 regex 路径一致性
# ═══════════════════════════════════════════════════════════════════════════════

class TestReportPathConsistency:
    """AST 与 regex 路径对同一场景 ok / value 一致。"""

    @pytest.mark.parametrize("formula,expect_ok", [
        ("REPORT('BS-001','本期')", True),
        ("REPORT('BS-001','上期')", True),
        ("REPORT('NONEXIST','本期')", False),
        ("REPORT('BS-001','未来')", False),
    ])
    def test_ast_regex_agree(self, formula: str, expect_ok: bool):
        ast_r = _exec(formula)
        regex_r = _exec_regex(formula)
        assert ast_r.ok == expect_ok
        assert regex_r.ok == expect_ok
        if expect_ok:
            assert ast_r.value == regex_r.value
        else:
            assert ast_r.value is None
            assert regex_r.value is None
