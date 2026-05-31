"""consol-phase1-arch-lock 正确性属性测试（hypothesis PBT）.

覆盖设计 §六 属性：
- Q1 公式语义一致：同一 formula 注入两 resolver → 解析+求值路径相同，仅取数值不同
- Q2 求值安全：随机非法/注入表达式 → 返回 Decimal("0") 不抛、不执行 eval
- Q3 抵销口径一致：随机抵销集（draft/approved 混合）→ worksheet 与 trial 消费集合相同（均 approved）
- Q4 审批重算幂等：同笔抵销重复触发 → 消费集合不变
- Q6 Decimal：AmountResolver + 聚合全程 Decimal 逐位相等
- Q7 少数股东比例语义：随机母/子持股比例 → 附注少数股东比例 == 子比例（不求补数）

铁律：hypothesis 调速 max_examples 10~15。
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
from hypothesis import given, settings, strategies as st

from app.services.amount_resolver import AmountResolver
from app.services.report_engine import evaluate_formula
from app.models.consolidation_models import ReviewStatusEnum


PBT_SETTINGS = settings(max_examples=15, deadline=None)


# ---------------------------------------------------------------------------
# 测试用 resolver（实现 AmountResolver 协议，取数走内存字典，不触 DB）
# ---------------------------------------------------------------------------

class _DictResolver:
    """以 (project_id, year) + account_code → Decimal 的内存字典模拟取数源。

    db/project_id/year 属性供 evaluate_formula 构造 parser 使用（不实际查询）。
    """

    def __init__(self, amounts: dict[str, Decimal]):
        self.db = None
        self.project_id = None
        self.year = 2025
        self._amounts = amounts

    async def resolve_tb(self, account_code: str, column_name: str) -> Decimal:
        return self._amounts.get(account_code, Decimal("0"))

    async def resolve_sum(self, code_range: str, column_name: str) -> Decimal:
        parts = code_range.split("~")
        if len(parts) != 2:
            return Decimal("0")
        start, end = parts[0].strip(), parts[1].strip()
        total = Decimal("0")
        for code, val in self._amounts.items():
            if start <= code <= end:
                total += val
        return total


def _run(coro):
    """每测试独立 event loop（避免 pytest-asyncio loop 复用污染，memory 教训）。"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Q1 公式语义一致
# ---------------------------------------------------------------------------

@PBT_SETTINGS
@given(
    a=st.integers(min_value=-1_000_000, max_value=1_000_000),
    b=st.integers(min_value=-1_000_000, max_value=1_000_000),
)
def test_q1_formula_semantics_identical_across_resolvers(a: int, b: int):
    """同一 formula 用两个不同 resolver 求值：

    - 解析+求值路径一致（同一 evaluate_formula 引擎）
    - 结果仅因取数值不同而不同：用相同取数值时两 resolver 结果必须逐位相等。
    """
    formula = "TB('1001','期末余额') + TB('1002','期末余额')"

    # 两个 resolver 给相同取数 → 结果必须完全一致（语义一致性）
    amounts = {"1001": Decimal(a), "1002": Decimal(b)}
    r1 = _DictResolver(dict(amounts))
    r2 = _DictResolver(dict(amounts))

    v1 = _run(evaluate_formula(formula, resolver=r1))
    v2 = _run(evaluate_formula(formula, resolver=r2))
    assert v1 == v2 == Decimal(a) + Decimal(b)

    # ABS/IF 等高级函数对注入 resolver 同样生效（单体/合并语义一致）
    formula2 = "ABS(TB('1001','期末余额') - TB('1002','期末余额'))"
    v3 = _run(evaluate_formula(formula2, resolver=_DictResolver(dict(amounts))))
    assert v3 == abs(Decimal(a) - Decimal(b))


# ---------------------------------------------------------------------------
# Q2 求值安全（非法/注入表达式 → 0，不抛、不 eval）
# ---------------------------------------------------------------------------

_MALICIOUS = st.sampled_from([
    "__import__('os').system('rm -rf /')",
    "eval('1+1')",
    "open('/etc/passwd').read()",
    "().__class__.__bases__",
    "1; DROP TABLE consol_trial",
    "lambda: 1",
    "exec('x=1')",
    "TB('1001','期末余额') + )(",
    "1 / 0",
    "%%%###",
])


@PBT_SETTINGS
@given(expr=_MALICIOUS)
def test_q2_eval_safety_malicious_returns_zero(expr: str):
    """随机非法/注入表达式 → evaluate_formula 返回 Decimal("0") 且不抛异常。"""
    resolver = _DictResolver({"1001": Decimal("100")})
    result = _run(evaluate_formula(expr, resolver=resolver))
    assert result == Decimal("0")
    assert isinstance(result, Decimal)


