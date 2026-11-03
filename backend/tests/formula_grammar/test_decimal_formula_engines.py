"""任务 5：附注 / 单元格求值器的 Decimal 与失败语义回归。

这些测试只走纯求值入口，不写共享 PG；数据库装载和 JSONB 回写边界由
``test_note_formula_dsl.py`` 与 ``test_note_formula_execute_tables.py`` 覆盖。
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.cell_formula_evaluator import _safe_eval, execute_formula
from app.services.formula_engine import safe_eval_expr
from app.services.note_formula_generator import (
    _exec_cross_table,
    _resolve_single_cross_ref,
)
from app.services.note_formula_tables import evaluate as evaluate_note_expression


def test_cell_safe_eval_keeps_decimal_precision() -> None:
    assert _safe_eval("0.1 + 0.2") == Decimal("0.3")
    assert _safe_eval("1 / 8") == Decimal("0.125")


def test_note_cross_table_eval_keeps_decimal_precision() -> None:
    cross_data = {
        "tb": {
            "1001": {
                "audited": Decimal("0.1"),
                "unadjusted": Decimal("0.2"),
            },
        },
    }
    result = _exec_cross_table(
        "TB('1001','审定数') + TB('1001','未审数')",
        cross_data,
    )
    assert result == Decimal("0.3")
    assert isinstance(result, Decimal)


def test_three_formula_engines_return_the_same_decimal_value() -> None:
    expression = "0.1 + 0.2"
    note_value, note_reason = evaluate_note_expression(expression, [])

    assert note_reason is None
    assert note_value == Decimal("0.3")
    assert _safe_eval(expression) == note_value
    assert safe_eval_expr(expression) == note_value


@pytest.mark.asyncio
async def test_cell_execute_reports_missing_coordinate_instead_of_zero() -> None:
    result = await execute_formula(
        "=B2+B3",
        db=None,
        project_id=None,
        year=2025,
        sheet_cells={"1:1": {"value": Decimal("0.1")}},
    )

    assert result["value"] is None
    assert result["error"] == "单元格 B3 无数值"


@pytest.mark.asyncio
async def test_cell_execute_reports_division_by_zero() -> None:
    result = await execute_formula(
        "=B2/0",
        db=None,
        project_id=None,
        year=2025,
        sheet_cells={"1:1": {"value": Decimal("1")}},
    )

    assert result["value"] is None
    assert result["error"] == "除数为 0"


def test_note_missing_cross_table_value_is_none_not_zero() -> None:
    missing = {"tb": {}, "report": {}, "note_tables": {}, "wp": {}, "prior": {}, "aging": {}}

    assert _resolve_single_cross_ref("TB('9999','期末')", missing) is None
    assert _resolve_single_cross_ref("REPORT('missing','期末')", missing) is None
    assert _exec_cross_table("TB('9999','期末') + 1", missing) is None


def test_note_missing_cross_table_value_carries_reason() -> None:
    value, reason = evaluate_note_expression(
        "TB('9999','期末')",
        [],
        lambda _token: None,
    )

    assert value is None
    assert reason == "取不到 TB('9999','期末')"
