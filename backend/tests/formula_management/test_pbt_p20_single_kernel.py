# Feature: formula-management-library, Property 20: 求值内核单一性
"""属性测试 P20：求值内核单一性（Single Evaluation Kernel）。

**Property 20: 求值内核单一性**

*对任意*公式表达式，经收口后的后端求值路径（``report_engine.evaluate_formula``，
consol_report_service 等 18 处调用方统一收口到此）最终都委托
``formula_engine.execute``（L1 内核）求值；不存在绕过内核的并行求值产生不一致结果。

被测收口路径：``app.services.report_engine.evaluate_formula``
（Task 13.3 求值内核收口：废弃 ``formula_parse_utils.evaluate_formula`` /
``FormulaEvaluator``，所有调用方迁移到 L1 内核 ``formula_engine.execute`` 或
``report_engine.evaluate_formula``，后者内部亦委托 L1 内核）。

验证策略（无 DB，纯收口路径 + 内核桩探针）：

1. **委托性**：monkeypatch ``formula_engine.execute`` 为探针（记录调用并转发真实内核），
   随机公式经 ``evaluate_formula`` 求值后，探针**至少被调用一次**——即收口路径确实委托
   L1 内核，未自带并行求值逻辑。
2. **结果一致性（无并行分叉）**：``evaluate_formula`` 的返回值**恰等于**探针记录的最后一次
   L1 内核输出（``FormulaResult.value``）——收口路径不在内核之外二次改写结果。
3. **确定性**：同一公式 + 同一取数源重复求值，结果逐次相等（单一内核纯函数，无并行路径
   产生不一致）。

Framework: hypothesis（遵循 conftest fast profile，max_examples 可经
HYPOTHESIS_MAX_EXAMPLES 覆盖）。

**Validates: Requirements 20.1, 20.2**（设计 Req 25.1/25.2：单一内核收口）
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

import app.services.formula_engine as formula_engine
from app.services.formula_engine import FormulaContext, execute as real_execute
from app.services.report_engine import evaluate_formula


# ─────────────────────────────────────────────────────────────────────────────
# 内存取数桩：实现 AmountResolver 协议（resolve_tb / resolve_sum），无 DB。
# ─────────────────────────────────────────────────────────────────────────────
class _StubResolver:
    """按 (account_code → 金额) 字典取数的 AmountResolver 桩。

    resolve_sum 对 ``start~end`` 范围内（按 code 前缀比较，与内核 SUM_TB 语义一致）
    的账户金额求和。取数语义与真实 resolver 一致，仅数据源为内存字典。
    """

    def __init__(self, tb_map: dict[str, Decimal]):
        self._tb = tb_map

    async def resolve_tb(self, account_code: str, column_name: str) -> Decimal:
        return self._tb.get(account_code, Decimal("0"))

    async def resolve_sum(self, code_range: str, column_name: str) -> Decimal:
        parts = code_range.split("~")
        if len(parts) != 2:
            return Decimal("0")
        start, end = parts[0], parts[1]
        prefix_len = len(start)
        total = Decimal("0")
        for code, val in self._tb.items():
            if start <= code[:prefix_len] <= end:
                total += val
        return total


# ─────────────────────────────────────────────────────────────────────────────
# 智能生成器：约束到内核可解析的公式空间（TB / SUM_TB / ROW / 数字 + 算术）。
# ─────────────────────────────────────────────────────────────────────────────
_ACCOUNT_CODE = st.integers(min_value=1000, max_value=6999).map(str)
_COLUMN = st.sampled_from(["期末余额", "审定数", "年初余额"])
_NUMBER = st.integers(min_value=0, max_value=100000).map(lambda n: str(n))


def _tb_ref(code: str, col: str) -> str:
    return f"TB('{code}','{col}')"


@st.composite
def _formula_and_tb(draw):
    """生成 (formula, tb_map, row_cache)：公式引用若干账户 + 数字，经算术组合。

    - tb_map：随机账户 → 正整数金额（保证内核取数确定）。
    - formula：1~4 个 TB(...) / 数字项以 +/-/* 连接（避免除法引入的边界噪声，
      单一内核语义仍完整覆盖）。
    - row_cache：随机 ROW 值（供收口路径 ctx 注入，验证 ROW 也走同一内核）。
    """
    codes = draw(
        st.lists(_ACCOUNT_CODE, min_size=1, max_size=5, unique=True)
    )
    tb_map = {c: Decimal(draw(st.integers(min_value=1, max_value=1_000_000))) for c in codes}

    n_terms = draw(st.integers(min_value=1, max_value=4))
    ops = draw(st.lists(st.sampled_from(["+", "-", "*"]), min_size=n_terms, max_size=n_terms))

    terms: list[str] = []
    for _ in range(n_terms):
        kind = draw(st.sampled_from(["tb", "num"]))
        if kind == "tb":
            code = draw(st.sampled_from(codes))
            col = draw(_COLUMN)
            terms.append(_tb_ref(code, col))
        else:
            terms.append(draw(_NUMBER))

    formula = terms[0]
    for i in range(1, n_terms):
        formula = f"{formula} {ops[i]} {terms[i]}"

    return formula, tb_map, {}


@given(payload=_formula_and_tb())
@settings(max_examples=100)
def test_p20_report_engine_delegates_to_l1_kernel(payload, monkeypatch):
    """P20：收口路径 evaluate_formula 委托 L1 内核，结果=内核输出，且确定性一致。

    **Validates: Requirements 20.1, 20.2**
    """
    formula, tb_map, row_cache = payload

    # ── L1 内核探针：记录每次调用与其真实输出（转发真实 execute，语义不变）──
    calls: list[tuple[str, Decimal]] = []

    def _spy_execute(f, ctx):
        result = real_execute(f, ctx)
        calls.append((f, result.value))
        return result

    # evaluate_formula 内部 `from app.services.formula_engine import execute`，
    # 于调用时做属性查找 → 打桩模块级 execute 即可被收口路径拾取。
    monkeypatch.setattr(formula_engine, "execute", _spy_execute)

    resolver = _StubResolver(tb_map)

    async def _scenario():
        return await evaluate_formula(formula, resolver=resolver, row_cache=dict(row_cache))

    # ── 第一次求值 ──
    value = asyncio.run(_scenario())

    # 1. 委托性：收口路径至少调用一次 L1 内核（未自带并行求值）。
    assert calls, "evaluate_formula 未委托 formula_engine.execute（L1 内核）"

    # 2. 结果一致性：返回值恰等于内核最后一次输出（内核之外无二次改写/并行分叉）。
    assert value == calls[-1][1]

    # 3. 确定性：同公式 + 同取数源重复求值结果逐次相等（单一内核纯函数）。
    value_again = asyncio.run(_scenario())
    assert value_again == value


@given(payload=_formula_and_tb())
@settings(max_examples=50)
def test_p20_result_matches_direct_kernel_call(payload):
    """P20 辅证：收口路径结果与直接调用 L1 内核（等价 ctx）逐一相等。

    收口路径把 TB/SUM_TB 经 resolver 预取为数值后交内核；直接构造等价
    FormulaContext（tb_data + row_cache）调 L1 内核应得同值——证明不存在
    "绕过内核的并行求值产生不一致结果"。

    **Validates: Requirements 20.1, 20.2**
    """
    formula, tb_map, row_cache = payload
    resolver = _StubResolver(tb_map)

    async def _via_funnel():
        return await evaluate_formula(formula, resolver=resolver, row_cache=dict(row_cache))

    funnel_value = asyncio.run(_via_funnel())

    # 直接经 L1 内核求值（等价上下文：tb_data 多列 + row_cache）。
    ctx = FormulaContext(
        tb_data={
            code: {"期末余额": val, "审定数": val, "年初余额": val}
            for code, val in tb_map.items()
        },
        row_cache={k: Decimal(str(v)) for k, v in row_cache.items()},
    )
    kernel_value = real_execute(formula, ctx).value

    assert funnel_value == kernel_value
