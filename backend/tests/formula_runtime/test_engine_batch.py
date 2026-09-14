"""tests/formula_runtime/test_engine_batch.py — batch runtime 单一入口测试。

验证 engine.execute_batch：
- auto_calc 产出 MutationIntent
- logic_check 产出 issue，不产 mutation
- reasonability 产出 hint，不产 mutation
- missing ref → error recorded, no mutation
- execute_batch 不写 last_computed_at（由上层确认）
- PBT: 对任意合法表达式和预加载上下文，auto_calc 总产 intent

**Validates: Requirements 1.2, 5.1, 11.1**
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.formula_management.engine import (
    BatchExecutionResult,
    BatchFormulaContext,
    BatchFormulaDefinition,
    CanonicalFormulaTarget,
    MutationIntent,
    execute_batch,
)


def _make_target(**kwargs) -> CanonicalFormulaTarget:
    defaults = {
        "domain": "workpaper",
        "project_id": uuid4(),
        "year": 2025,
        "addr_id": "D2/D2-1/B5",
        "locator": {"wp_id": str(uuid4()), "item": "test", "cell": "B5"},
    }
    defaults.update(kwargs)
    return CanonicalFormulaTarget(**defaults)


# ─── Unit tests ───────────────────────────────────────────────────────────────


class TestBatchAutoCalc:
    """auto_calc 类型的 batch 执行。"""

    def test_produces_mutation_intent(self):
        """auto_calc 成功求值产出 MutationIntent。"""
        target = _make_target()
        formulas = [
            BatchFormulaDefinition(
                id="f1",
                formula_type="auto_calc",
                expression="100+200",
                target=target,
                ref_addr_ids=[],
                addr_id="D2/D2-1/B5",
            ),
        ]
        ctx = BatchFormulaContext(values={}, missing=set(), ambiguous=set())
        result = execute_batch(formulas=formulas, context=ctx)

        assert len(result.intents) == 1
        intent = result.intents[0]
        assert intent.computed_value == Decimal("300")
        assert intent.formula_id == "f1"
        assert intent.formula_type == "auto_calc"
        assert intent.target == target

    def test_no_last_computed_at_in_result(self):
        """execute_batch 返回中没有 last_computed_at — 由上层确认。"""
        target = _make_target()
        formulas = [
            BatchFormulaDefinition(
                id="f1",
                formula_type="auto_calc",
                expression="50*2",
                target=target,
                ref_addr_ids=[],
            ),
        ]
        ctx = BatchFormulaContext(values={}, missing=set(), ambiguous=set())
        result = execute_batch(formulas=formulas, context=ctx)

        # BatchExecutionResult has no last_computed_at field
        assert not hasattr(result, "last_computed_at")
        # MutationIntent has no last_computed_at field
        assert not hasattr(result.intents[0], "last_computed_at")

    def test_uses_preloaded_context_values(self):
        """auto_calc 使用预加载的 BatchFormulaContext.values。"""
        target = _make_target(addr_id="report/BS-001/current")
        formulas = [
            BatchFormulaDefinition(
                id="f1",
                formula_type="auto_calc",
                expression="ROW('ref-a')+ROW('ref-b')",
                target=target,
                ref_addr_ids=["ref-a", "ref-b"],
                addr_id="report/BS-001/current",
            ),
        ]
        ctx = BatchFormulaContext(
            values={"ref-a": Decimal("1000"), "ref-b": Decimal("500")},
            missing=set(),
            ambiguous=set(),
        )
        result = execute_batch(formulas=formulas, context=ctx)

        assert len(result.intents) == 1
        assert result.intents[0].computed_value == Decimal("1500")
        assert len(result.errors) == 0

    def test_evaluation_failure_records_error(self):
        """求值失败记录 error，不产 MutationIntent。"""
        target = _make_target()
        formulas = [
            BatchFormulaDefinition(
                id="f1",
                formula_type="auto_calc",
                expression="INVALID_SYNTAX((((",
                target=target,
                ref_addr_ids=[],
            ),
        ]
        ctx = BatchFormulaContext(values={}, missing=set(), ambiguous=set())
        result = execute_batch(formulas=formulas, context=ctx)

        assert len(result.intents) == 0
        assert len(result.errors) == 1
        assert result.errors[0]["formula_id"] == "f1"
        assert result.errors[0]["reason"] == "evaluation_failed"


class TestBatchLogicCheck:
    """logic_check 类型的 batch 执行。"""

    def test_produces_issue_no_mutation(self):
        """logic_check 条件不通过产 issue，不产 MutationIntent。"""
        formulas = [
            BatchFormulaDefinition(
                id="lc1",
                formula_type="logic_check",
                expression="0",  # evaluates to 0 → 条件不通过
                ref_addr_ids=[],
                issue_description="资产负债表不平",
                addr_id="report/BS/check",
            ),
        ]
        ctx = BatchFormulaContext(values={}, missing=set(), ambiguous=set())
        result = execute_batch(formulas=formulas, context=ctx)

        assert len(result.intents) == 0  # no mutation
        assert len(result.issues) == 1
        assert result.issues[0]["formula_id"] == "lc1"
        assert "资产负债表不平" in result.issues[0]["description"]

    def test_passes_when_nonzero(self):
        """logic_check 条件通过(!=0)时不产 issue。"""
        formulas = [
            BatchFormulaDefinition(
                id="lc2",
                formula_type="logic_check",
                expression="1",  # nonzero → 通过
                ref_addr_ids=[],
                issue_description="should pass",
            ),
        ]
        ctx = BatchFormulaContext(values={}, missing=set(), ambiguous=set())
        result = execute_batch(formulas=formulas, context=ctx)

        assert len(result.intents) == 0
        assert len(result.issues) == 0


class TestBatchReasonability:
    """reasonability 类型的 batch 执行。"""

    def test_produces_hint_no_mutation(self):
        """reasonability 条件成立时产 hint，不产 MutationIntent。"""
        formulas = [
            BatchFormulaDefinition(
                id="r1",
                formula_type="reasonability",
                expression="1",  # nonzero → triggered
                ref_addr_ids=[],
                hint_text="费用变动率超过阈值",
                addr_id="D2/D2-5/analysis",
            ),
        ]
        ctx = BatchFormulaContext(values={}, missing=set(), ambiguous=set())
        result = execute_batch(formulas=formulas, context=ctx)

        assert len(result.intents) == 0  # no mutation
        assert len(result.hints) == 1
        assert result.hints[0]["formula_id"] == "r1"
        assert "费用变动率" in result.hints[0]["hint_text"]

    def test_not_triggered_no_hint(self):
        """reasonability 条件不成立(==0)时不产 hint。"""
        formulas = [
            BatchFormulaDefinition(
                id="r2",
                formula_type="reasonability",
                expression="0",  # not triggered
                ref_addr_ids=[],
                hint_text="should not appear",
            ),
        ]
        ctx = BatchFormulaContext(values={}, missing=set(), ambiguous=set())
        result = execute_batch(formulas=formulas, context=ctx)

        assert len(result.hints) == 0


class TestBatchMissingRefs:
    """missing/ambiguous ref 处理。"""

    def test_missing_ref_produces_error(self):
        """引用在 missing 集中 → error，不产 mutation。"""
        target = _make_target()
        formulas = [
            BatchFormulaDefinition(
                id="f1",
                formula_type="auto_calc",
                expression="ROW('ref-x')+1",
                target=target,
                ref_addr_ids=["ref-x"],
            ),
        ]
        ctx = BatchFormulaContext(
            values={},
            missing={"ref-x"},
            ambiguous=set(),
        )
        result = execute_batch(formulas=formulas, context=ctx)

        assert len(result.intents) == 0
        assert len(result.errors) == 1
        assert result.errors[0]["reason"] == "unresolved_refs"
        assert "missing:ref-x" in result.errors[0]["refs"]

    def test_ambiguous_ref_produces_error(self):
        """引用在 ambiguous 集中 → error，不产 mutation。"""
        target = _make_target()
        formulas = [
            BatchFormulaDefinition(
                id="f2",
                formula_type="auto_calc",
                expression="ROW('ref-y')",
                target=target,
                ref_addr_ids=["ref-y"],
            ),
        ]
        ctx = BatchFormulaContext(
            values={},
            missing=set(),
            ambiguous={"ref-y"},
        )
        result = execute_batch(formulas=formulas, context=ctx)

        assert len(result.intents) == 0
        assert len(result.errors) == 1
        assert "ambiguous:ref-y" in result.errors[0]["refs"]


class TestBatchMixed:
    """混合批次（多类型公式同批执行）。"""

    def test_mixed_batch(self):
        """同批含 auto_calc + logic_check + reasonability。"""
        target = _make_target()
        formulas = [
            BatchFormulaDefinition(
                id="f-auto",
                formula_type="auto_calc",
                expression="100+50",
                target=target,
                ref_addr_ids=[],
            ),
            BatchFormulaDefinition(
                id="f-logic",
                formula_type="logic_check",
                expression="0",  # fails
                ref_addr_ids=[],
                issue_description="勾稽失败",
            ),
            BatchFormulaDefinition(
                id="f-reason",
                formula_type="reasonability",
                expression="1",  # triggered
                ref_addr_ids=[],
                hint_text="合理性提示",
            ),
        ]
        ctx = BatchFormulaContext(values={}, missing=set(), ambiguous=set())
        result = execute_batch(formulas=formulas, context=ctx)

        assert len(result.intents) == 1
        assert result.intents[0].computed_value == Decimal("150")
        assert len(result.issues) == 1
        assert len(result.hints) == 1
        assert len(result.errors) == 0


# ─── PBT ──────────────────────────────────────────────────────────────────────


@settings(max_examples=5)
@given(
    a=st.integers(min_value=0, max_value=99999),
    b=st.integers(min_value=0, max_value=99999),
)
def test_auto_calc_always_produces_intent(a: int, b: int):
    """**Validates: Requirements 1.2**

    PBT: 对任意合法算术表达式和预加载上下文，auto_calc 总产出 MutationIntent
    且 computed_value 等于期望结果。
    """
    target = _make_target()
    formulas = [
        BatchFormulaDefinition(
            id="pbt-f",
            formula_type="auto_calc",
            expression=f"{a}+{b}",
            target=target,
            ref_addr_ids=[],
        ),
    ]
    ctx = BatchFormulaContext(values={}, missing=set(), ambiguous=set())
    result = execute_batch(formulas=formulas, context=ctx)

    assert len(result.intents) == 1
    assert result.intents[0].computed_value == Decimal(str(a + b))
    assert len(result.errors) == 0
