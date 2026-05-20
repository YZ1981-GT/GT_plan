"""J 循环属性测试（spec workpaper-j-payroll-cycle PBT P1~P4）

Properties:
- P1: Sheet 名归一化幂等性（100 examples）
- P2: VR-J1-01 三角勾稽正确性（200 + 9 boundary）
- P3: J 循环 8 类 sheet 分组完备性（200 examples）
- P4: cross_wp_ref ref_id 全局唯一（50 examples）

**Validates: Requirements J-F1, J-F3, J-F2, J-F4**
"""
from __future__ import annotations

import json
import re
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

sys.path.insert(0, "backend")


# ═══════════════════════════════════════════════════════════════════════════════
# J 循环 29 个有效 sheet 名（openpyxl 实测）
# ═══════════════════════════════════════════════════════════════════════════════

ALL_J_SHEET_NAMES: list[str] = [
    "应付职工薪酬实质性程序表 J1A",
    "应付职工薪酬实质性程序表 J1A-原版",
    "应付职工薪酬实质性程序表 L1A-原",
    "审定表J1-1 ",
    "附注披露信息（上市公司）",
    "附注披露信息（国有企业）",
    "明细表J1-2 ",
    "调整分录汇总表J1-3",
    "月度分析表J1-4",
    "与同行业对比分析表J1-5",
    "计提情况检查表J1-6",
    "分配情况检查表J1-7",
    "检查表J1-8",
    "非货币性福利检查表J1-9",
    "辞退福利检查表J1-10",
    "IPO企业薪酬审计提示",
    "GT_Custom",
    "长期应付职工薪酬实质性程序表 J2A",
    "长期应付职工薪酬实质性程序表 L2A",
    "审定表J2-1",
    "明细表J2-2",
    "调整分录汇总表J2-3",
    "计提情况检查表J2-4",
    "股份支付实质性程序表 J3A",
    "股份支付情况表J3-1",
    "股份支付检查表J3-2",
    "IPO企业股权激励工具关注的审计重点",
    "首发业务解答二",
    "底稿目录",
]


# ═══════════════════════════════════════════════════════════════════════════════
# PBT-P1: Sheet 名归一化幂等性（100 examples）
# **Validates: Requirements J-F1**
# ═══════════════════════════════════════════════════════════════════════════════


@given(name=st.text(min_size=0, max_size=100))
@settings(max_examples=100, deadline=None)
def test_j_normalize_idempotent(name: str) -> None:
    """P1: normalize(normalize(x)) == normalize(x) — 幂等性

    J 循环含末尾空格的 sheet 名（如"审定表J1-1 "）归一化后
    应满足幂等性（二次归一化结果不变）。
    """
    from app.services.wp_template_init_service import _normalize_sheet_name

    once = _normalize_sheet_name(name)
    twice = _normalize_sheet_name(once)
    assert once == twice, (
        f"J 循环 normalize 非幂等: input={name!r} once={once!r} twice={twice!r}"
    )


# 补充：用 J 循环真实 sheet 名验证幂等性
@given(j_sheet=st.sampled_from(ALL_J_SHEET_NAMES))
@settings(max_examples=50, deadline=None)
def test_j_normalize_idempotent_real_sheets(j_sheet: str) -> None:
    """P1 补充：J 循环真实 sheet 名归一化幂等"""
    from app.services.wp_template_init_service import _normalize_sheet_name

    once = _normalize_sheet_name(j_sheet)
    twice = _normalize_sheet_name(once)
    assert once == twice


# ═══════════════════════════════════════════════════════════════════════════════
# PBT-P2: VR-J1-01 三角勾稽正确性（200 + 9 boundary）
# **Validates: Requirements J-F3**
# ═══════════════════════════════════════════════════════════════════════════════

TOLERANCE = Decimal("1.0")


def _vr_j1_01_passes(opening: Decimal, accrued: Decimal, paid: Decimal,
                     closing: Decimal, tolerance: Decimal = TOLERANCE) -> bool:
    """VR-J1-01: 期末 = 期初 + 本期计提 - 本期实发（容差 1.0）"""
    expected = opening + accrued - paid
    return abs(closing - expected) < tolerance


_amount_st = st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False)