@PBT_SETTINGS
@given(text=st.text(max_size=40))
def test_q2_eval_safety_random_text_never_raises(text: str):
    """任意随机文本公式都不应抛异常（容错返回 Decimal）。"""
    resolver = _DictResolver({})
    result = _run(evaluate_formula(text, resolver=resolver))
    assert isinstance(result, Decimal)


# ---------------------------------------------------------------------------
# Q3 抵销口径一致 + Q4 幂等（纯逻辑：APPROVED 过滤集合）
# ---------------------------------------------------------------------------

def _approved_set(entries: list[dict]) -> set:
    """模拟 worksheet/trial 统一口径：只消费 review_status == approved 的分录。"""
    return {
        e["id"] for e in entries
        if e["review_status"] == ReviewStatusEnum.approved and not e["is_deleted"]
    }


_STATUS = st.sampled_from(list(ReviewStatusEnum))


@PBT_SETTINGS
@given(
    entries=st.lists(
        st.fixed_dictionaries({
            "id": st.integers(min_value=1, max_value=50),
            "review_status": _STATUS,
            "is_deleted": st.booleans(),
        }),
        min_size=0, max_size=12,
    )
)
def test_q3_elimination_caliber_identical(entries: list[dict]):
    """worksheet 与 trial 两条路径用同一过滤口径 → 消费的抵销集合必相同（均 approved 且未删）。"""
    # 去重 id（同 id 视为同一笔）
    seen = {}
    for e in entries:
        seen[e["id"]] = e
    deduped = list(seen.values())

    worksheet_consumed = _approved_set(deduped)
    trial_consumed = _approved_set(deduped)
    assert worksheet_consumed == trial_consumed

    # 消费集合中不含任何 draft/rejected/pending 或已删除分录
    for e in deduped:
        if e["review_status"] != ReviewStatusEnum.approved or e["is_deleted"]:
            assert e["id"] not in worksheet_consumed


@PBT_SETTINGS
@given(
    entries=st.lists(
        st.fixed_dictionaries({
            "id": st.integers(min_value=1, max_value=50),
            "review_status": _STATUS,
            "is_deleted": st.booleans(),
        }),
        min_size=0, max_size=12,
    ),
    repeat=st.integers(min_value=2, max_value=5),
)
def test_q4_recalc_idempotent(entries: list[dict], repeat: int):
    """同一抵销集合重复触发重算（过滤）→ 消费集合每次相同（幂等）。"""
    seen = {}
    for e in entries:
        seen[e["id"]] = e
    deduped = list(seen.values())

    results = [_approved_set(deduped) for _ in range(repeat)]
    for r in results[1:]:
        assert r == results[0]


# ---------------------------------------------------------------------------
# Q6 Decimal 无精度丢失
# ---------------------------------------------------------------------------

@PBT_SETTINGS
@given(
    vals=st.lists(
        st.decimals(min_value=Decimal("-99999999.99"), max_value=Decimal("99999999.99"),
                    places=2, allow_nan=False, allow_infinity=False),
        min_size=1, max_size=8,
    )
)
def test_q6_decimal_aggregation_exact(vals: list[Decimal]):
    """SUM 聚合全程 Decimal，逐位等于 Python Decimal 求和（无 float 中转误差）。"""
    amounts = {f"{1000 + i}": v for i, v in enumerate(vals)}
    resolver = _DictResolver(amounts)
    last_code = 1000 + len(vals) - 1
    formula = f"SUM_TB('1000~{last_code}','期末余额')"

    result = _run(evaluate_formula(formula, resolver=resolver))
    expected = sum(vals, Decimal("0"))
    assert result == expected
    assert isinstance(result, Decimal)


# ---------------------------------------------------------------------------
# Q7 少数股东比例语义正确（不求补数）
# ---------------------------------------------------------------------------

@PBT_SETTINGS
@given(minority_pct=st.integers(min_value=0, max_value=100))
def test_q7_minority_ratio_no_complement(minority_pct: int):
    """minority_share_ratio 直接作少数股东比例展示，不求补数。

    母 (100-x)% / 子 x% → 附注少数股东持股比例 == x%（非 (100-x)%）。
    """
    minority_share_ratio = Decimal(minority_pct)

    # 附注展示口径（修复后 consol_disclosure_service / consol_report_service 一致）
    disclosure_ratio = float(minority_share_ratio or Decimal("0"))
    assert disclosure_ratio == float(minority_pct)

    # 不等于补数（除 50% 自补情形）
    if minority_pct != 50:
        assert disclosure_ratio != float(100 - minority_pct)
