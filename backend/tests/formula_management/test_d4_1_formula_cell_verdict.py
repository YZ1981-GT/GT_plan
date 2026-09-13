# -*- coding: utf-8 -*-
"""D4-1 公式单元格裁决守卫（Task 3.2 / Req 3.2, 3.4, 2.2, 1.4）。

行为级断言：验证 HTML/OO 共用裁决层的失败闭环（不转零）、来源 tooltip 口径单一、
状态到裁决的映射。每类含变异反向自检（把关键判据取反必须打红）。
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.formula_management.d4_formula_cell_verdict import (
    FormulaCellVerdict,
    build_source_tooltip,
    verdict_from_effective,
    verdict_from_evaluation,
)
from app.services.formula_management.effective_formula import EffectiveFormula


def _eff(state: str, *, expression="=SUM(1,2)", source="preset:seed", reason="", preset_expression=None):
    return EffectiveFormula(
        key=f"wp∷D4∷r∷f∷",
        state=state,  # type: ignore[arg-type]
        expression=expression,
        source=source,
        formula_type="auto_calc",
        refs=[],
        preset_expression=preset_expression,
        reason=reason,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Req 3.4：失败/损坏/blocked/stale/pending 一律 value=None、applied=False（不转零）
# ─────────────────────────────────────────────────────────────────────────────
class TestNoZeroCoercion:
    def test_eval_failure_does_not_coerce_to_zero(self):
        """求值器返回 (Decimal('0'), errors) 时，裁决必须丢弃那个 0。"""
        eff = _eff("preset")
        v = verdict_from_evaluation(eff, value=Decimal("0"), errors=["TB(6001): 无此科目"])
        assert v.outcome == "failed"
        assert v.value is None, "失败时 value 必须是 None，绝不是 0"
        assert v.applied is False

    def test_eval_failure_with_nonzero_stale_value_also_discarded(self):
        eff = _eff("custom", source="custom")
        v = verdict_from_evaluation(eff, value=Decimal("123.45"), errors=["boom"])
        assert v.outcome == "failed"
        assert v.value is None

    def test_dependency_failure_short_circuits(self):
        eff = _eff("preset")
        v = verdict_from_evaluation(eff, value=Decimal("10"), errors=[], dependency_failed=True)
        assert v.outcome == "failed"
        assert v.value is None
        assert v.applied is False

    def test_corrupt_never_evaluates(self):
        eff = _eff("corrupt", expression=None, reason="表达式含 eval")
        v = verdict_from_evaluation(eff, value=Decimal("999"), errors=[])
        assert v.outcome == "failed"
        assert v.value is None

    def test_blocked_readonly_no_value(self):
        eff = _eff("blocked", reason="无权编辑")
        v = verdict_from_evaluation(eff, value=Decimal("5"), errors=[])
        assert v.outcome == "blocked"
        assert v.value is None
        assert v.applied is False

    def test_preset_missing_is_pending(self):
        eff = _eff("preset_missing", expression=None, source="none")
        v = verdict_from_evaluation(eff, value=None, errors=[])
        assert v.outcome == "pending"
        assert v.value is None

    def test_stale_does_not_write_current_value(self):
        eff = _eff("stale", reason="上游已变")
        v = verdict_from_evaluation(eff, value=Decimal("7"), errors=[])
        assert v.outcome == "stale"
        assert v.value is None
        assert v.applied is False


# ─────────────────────────────────────────────────────────────────────────────
# 成功路径：ok 态才写值
# ─────────────────────────────────────────────────────────────────────────────
class TestSuccessPath:
    def test_ok_applies_value(self):
        eff = _eff("preset")
        v = verdict_from_evaluation(eff, value=Decimal("42.5"), errors=[])
        assert v.outcome == "ok"
        assert v.value == Decimal("42.5")
        assert v.applied is True

    def test_custom_ok_applies_value(self):
        eff = _eff("custom", source="custom")
        v = verdict_from_evaluation(eff, value=Decimal("1"), errors=[])
        assert v.outcome == "ok"
        assert v.applied is True

    def test_serialized_value_is_string_not_number(self):
        """value 序列化为字符串防 JSON 丢精度；None 保持 null。"""
        eff = _eff("preset")
        ok = verdict_from_evaluation(eff, value=Decimal("0.005"), errors=[]).to_dict()
        assert ok["value"] == "0.005"
        failed = verdict_from_evaluation(eff, value=Decimal("0"), errors=["x"]).to_dict()
        assert failed["value"] is None


# ─────────────────────────────────────────────────────────────────────────────
# Req 2.2：来源 tooltip 口径单一（HTML/OO 读同一段）
# ─────────────────────────────────────────────────────────────────────────────
class TestSourceTooltip:
    def test_custom_tooltip(self):
        eff = _eff("custom", expression="=WP('D4-2','E')", source="custom")
        t = build_source_tooltip(eff)
        assert "用户自定义" in t
        assert "=WP('D4-2','E')" in t

    def test_preset_tooltip_shows_source_name(self):
        eff = _eff("preset", expression="=SUM(1,2)", source="preset:seed")
        t = build_source_tooltip(eff)
        assert "预设公式" in t
        assert "seed" in t

    def test_none_tooltip(self):
        eff = _eff("preset_missing", expression=None, source="none")
        t = build_source_tooltip(eff)
        assert "无" in t

    def test_verdict_carries_same_tooltip(self):
        """裁决携带的 tooltip 与 build_source_tooltip 完全一致（单一口径）。"""
        eff = _eff("preset")
        v = verdict_from_evaluation(eff, value=Decimal("1"), errors=[])
        assert v.tooltip == build_source_tooltip(eff)


# ─────────────────────────────────────────────────────────────────────────────
# verdict_from_effective：非求值态直达，可求值态返回 None
# ─────────────────────────────────────────────────────────────────────────────
class TestVerdictFromEffective:
    @pytest.mark.parametrize(
        "state,outcome",
        [("corrupt", "failed"), ("blocked", "blocked"), ("preset_missing", "pending"), ("stale", "stale")],
    )
    def test_non_eval_states_direct(self, state, outcome):
        v = verdict_from_effective(_eff(state, expression=None))
        assert v is not None
        assert v.outcome == outcome
        assert v.value is None

    @pytest.mark.parametrize("state", ["custom", "preset"])
    def test_eval_states_return_none(self, state):
        assert verdict_from_effective(_eff(state)) is None


# ─────────────────────────────────────────────────────────────────────────────
# 变异反向自检：如果裁决层被改成「失败转零」，上面的守卫必须打红
# ─────────────────────────────────────────────────────────────────────────────
class TestMutationReverseCheck:
    def test_failure_outcome_is_not_ok(self):
        """反向：failed 态不得被误判为 ok（否则失败会写值）。"""
        eff = _eff("preset")
        v = verdict_from_evaluation(eff, value=Decimal("0"), errors=["e"])
        assert v.outcome != "ok"
        assert not v.applied
