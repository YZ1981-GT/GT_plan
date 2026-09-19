# Feature: formula-management-library, Property 17: logic_check 收编等价于原硬编码勾稽
"""属性测试 P17：logic_check 收编 7 条报表勾稽，其 passed 判定等价于原硬编码实现。

*对任意* 报表数据（资产负债表 / 利润表随机行），以 ``logic_check`` 公式执行的
7 条勾稽校验结果（每条 ``passed`` 判定）与原前端 ``computeCrossCheckResults``
硬编码实现逐条一致（model-based：收编不改变勾稽语义，Req 6.4）。

被测（后端收编路径）:
    ``app.services.formula_management.logic_check``
    - ``build_report_row_cache(bs_rows, is_rows)`` — 由报表行构建 row_cache；
    - ``run_cross_checks(row_cache, resolve_refs=False)`` — 经 ``execute_formula``
      的 logic_check 分派执行 7 条勾稽，聚合每条 ``CrossCheckOutcome.passed``。

参照模型（reference model）:
    本文件在 Python 侧**独立移植**前端
    ``audit-platform/frontend/src/views/composables/useReportCrossCheck.ts``
    的 ``computeCrossCheckResults``（``buildMap`` + ``get`` + 7 条 ``check``），
    用 IEEE-754 double（Python ``float``）与 ``Math.round`` 语义逐字节复刻 JS 行为，
    **不复用**任何后端逻辑，作为独立参照。``reportCodeMap`` 取 ``undefined``
    （向后兼容路径，与后端 ``build_report_row_cache`` 的取值口径一致）。

断言:
    后端 7 条 ``outcomes[i].passed`` 与参照模型第 i 条 ``passed`` 逐条相等
    （顺序与 ``_CROSS_CHECK_SEEDS`` / 前端 check 列表一致）。

生成器（智能约束到报表输入空间）:
    随机整数金额（非零以命中精确匹配主路径），并以一定概率构造"平衡"数据
    （资产=负债+权益 / 净利润=利润总额−所得税 / 所得税=利润总额×25%）以覆盖
    每条勾稽的 passed / not-passed 两个分支；整数金额使 checks 1–5、7 的算术
    在 ``float`` 与 ``Decimal`` 下均为精确值（无舍入分歧），从而聚焦语义等价性。

Framework: hypothesis（遵循 conftest fast profile，max_examples 可经
HYPOTHESIS_MAX_EXAMPLES 覆盖）。

**Validates: Requirements 6.4**
"""

from __future__ import annotations

import asyncio
import math
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.formula_management.logic_check import (
    build_report_row_cache,
    run_cross_checks,
)


# ─────────────────────────────────────────────────────────────────────────────
# 事件循环辅助：run_cross_checks 为协程；resolve_refs=False 时无真实 async I/O。
# ─────────────────────────────────────────────────────────────────────────────
def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─────────────────────────────────────────────────────────────────────────────
# 参照模型：Python 侧独立移植 useReportCrossCheck.computeCrossCheckResults
# （reportCodeMap=undefined 的向后兼容路径；float + Math.round 语义复刻 JS）。
# ─────────────────────────────────────────────────────────────────────────────
def _build_map_ref(rows: list[dict[str, Any]]) -> dict[str, float]:
    """复刻前端 ``buildMap``：按 row_code / row_name 建索引，合计行覆盖同名非合计行。"""
    m: dict[str, float] = {}
    # 先填非合计行（仅当键未出现，`!map[k]` 语义把 0/None 视为未出现）
    for row in rows:
        amt = float(row.get("current_period_amount") or 0)
        if not row.get("is_total_row"):
            code = row.get("row_code")
            name = row.get("row_name")
            if code and not m.get(code):
                m[code] = amt
            if name and not m.get(name):
                m[name] = amt
    # 再填合计行（覆盖同名）
    for row in rows:
        amt = float(row.get("current_period_amount") or 0)
        if row.get("is_total_row"):
            code = row.get("row_code")
            name = row.get("row_name")
            if code:
                m[code] = amt
            if name:
                m[name] = amt
    return m