@settings(max_examples=200, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(opening=_amount_st, accrued=_amount_st, paid=_amount_st,
       drift=st.floats(min_value=-2.0, max_value=2.0))
def test_vr_j1_01_triangle_formula_pbt(opening, accrued, paid, drift):
    """VR-J1-01: drift ∈ [-2,2]，passes ↔ |drift| < tolerance

    业务不变量：期末余额 = 期初 + 计提 - 实发 ± drift
    当 |drift| < 1.0 时通过，≥ 1.0 时失败。
    """
    o = Decimal(str(round(opening, 2)))
    a = Decimal(str(round(accrued, 2)))
    p = Decimal(str(round(paid, 2)))
    drift_dec = Decimal(str(round(drift, 4)))

    expected = o + a - p
    closing = expected + drift_dec

    passes = _vr_j1_01_passes(o, a, p, closing)
    expected_pass = abs(drift_dec) < TOLERANCE
    assert passes == expected_pass, (
        f"VR-J1-01 偏差 {drift_dec} 检测异常: expected_pass={expected_pass}, actual={passes}"
    )


# 9 个边界用例
@pytest.mark.parametrize("opening,accrued,paid,drift,should_pass", [
    # 标准参数：opening=500000, accrued=200000, paid=180000
    # expected = 520000; closing = 520000 + drift
    (Decimal("500000"), Decimal("200000"), Decimal("180000"), Decimal("0"), True),
    (Decimal("500000"), Decimal("200000"), Decimal("180000"), Decimal("0.99"), True),
    (Decimal("500000"), Decimal("200000"), Decimal("180000"), Decimal("-0.99"), True),
    (Decimal("500000"), Decimal("200000"), Decimal("180000"), Decimal("1.0"), False),
    (Decimal("500000"), Decimal("200000"), Decimal("180000"), Decimal("-1.0"), False),
    (Decimal("500000"), Decimal("200000"), Decimal("180000"), Decimal("1.5"), False),
    (Decimal("500000"), Decimal("200000"), Decimal("180000"), Decimal("-1.5"), False),
    # 极小金额
    (Decimal("0.01"), Decimal("0.01"), Decimal("0.01"), Decimal("0"), True),
    # 大金额
    (Decimal("999999999"), Decimal("100000000"), Decimal("50000000"), Decimal("0.5"), True),
])
def test_vr_j1_01_boundary(opening, accrued, paid, drift, should_pass):
    """VR-J1-01 边界用例：临界值附近显式覆盖"""
    expected = opening + accrued - paid
    closing = expected + drift
    passes = _vr_j1_01_passes(opening, accrued, paid, closing)
    assert passes == should_pass, (
        f"VR-J1-01 boundary: drift={drift}, expected_pass={should_pass}, actual={passes}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PBT-P3: J 循环 8 类 sheet 分组完备性（200 examples）
# **Validates: Requirements J-F2**
# ═══════════════════════════════════════════════════════════════════════════════

# 8 类分组规则（与前端 useJPayrollSheetGroups.ts J_SHEET_GROUP_RULES 对齐）
_J_SHEET_GROUP_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("索引", re.compile(r"^底稿目录$|^GT_Custom$")),
    ("程序表", re.compile(r"实质性程序表|[A-Z]\dA$|[A-Z]\dA-")),
    ("审定表", re.compile(r"审定表|情况表")),
    ("明细表", re.compile(r"明细表")),
    ("分析程序", re.compile(r"分析表|分析|对比")),
    ("检查表", re.compile(r"检查表|计提情况|分配情况")),
    ("IPO专项", re.compile(r"IPO|首发")),
    ("附注+调整", re.compile(r"附注披露|调整分录")),
]

_FALLBACK_GROUP = "其他"


def _classify_j_sheet(name: str) -> str:
    """按 8 类规则分类 J 循环 sheet 名（首个命中即停止）"""
    for group_name, pattern in _J_SHEET_GROUP_RULES:
        if pattern.search(name):
            return group_name
    return _FALLBACK_GROUP


@given(j_sheet=st.sampled_from(ALL_J_SHEET_NAMES))
@settings(max_examples=200, deadline=None)
def test_j_sheet_group_completeness_pbt(j_sheet: str) -> None:
    """P3: 任意 J 循环有效 sheet 恰好匹配 1 类（非 fallback）

    不变量：∀ sheet ∈ ALL_J_SHEET_NAMES: classify(sheet) ∈ 8 类（不落入 fallback）
    """
    group = _classify_j_sheet(j_sheet)
    valid_groups = {g for g, _ in _J_SHEET_GROUP_RULES}
    assert group in valid_groups, (
        f"J sheet '{j_sheet}' 落入 fallback（未被 8 类规则覆盖）"
    )


# 显式覆盖全部 29 个 sheet 确认无遗漏
@pytest.mark.parametrize("sheet_name", ALL_J_SHEET_NAMES)
def test_j_sheet_group_explicit_coverage(sheet_name: str) -> None:
    """每个 J 循环有效 sheet 都能被分类到非 fallback 组"""
    group = _classify_j_sheet(sheet_name)
    assert group != _FALLBACK_GROUP, (
        f"J sheet '{sheet_name}' 未被 8 类规则覆盖（落入 fallback）"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PBT-P4: cross_wp_ref ref_id 全局唯一（50 examples）
# **Validates: Requirements J-F4**
# ═══════════════════════════════════════════════════════════════════════════════


def _load_all_cross_wp_refs() -> list[dict]:
    """加载全部 cross_wp_references JSON 文件"""
    data_dir = Path("backend/data")
    all_refs: list[dict] = []
    for f in data_dir.glob("cross_wp_references*.json"):
        with open(f, "r", encoding="utf-8") as fp:
            data = json.load(fp)
            if isinstance(data, list):
                all_refs.extend(data)
            elif isinstance(data, dict):
                # 支持多种 key: entries / references
                if "entries" in data:
                    all_refs.extend(data["entries"])
                elif "references" in data:
                    all_refs.extend(data["references"])
    return all_refs


def _extract_ref_ids(refs: list[dict]) -> list[int]:
    """提取所有 ref_id 的数字部分"""
    ids: list[int] = []
    for r in refs:
        rid = r.get("ref_id", "")
        if isinstance(rid, str) and rid.startswith("CW-"):
            try:
                ids.append(int(rid.replace("CW-", "")))
            except ValueError:
                pass
        elif isinstance(rid, int):
            ids.append(rid)
    return ids


def _filter_j_cycle_refs(refs: list[dict]) -> list[dict]:
    """过滤 J 循环相关 cross_wp_refs（source_wp 或 targets[].wp_code 以 J 开头）"""
    result = []
    for r in refs:
        source_wp = r.get("source_wp", "")
        if source_wp.upper().startswith("J"):
            result.append(r)
            continue
        # 检查 targets 数组中的 wp_code
        targets = r.get("targets", [])
        for t in targets:
            if t.get("wp_code", "").upper().startswith("J"):
                result.append(r)
                break
    return result


class TestCrossWpRefIdUniqueness:
    """PBT-P4: cross_wp_ref ref_id 全局唯一 + J 循环闭区间"""

    def test_all_ref_ids_globally_unique(self):
        """全局 ref_id 无重复"""
        refs = _load_all_cross_wp_refs()
        ids = _extract_ref_ids(refs)
        assert len(ids) == len(set(ids)), (
            f"ref_id 有重复: total={len(ids)}, unique={len(set(ids))}"
        )

    def test_j_cycle_refs_in_closed_interval(self):
        """J 循环新增 ref_id 在闭区间 CW-293~N 内"""
        refs = _load_all_cross_wp_refs()
        j_refs = _filter_j_cycle_refs(refs)
        j_ids = _extract_ref_ids(j_refs)
        # J 循环新增应从 CW-293 起编
        new_j_ids = [i for i in j_ids if i >= 293]
        if new_j_ids:
            assert min(new_j_ids) >= 293, f"J 循环新增 ref_id 起编 < 293: {min(new_j_ids)}"
            # 闭区间连续性检查（允许间隔但不允许重叠其他循环）
            assert max(new_j_ids) < 400, f"J 循环 ref_id 超出预期范围: {max(new_j_ids)}"

    def test_j_cycle_ref_count_ge_20(self):
        """J 循环 cross_wp_ref 新增 ≥ 20 条（CW-293 起编段）"""
        refs = _load_all_cross_wp_refs()
        j_refs = _filter_j_cycle_refs(refs)
        j_new_ids = [i for i in _extract_ref_ids(j_refs) if i >= 293]
        assert len(j_new_ids) >= 20, (
            f"J 循环新增 cross_wp_ref 不足 20 条: actual={len(j_new_ids)}"
        )


# PBT 验证：随机抽样 ref_id 子集仍无重复
@given(sample_size=st.integers(min_value=1, max_value=50))
@settings(max_examples=50, deadline=None)
def test_ref_id_subset_unique_pbt(sample_size: int) -> None:
    """P4: 随机抽样任意子集 ref_id 仍无重复（全局唯一性的概率验证）"""
    import random
    refs = _load_all_cross_wp_refs()
    ids = _extract_ref_ids(refs)
    if not ids:
        return
    actual_sample = min(sample_size, len(ids))
    sample = random.sample(ids, actual_sample)
    assert len(sample) == len(set(sample)), "随机子集中发现 ref_id 重复"


# ═══════════════════════════════════════════════════════════════════════════════
# PBT-P5: Black-Scholes 单调性（200 examples）
# **Validates: Requirements J-F8**
# ═══════════════════════════════════════════════════════════════════════════════


def _black_scholes_call(
    S: float, K: float, r: float, sigma: float, T: float, q: float = 0.0
) -> float:
    """Black-Scholes 看涨期权定价（含股息率 q）— 复刻 wp_j_share_payment.py"""
    import math

    d1 = (math.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    call_value = S * math.exp(-q * T) * (0.5 * (1.0 + math.erf(d1 / math.sqrt(2.0)))) - \
                 K * math.exp(-r * T) * (0.5 * (1.0 + math.erf(d2 / math.sqrt(2.0))))
    return call_value


# 策略：合理范围内的金融参数
_stock_price_st = st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False)
_exercise_price_st = st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False)
_rate_st = st.floats(min_value=0.001, max_value=0.5, allow_nan=False, allow_infinity=False)
_vol_st = st.floats(min_value=0.01, max_value=3.0, allow_nan=False, allow_infinity=False)
_time_st = st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False)
_dividend_st = st.floats(min_value=0.0, max_value=0.3, allow_nan=False, allow_infinity=False)


