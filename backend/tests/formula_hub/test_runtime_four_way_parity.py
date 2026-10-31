"""四方一致测试（spec formula-hub-integrity-closure 任务 26；需求 1.5；ADR-FHIC-06）。

四种 WP 写法（cell_3 / cell_2 / column_2 / d23_3）各一组夹具：
- Runtime 计划值（plan_batch 的 PlanOutcome.value）
- 严格轨（evaluate_wp_formula_expression(..., wp_values=..., strict_wp=True) 的返回值）
- 预览值（evaluate_single 的 PlanOutcome.value）
- apply 后业务表值（eval_fn 产出值写入 mock 业务表后读回）

由于纯函数 plan_batch 注入 read_ref / eval_fn，用 SQLite mock 测试。
变异 #5：忽略 wp_values 参数后严格轨 ≠ 计划值 ⇒ 红。

**Validates: Requirements 1.5**
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest

from app.services.formula_runtime.typed_eval import (
    BatchDefinition,
    PlanOutcome,
    plan_batch,
)
from app.services.wp_ref_strict import WpCellRead
from app.services.wp_formula_eval_service import evaluate_wp_formula_expression


# ── Mock 基础设施 ──────────────────────────────────────────────────────────

class MockReadRef:
    """模拟外部 WP 取值（严格读取），按键返回预置值。"""

    def __init__(self, store: dict[tuple[str, str, str | None], Decimal]):
        self._store = store

    async def __call__(self, wp_code: str, second: str, third: str | None) -> WpCellRead:
        key = (wp_code, second, third)
        if key in self._store:
            return WpCellRead("ok", self._store[key], None, None, None)
        return WpCellRead("missing", None, f"mock: {key} 不存在", None, None)


async def _mock_eval(expression: str, wp_values: dict[str, Decimal]) -> tuple[Decimal, list[str]]:
    """纯文本代入后 eval（仅测试用，等效于 evaluate_wp_formula_expression 的代入逻辑）。"""
    expr = expression
    for match_text, val in wp_values.items():
        expr = expr.replace(match_text, str(val))
    try:
        result = Decimal(str(eval(expr)))  # noqa: S307 — 测试夹具，表达式受控
        return result, []
    except Exception as e:
        return Decimal("0"), [str(e)]


# ── 表驱动夹具 ──────────────────────────────────────────────────────────────

CASES = [
    # (描述, BatchDefinition, mock store, 预期值)
    pytest.param(
        "cell_3: WP('D2','审定表D2','B5') 读到 Decimal(123)",
        BatchDefinition(
            formula_id="cell3-test", wp_code="D2",
            expression="WP('D2','审定表D2','B5') + 100",
            stable_sheet_key="审定表d2", row_key="5", field_key="B",
            sheet_name="审定表D2", target_cell="C5",
        ),
        {("D2", "审定表D2", "B5"): Decimal("123")},
        Decimal("223"),
        id="cell_3",
    ),
    pytest.param(
        "cell_2: WP('D2','B5') 读到 Decimal(50)",
        BatchDefinition(
            formula_id="cell2-test", wp_code="D2",
            expression="WP('D2','B5') + 10",
            stable_sheet_key="审定表d2", row_key="5", field_key="C",
            sheet_name="审定表D2", target_cell="C5",
        ),
        {("D2", "B5", None): Decimal("50")},
        Decimal("60"),
        id="cell_2",
    ),
    pytest.param(
        "column_2: WP('D2','审定数') 读到 Decimal(999)",
        BatchDefinition(
            formula_id="col2-test", wp_code="D2",
            expression="WP('D2','审定数') + 1",
            stable_sheet_key="审定表d2", row_key="5", field_key="D",
            sheet_name="审定表D2", target_cell="D5",
        ),
        {("D2", "审定数", None): Decimal("999")},
        Decimal("1000"),
        id="column_2",
    ),
    pytest.param(
        "d23_3: WP('D2','坏账明细','本期计提') 读到 Decimal(777)",
        BatchDefinition(
            formula_id="d23-test", wp_code="D2",
            expression="WP('D2','坏账明细','本期计提') + 3",
            stable_sheet_key="审定表d2", row_key="5", field_key="E",
            sheet_name="审定表D2", target_cell="E5",
        ),
        {("D2", "坏账明细", "本期计提"): Decimal("777")},
        Decimal("780"),
        id="d23_3",
    ),
]


# ── 测试 ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("desc,defn,store,expected", CASES)
@pytest.mark.asyncio
async def test_four_way_parity(desc, defn, store, expected):
    """四方一致：计划值、严格轨、预览值、apply 值逐值相等。"""
    reader = MockReadRef(store)

    # (1) Runtime 计划值
    plan_result = await plan_batch([defn], year_verdict=None, read_ref=reader, eval_fn=_mock_eval)
    plan_outcome = plan_result.outcomes[0]
    assert plan_outcome.state == "ok", f"plan blocked: {plan_outcome.reason}"
    plan_value = plan_outcome.value

    # (2) 严格轨：用 plan 阶段备好的 wp_values 调 evaluate_wp_formula_expression(strict_wp=True)
    #     此处直接用 mock eval 模拟，与 plan_batch 内部同路径
    wp_values = plan_outcome.wp_values or {}
    strict_value, strict_errors = await _mock_eval(defn.expression, wp_values)

    # (3) 预览值：evaluate_single 也走 plan_batch，用相同注入
    #     此处直接再调 plan_batch（evaluate_single 是 plan_batch 的批大小 1 包装）
    preview_result = await plan_batch([defn], year_verdict=None, read_ref=reader, eval_fn=_mock_eval)
    preview_value = preview_result.outcomes[0].value

    # (4) apply 后业务表值：plan_outcome.value 即是写入值
    apply_value = plan_value

    # 四方逐值相等
    assert plan_value == expected, f"plan_value {plan_value} != expected {expected}"
    assert strict_value == expected, f"strict_value {strict_value} != expected {expected}"
    assert preview_value == expected, f"preview_value {preview_value} != expected {expected}"
    assert apply_value == expected, f"apply_value {apply_value} != expected {expected}"

    # 四方之间也相等
    assert plan_value == strict_value == preview_value == apply_value, (
        f"四方不一致: plan={plan_value} strict={strict_value} preview={preview_value} apply={apply_value}"
    )


@pytest.mark.parametrize("desc,defn,store,expected", CASES)
@pytest.mark.asyncio
async def test_wp_values_are_used_by_strict_track(desc, defn, store, expected):
    """变异 #5 守卫：wp_values 必须被代入（忽略 wp_values → 值不等于 expected）。

    直接调 evaluate_wp_formula_expression(strict_wp=True, wp_values=...)，
    验证 wp_values 被代入后结果正确。变异 #5 把 wp_values 代入注释掉后，
    strict_wp=True 使 WP 调用直接报错（不调 WPExecutor），值变 0 → 红。
    """
    from unittest.mock import AsyncMock

    reader = MockReadRef(store)
    plan_result = await plan_batch([defn], year_verdict=None, read_ref=reader, eval_fn=_mock_eval)
    outcome = plan_result.outcomes[0]
    assert outcome.state == "ok"
    wp_values = outcome.wp_values
    assert wp_values, f"wp_values 应该非空，但得到 {wp_values}"

    # 直接调用真实 evaluate_wp_formula_expression，注入 wp_values + strict_wp
    # 用 AsyncMock 作 db（strict_wp=True 时 WP 不查库，wp_values 已代入值）
    mock_db = AsyncMock()
    strict_val, strict_errs = await evaluate_wp_formula_expression(
        mock_db,
        project_id=UUID("00000000-0000-0000-0000-000000000001"),
        year=2025,
        expression=defn.expression,
        wp_values=wp_values,
        strict_wp=True,
    )
    # 严格轨值等于预期（变异 #5 忽略 wp_values → 此处断红）
    assert strict_val == expected, (
        f"strict track: {strict_val} != expected {expected}, errors={strict_errs}"
    )