def _get_ref(m: dict[str, float], *keys: str) -> float:
    """复刻前端 ``get``（reportCodeMap=undefined）：① 精确非零 → ③ 子串模糊非零 → 0。"""
    # ① 精确匹配值表 key（row_code / row_name），非零优先
    for k in keys:
        v = m.get(k)
        if v is not None and v != 0:
            return v
    # ②（canonical row_code 解析）——reportCodeMap 缺省，跳过（向后兼容路径）
    # ③ miss 回退：中文名/编码子串模糊匹配（非零）
    for k in keys:
        for mk, mv in m.items():
            if mv != 0 and k in mk:
                return mv
    return 0.0


def _js_round(x: float) -> float:
    """复刻 JS ``Math.round``（half-up：floor(x + 0.5)），区别于 Python 银行家舍入。"""
    return math.floor(x + 0.5)


def _check_ref(left: float, right: float, tolerance: float = 0.0) -> bool:
    """复刻前端 ``check``：diff = Math.round((l-r)*100)/100；tol>0→|diff|<=tol 否则|diff|<0.01。"""
    diff = _js_round((left - right) * 100) / 100
    return abs(diff) <= tolerance if tolerance > 0 else abs(diff) < 0.01


def compute_cross_check_passed_ref(
    bs_rows: list[dict[str, Any]], is_rows: list[dict[str, Any]]
) -> list[bool]:
    """参照模型：返回 7 条勾稽的 passed 列表（顺序与前端 / 后端 seeds 一致）。"""
    bs_map = _build_map_ref(bs_rows)
    is_map = _build_map_ref(is_rows)

    total_assets = _get_ref(bs_map, "assets_total", "资产总计", "资产合计")
    total_liabilities = _get_ref(bs_map, "liabilities_total", "负债合计", "负债总计")
    total_equity = _get_ref(
        bs_map, "equity_total", "所有者权益合计", "股东权益合计", "权益合计"
    )
    net_profit = _get_ref(is_map, "IS-019", "净利润")
    revenue = _get_ref(is_map, "IS-001", "营业收入")
    cost = _get_ref(is_map, "IS-002", "营业成本")
    profit_before_tax = _get_ref(is_map, "IS-017", "利润总额")
    income_tax = _get_ref(is_map, "IS-018", "所得税费用", "所得税")
    cash = _get_ref(bs_map, "BS-001", "货币资金")

    return [
        # 1. 资产合计 = 负债合计 + 所有者权益合计（tol=1）
        _check_ref(total_assets, total_liabilities + total_equity, 1),
        # 2. 营业收入 − 营业成本 = 毛利（恒等）
        _check_ref(revenue - cost, revenue - cost),
        # 3. 利润总额 − 所得税 = 净利润（tol=1）
        _check_ref(profit_before_tax - income_tax, net_profit, 1),
        # 4. 资产 − 负债 = 权益（tol=1）
        _check_ref(total_assets - total_liabilities, total_equity, 1),
        # 5. 所有者权益变动表期末 = 资产负债表权益（恒等）
        _check_ref(total_equity, total_equity),
        # 6. 有效税率 ≈ 25%（tol = 利润总额 × 5%）
        _check_ref(
            income_tax,
            profit_before_tax * 0.25 if profit_before_tax > 0 else 0,
            profit_before_tax * 0.05,
        ),
        # 7. 货币资金 ≥ 0（负值异常；tol = |cash|）
        _check_ref(cash, 0, abs(cash)),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# 智能生成器：随机报表数据（整数金额 + 概率性平衡以覆盖 passed / not-passed）
# ─────────────────────────────────────────────────────────────────────────────
# 非零整数：命中精确匹配主路径，且使 checks 1–5、7 的算术在 float / Decimal 下皆精确。
_NONZERO_INT = st.integers(min_value=-1_000_000, max_value=1_000_000).filter(
    lambda v: v != 0
)


def _row(code: str, name: str, amount: float) -> dict[str, Any]:
    return {
        "row_code": code,
        "row_name": name,
        "current_period_amount": amount,
        "is_total_row": False,
    }


@st.composite
def _report_data(draw):
    """联合抽取资产负债表 / 利润表随机行；概率性构造平衡数据覆盖两分支。

    - 资产 = 负债 + 权益（balance_bs）→ 覆盖 check 1 / 4 的 passed 分支；
    - 所得税 = 利润总额 × 25%（balance_tax）→ 覆盖 check 6 的 passed 分支；
    - 净利润 = 利润总额 − 所得税（balance_net）→ 覆盖 check 3 的 passed 分支；
      否则取独立随机值（多数情形不平衡 → 覆盖 not-passed 分支）。
    """
    liabilities = draw(_NONZERO_INT)
    equity = draw(_NONZERO_INT)
    if draw(st.booleans()):
        assets: float = liabilities + equity  # 平衡 → check 1/4 passed
    else:
        assets = liabilities + equity + draw(_NONZERO_INT)  # 大概率不平衡

    profit_before_tax = draw(_NONZERO_INT)
    # 所得税：平衡取 25% 有效税率；否则独立随机
    if draw(st.booleans()):
        income_tax: float = profit_before_tax * 0.25 if profit_before_tax > 0 else 0.0
    else:
        income_tax = draw(_NONZERO_INT)

    # 净利润：平衡取 利润总额 − 所得税；否则独立随机
    if draw(st.booleans()):
        net_profit: float = profit_before_tax - income_tax
    else:
        net_profit = draw(_NONZERO_INT)

    revenue = draw(_NONZERO_INT)
    cost = draw(_NONZERO_INT)
    cash = draw(st.integers(min_value=-1_000_000, max_value=1_000_000))

    bs_rows = [
        _row("assets_total", "资产总计", assets),
        _row("liabilities_total", "负债合计", liabilities),
        _row("equity_total", "所有者权益合计", equity),
        _row("BS-001", "货币资金", cash),
    ]
    is_rows = [
        _row("IS-019", "净利润", net_profit),
        _row("IS-001", "营业收入", revenue),
        _row("IS-002", "营业成本", cost),
        _row("IS-017", "利润总额", profit_before_tax),
        _row("IS-018", "所得税费用", income_tax),
    ]
    return bs_rows, is_rows


@given(_report_data())
@settings(max_examples=200)
def test_logic_check_crosscheck_equiv(case):
    """P17：7 条 logic_check 勾稽的 passed 判定逐条等价于原硬编码 computeCrossCheckResults。

    **Validates: Requirements 6.4**
    """
    bs_rows, is_rows = case

    # 后端收编路径：报表行 → row_cache → logic_check 执行 → 逐条 passed。
    row_cache = build_report_row_cache(bs_rows, is_rows)
    result = _run(run_cross_checks(row_cache, resolve_refs=False))
    backend_passed = [o.passed for o in result.outcomes]

    # 参照模型：独立移植的前端 computeCrossCheckResults 逐条 passed。
    reference_passed = compute_cross_check_passed_ref(bs_rows, is_rows)

    # 收编等价性：条数一致 + 逐条 passed 相等。
    assert len(backend_passed) == 7, f"应有 7 条勾稽，实得 {len(backend_passed)}"
    assert len(reference_passed) == 7
    for i, (be, ref) in enumerate(zip(backend_passed, reference_passed), start=1):
        assert be == ref, (
            f"第 {i} 条勾稽 passed 不一致：后端 logic_check={be} 参照模型={ref}；"
            f"bs_rows={bs_rows} is_rows={is_rows}"
        )