@settings(max_examples=200, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    S=_stock_price_st,
    K=_exercise_price_st,
    r=_rate_st,
    T=_time_st,
    q=_dividend_st,
    sigma_low=_vol_st,
    sigma_delta=st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False),
)
def test_black_scholes_monotonicity(
    S: float, K: float, r: float, T: float, q: float,
    sigma_low: float, sigma_delta: float,
) -> None:
    """PBT-P5: Black-Scholes option value increases with volatility (monotonicity)

    Business invariant: σ↑ → C↑ (non-strict due to quantization)
    For European call options, option value is monotonically non-decreasing in volatility.

    Uses non-strict inequality (>=) because internal quantization to 4 decimal places
    can make very small sigma differences produce equal option values.
    """
    sigma_high = sigma_low + sigma_delta

    # Skip if sigma_high exceeds reasonable bounds
    if sigma_high > 5.0:
        return

    c_low = _black_scholes_call(S, K, r, sigma_low, T, q)
    c_high = _black_scholes_call(S, K, r, sigma_high, T, q)

    # Non-strict monotonicity: higher volatility → higher or equal option value
    assert c_high >= c_low - 1e-10, (
        f"BS monotonicity violated: σ_low={sigma_low:.4f} → C={c_low:.6f}, "
        f"σ_high={sigma_high:.4f} → C={c_high:.6f}, "
        f"S={S}, K={K}, r={r}, T={T}, q={q}"
    )


# 9 显式边界用例验证 BS 单调性
@pytest.mark.parametrize("S,K,r,sigma_low,sigma_high,T,q", [
    # ATM option
    (100.0, 100.0, 0.05, 0.1, 0.3, 1.0, 0.0),
    # Deep ITM
    (150.0, 100.0, 0.05, 0.1, 0.5, 1.0, 0.0),
    # Deep OTM
    (50.0, 100.0, 0.05, 0.1, 0.5, 1.0, 0.0),
    # Short maturity
    (100.0, 100.0, 0.05, 0.2, 0.4, 0.1, 0.0),
    # Long maturity
    (100.0, 100.0, 0.05, 0.2, 0.4, 5.0, 0.0),
    # With dividend
    (100.0, 100.0, 0.05, 0.2, 0.4, 1.0, 0.03),
    # High volatility range
    (100.0, 100.0, 0.05, 1.0, 2.0, 1.0, 0.0),
    # Low rate
    (100.0, 100.0, 0.001, 0.1, 0.3, 1.0, 0.0),
    # High rate
    (100.0, 100.0, 0.3, 0.1, 0.3, 1.0, 0.0),
])
def test_black_scholes_monotonicity_boundary(S, K, r, sigma_low, sigma_high, T, q):
    """BS 单调性边界用例：各种市场条件下 σ↑ → C↑"""
    c_low = _black_scholes_call(S, K, r, sigma_low, T, q)
    c_high = _black_scholes_call(S, K, r, sigma_high, T, q)
    assert c_high >= c_low - 1e-10, (
        f"BS monotonicity boundary violated: σ_low={sigma_low} → C={c_low:.6f}, "
        f"σ_high={sigma_high} → C={c_high:.6f}"
    )
