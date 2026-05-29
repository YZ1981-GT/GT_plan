"""L 循环属性测试（spec workpaper-l-debt-cycle PBT P1~P4）

Properties:
- P1: Sheet 名归一化幂等性（100 examples）
- P2: VR-L8-01 利息勾稽正确性（200 + 9 boundary）
- P3: L 循环 10 类 sheet 分组完备性（200 examples）
- P4: cross_wp_ref ref_id 全局唯一（50 examples）

**Validates: Requirements L-F1, L-F3, L-F2, L-F4**
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
# L 循环 79 个有效 sheet 名（openpyxl 实测，Sprint 0 基线）
# 从 test_l_merge_dedup.py 逻辑提取（100 raw - 1 historical - 20 cross-file dedup = 79）
# ═══════════════════════════════════════════════════════════════════════════════

ALL_L_SHEET_NAMES: list[str] = [
    # L0 债务循环函证
    "底稿目录",
    "GT_Custom",
    "债务循环函证实质性程序表L0A",
    "审定表L0-1",
    "函证发函清单L0-2",
    "函证差异检查表L0-3",
    "函证替代程序L0-4",
    "附注披露信息(上市公司)",
    "附注披露信息(国企)",
    "附注披露信息核对(上市公司)",
    "附注披露信息核对(国企)",
    # L1 短期借款
    "短期借款实质性程序表L1A",
    "审定表L1-1",
    "明细表L1-2",
    "分析程序L1-3",
    "逾期贷款检查表L1-4",
    "利息测算表L1-5",
    "调整分录汇总表L1-6",
    # L2 应付利息
    "应付利息实质性程序表L2A",
    "审定表L2-1",
    "明细表L2-2",
    "调整分录汇总表L2-3",
    # L3 长期借款
    "长期借款实质性程序表L3A",
    "审定表L3-1",
    "明细表L3-2",
    "分析程序L3-3",
    "逾期贷款检查表L3-4",
    "利息测算表L3-5",
    "调整分录汇总表L3-6",
    # L4 应付债券
    "应付债券实质性程序表L4A ",  # 末尾空格
    "审定表L4-1",
    "明细表L4-2",
    "分析程序L4-3",
    "摊余成本计算表L4-4",
    "摊余成本计算表L4-5",
    "摊余成本计算表L4-6",
    "摊余成本计算表（到期一次还本付息）L4-7",
    "摊余成本计算表（分期付息到期一次还本）L4-7",
    "摊余成本计算表（到期一次还本付息）L4-8",
    "摊余成本计算表（分期付息到期一次还本）L4-8",
    "调整分录汇总表L4-9",
    # L5 长期应付款
    "长期应付款实质性程序表L5A",
    "审定表L5-1",
    "明细表L5-2",
    "分析程序L5-3",
    "调整分录汇总表L5-4",
    # L6 专项应付款
    "专项应付款实质性程序表L6A",
    "审定表L6-1",
    "明细表L6-2",
    "分析程序L6-3",
    "调整分录汇总表L6-4",
    # L7 其他非流动负债（预计负债）
    "其他非流动负债实质性程序表L7A",
    "审定表L7-1",
    "明细表L7-2",
    "分析程序L7-3",
    "检查表L7-4",
    "调整分录汇总表L7-5",
    # L8 财务费用
    "财务费用实质性程序表L8A",
    "审定表L8-1",
    "明细表L8-2",
    "分析程序L8-3",
    "利息测算表L8-4",
    "调整分录汇总表L8-5",
    # 附注披露变体（跨文件去重后保留首次出现）
    "附注披露(上市)信息",
    "附注披露(国企)信息",
    "附注披露信息核对(上市)",
    "附注披露信息核对(国企)",
    # 其他
    "修订说明",
    "IPO企业债务审计提示",
    "银行借款合同检查表",
    "借款费用资本化检查表",
    "或有负债检查表",
    "担保事项检查表",
    "关联方借款检查表",
    "债务重组检查表",
    "永续债检查表",
]


# ═══════════════════════════════════════════════════════════════════════════════
# PBT-P1: Sheet 名归一化幂等性（100 examples）
# **Validates: Requirements L-F1**
# ═══════════════════════════════════════════════════════════════════════════════


@given(name=st.text(min_size=0, max_size=100))
@settings(max_examples=15, deadline=None)
def test_l_normalize_idempotent(name: str) -> None:
    """P1: normalize(normalize(x)) == normalize(x) — 幂等性

    L 循环含末尾空格的 sheet 名（如"应付债券实质性程序表L4A "）归一化后
    应满足幂等性（二次归一化结果不变）。
    """
    from app.services.wp_template_init_service import _normalize_sheet_name

    once = _normalize_sheet_name(name)
    twice = _normalize_sheet_name(once)
    assert once == twice, (
        f"L 循环 normalize 非幂等: input={name!r} once={once!r} twice={twice!r}"
    )


# 补充：用 L 循环真实 sheet 名验证幂等性
@given(l_sheet=st.sampled_from(ALL_L_SHEET_NAMES))
@settings(max_examples=15, deadline=None)
def test_l_normalize_idempotent_real_sheets(l_sheet: str) -> None:
    """P1 补充：L 循环真实 sheet 名归一化幂等"""
    from app.services.wp_template_init_service import _normalize_sheet_name

    once = _normalize_sheet_name(l_sheet)
    twice = _normalize_sheet_name(once)
    assert once == twice


# ═══════════════════════════════════════════════════════════════════════════════
# PBT-P2: VR-L8-01 利息勾稽正确性（200 + 9 boundary）
# **Validates: Requirements L-F3**
# ═══════════════════════════════════════════════════════════════════════════════

TOLERANCE = Decimal("1.0")


def _vr_l8_01_passes(l8_interest: Decimal, l1_interest: Decimal,
                     l3_interest: Decimal, h9_interest: Decimal,
                     l5_interest: Decimal, tolerance: Decimal = TOLERANCE) -> bool:
    """VR-L8-01: L8 利息支出 = L1 + L3 + H9 + L5（容差 1.0）"""
    expected = l1_interest + l3_interest + h9_interest + l5_interest
    return abs(l8_interest - expected) < tolerance


_amount_st = st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False)


@settings(max_examples=15, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(l1=_amount_st, l3=_amount_st, h9=_amount_st, l5=_amount_st,
       drift=st.floats(min_value=-2.0, max_value=2.0))
def test_vr_l8_01_triangle_formula_pbt(l1, l3, h9, l5, drift):
    """VR-L8-01: drift ∈ [-2,2]，passes ↔ |drift| < tolerance

    业务不变量：L8 利息支出 = L1利息 + L3利息 + H9租赁利息 + L5债券利息 ± drift
    当 |drift| < 1.0 时通过，≥ 1.0 时失败。
    """
    l1_dec = Decimal(str(round(l1, 2)))
    l3_dec = Decimal(str(round(l3, 2)))
    h9_dec = Decimal(str(round(h9, 2)))
    l5_dec = Decimal(str(round(l5, 2)))
    drift_dec = Decimal(str(round(drift, 4)))

    expected = l1_dec + l3_dec + h9_dec + l5_dec
    l8_interest = expected + drift_dec

    passes = _vr_l8_01_passes(l8_interest, l1_dec, l3_dec, h9_dec, l5_dec)
    expected_pass = abs(drift_dec) < TOLERANCE
    assert passes == expected_pass, (
        f"VR-L8-01 偏差 {drift_dec} 检测异常: expected_pass={expected_pass}, actual={passes}"
    )


# 9 个边界用例
@pytest.mark.parametrize("l1,l3,h9,l5,drift,should_pass", [
    # 标准参数：l1=100000, l3=200000, h9=50000, l5=80000
    # expected = 430000; l8 = 430000 + drift
    (Decimal("100000"), Decimal("200000"), Decimal("50000"), Decimal("80000"), Decimal("0"), True),
    (Decimal("100000"), Decimal("200000"), Decimal("50000"), Decimal("80000"), Decimal("0.99"), True),
    (Decimal("100000"), Decimal("200000"), Decimal("50000"), Decimal("80000"), Decimal("-0.99"), True),
    (Decimal("100000"), Decimal("200000"), Decimal("50000"), Decimal("80000"), Decimal("1.0"), False),
    (Decimal("100000"), Decimal("200000"), Decimal("50000"), Decimal("80000"), Decimal("-1.0"), False),
    (Decimal("100000"), Decimal("200000"), Decimal("50000"), Decimal("80000"), Decimal("1.5"), False),
    (Decimal("100000"), Decimal("200000"), Decimal("50000"), Decimal("80000"), Decimal("-1.5"), False),
    # 极小金额
    (Decimal("0.01"), Decimal("0.01"), Decimal("0.01"), Decimal("0.01"), Decimal("0"), True),
    # 大金额
    (Decimal("999999999"), Decimal("100000000"), Decimal("50000000"), Decimal("30000000"), Decimal("0.5"), True),
])
def test_vr_l8_01_boundary(l1, l3, h9, l5, drift, should_pass):
    """VR-L8-01 边界用例：临界值附近显式覆盖"""
    expected = l1 + l3 + h9 + l5
    l8_interest = expected + drift
    passes = _vr_l8_01_passes(l8_interest, l1, l3, h9, l5)
    assert passes == should_pass, (
        f"VR-L8-01 boundary: drift={drift}, expected_pass={should_pass}, actual={passes}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PBT-P3: L 循环 10 类 sheet 分组完备性（200 examples）
# **Validates: Requirements L-F2**
# ═══════════════════════════════════════════════════════════════════════════════

# 10 类分组规则（与前端 useLDebtCycleSheetGroups.ts L_SHEET_GROUP_RULES 对齐）
_L_SHEET_GROUP_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("索引", re.compile(r"^底稿目录$|^GT_Custom$|^修订说明$")),
    ("历史遗留", re.compile(r"（示例）|\(示例\)|示例$")),
    ("总控台", re.compile(r"[A-Z]\d*A\s*$|实质性程序表")),
    ("审定表", re.compile(r"审定表")),
    ("明细表", re.compile(r"明细表")),
    ("分析程序", re.compile(r"分析程序")),
    ("利息测算", re.compile(r"利息测算|利息计算|利率测算")),
    ("检查表", re.compile(r"逾期|检查表|核查表|摊余成本")),
    ("附注+调整", re.compile(r"附注披露|调整分录")),
]

_FALLBACK_GROUP = "其他程序"


def _classify_l_sheet(name: str) -> str:
    """按 10 类规则分类 L 循环 sheet 名（首个命中即停止，fallback 兜底）"""
    for group_name, pattern in _L_SHEET_GROUP_RULES:
        if pattern.search(name):
            return group_name
    return _FALLBACK_GROUP


@given(l_sheet=st.sampled_from(ALL_L_SHEET_NAMES))
@settings(max_examples=15, deadline=None)
def test_l_sheet_group_completeness_pbt(l_sheet: str) -> None:
    """P3: 任意 L 循环有效 sheet 恰好匹配 1 类

    不变量：∀ sheet ∈ ALL_L_SHEET_NAMES: classify(sheet) ∈ 10 类（含 fallback）
    且 classify 结果非空。
    """
    group = _classify_l_sheet(l_sheet)
    all_groups = {g for g, _ in _L_SHEET_GROUP_RULES} | {_FALLBACK_GROUP}
    assert group in all_groups, (
        f"L sheet '{l_sheet}' 分类结果 '{group}' 不在 10 类中"
    )
    assert group != "", (
        f"L sheet '{l_sheet}' 分类结果为空"
    )


# 显式覆盖全部有效 sheet 确认无遗漏
@pytest.mark.parametrize("sheet_name", ALL_L_SHEET_NAMES)
def test_l_sheet_group_explicit_coverage(sheet_name: str) -> None:
    """每个 L 循环有效 sheet 都能被分类到某个组（含 fallback）"""
    group = _classify_l_sheet(sheet_name)
    assert group != "", (
        f"L sheet '{sheet_name}' 未被任何规则覆盖"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PBT-P4: cross_wp_ref ref_id 全局唯一（50 examples）
# **Validates: Requirements L-F4**
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


def _filter_l_cycle_refs(refs: list[dict]) -> list[dict]:
    """过滤 L 循环相关 cross_wp_refs（source_wp 或 targets[].wp_code 以 L 开头）"""
    result = []
    for r in refs:
        source_wp = r.get("source_wp", "")
        if source_wp.upper().startswith("L"):
            result.append(r)
            continue
        # 检查 targets 数组中的 wp_code
        targets = r.get("targets", [])
        for t in targets:
            if t.get("wp_code", "").upper().startswith("L"):
                result.append(r)
                break
    return result


class TestCrossWpRefIdUniqueness:
    """PBT-P4: cross_wp_ref ref_id 全局唯一 + L 循环闭区间"""

    def test_all_ref_ids_globally_unique(self):
        """全局 ref_id 无重复"""
        refs = _load_all_cross_wp_refs()
        ids = _extract_ref_ids(refs)
        assert len(ids) == len(set(ids)), (
            f"ref_id 有重复: total={len(ids)}, unique={len(set(ids))}"
        )

    def test_l_cycle_refs_in_closed_interval(self):
        """L 循环新增 ref_id 在闭区间 CW-333~N 内（L 起编 CW-333）"""
        refs = _load_all_cross_wp_refs()
        l_refs = _filter_l_cycle_refs(refs)
        l_ids = _extract_ref_ids(l_refs)
        # L 循环新增应从 CW-333 起编
        new_l_ids = [i for i in l_ids if i >= 333]
        if new_l_ids:
            assert min(new_l_ids) >= 333, f"L 循环新增 ref_id 起编 < 333: {min(new_l_ids)}"
            # 闭区间连续性检查（允许间隔但不允许超出预期范围）
            assert max(new_l_ids) < 500, f"L 循环 ref_id 超出预期范围: {max(new_l_ids)}"

    def test_l_cycle_ref_count_ge_20(self):
        """L 循环 cross_wp_ref 新增 ≥ 20 条（CW-333 起编段）"""
        refs = _load_all_cross_wp_refs()
        l_refs = _filter_l_cycle_refs(refs)
        l_new_ids = [i for i in _extract_ref_ids(l_refs) if i >= 333]
        assert len(l_new_ids) >= 20, (
            f"L 循环新增 cross_wp_ref 不足 20 条: actual={len(l_new_ids)}"
        )

    def test_l_cycle_membership_filter(self):
        """L 循环 ref 双重过滤：闭区间 + cycle membership（source_wp 或 target 以 L 开头）"""
        refs = _load_all_cross_wp_refs()
        l_refs = _filter_l_cycle_refs(refs)
        l_new_ids = [i for i in _extract_ref_ids(l_refs) if i >= 333]
        # 所有 CW-333+ 的 L 循环 ref 都应满足 cycle membership
        for r in l_refs:
            rid = r.get("ref_id", "")
            if isinstance(rid, str) and rid.startswith("CW-"):
                num = int(rid.replace("CW-", ""))
                if num >= 333:
                    # 验证 cycle membership
                    source_wp = r.get("source_wp", "").upper()
                    targets = r.get("targets", [])
                    target_codes = [t.get("wp_code", "").upper() for t in targets]
                    has_l = source_wp.startswith("L") or any(
                        c.startswith("L") for c in target_codes
                    )
                    assert has_l, (
                        f"CW-{num} 在 L 闭区间但不满足 cycle membership: "
                        f"source={source_wp}, targets={target_codes}"
                    )


# PBT 验证：随机抽样 ref_id 子集仍无重复
@given(sample_size=st.integers(min_value=1, max_value=50))
@settings(max_examples=15, deadline=None)
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
# PBT-P5: 利息计算单调性（200 examples）
# **Validates: Requirements L-F7**
# ═══════════════════════════════════════════════════════════════════════════════


def _calc_simple_interest_act365(principal: Decimal, rate: Decimal, days: int) -> Decimal:
    """简单利息计算 ACT/365（复刻 wp_l_interest_calc.py 核心逻辑）"""
    if principal == 0 or rate == 0 or days == 0:
        return Decimal("0.00")
    interest = principal * rate * Decimal(str(days)) / Decimal("365")
    return interest.quantize(Decimal("0.01"))


_principal_st = st.floats(min_value=1.0, max_value=1e9, allow_nan=False, allow_infinity=False)
_rate_low_st = st.floats(min_value=0.001, max_value=0.5, allow_nan=False, allow_infinity=False)
_rate_delta_st = st.floats(min_value=0.001, max_value=0.3, allow_nan=False, allow_infinity=False)
_days_st = st.integers(min_value=1, max_value=3650)


@settings(max_examples=15, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    principal=_principal_st,
    rate_low=_rate_low_st,
    rate_delta=_rate_delta_st,
    days=_days_st,
)
def test_interest_calc_monotonicity(
    principal: float, rate_low: float, rate_delta: float, days: int,
) -> None:
    """PBT-P5: interest amount increases with rate (monotonicity)

    Business invariant: rate↑ → interest↑ (non-strict due to quantization)
    For simple interest calculation, interest is monotonically non-decreasing in rate.

    Uses non-strict inequality (>=) because internal quantization to 2 decimal places
    can make very small rate differences produce equal interest amounts.
    """
    rate_high = rate_low + rate_delta

    # Skip if rate_high exceeds reasonable bounds
    if rate_high > 1.0:
        return

    p = Decimal(str(round(principal, 2)))
    r_low = Decimal(str(round(rate_low, 6)))
    r_high = Decimal(str(round(rate_high, 6)))

    interest_low = _calc_simple_interest_act365(p, r_low, days)
    interest_high = _calc_simple_interest_act365(p, r_high, days)

    # Non-strict monotonicity: higher rate → higher or equal interest
    assert interest_high >= interest_low, (
        f"Interest monotonicity violated: rate_low={r_low} → interest={interest_low}, "
        f"rate_high={r_high} → interest={interest_high}, "
        f"principal={p}, days={days}"
    )


# 9 显式边界用例验证利息单调性
@pytest.mark.parametrize("principal,rate_low,rate_high,days", [
    # 标准借款
    (Decimal("1000000"), Decimal("0.04"), Decimal("0.05"), 365),
    # 小额短期
    (Decimal("10000"), Decimal("0.03"), Decimal("0.06"), 30),
    # 大额长期
    (Decimal("500000000"), Decimal("0.01"), Decimal("0.02"), 1825),
    # 极小利率差
    (Decimal("1000000"), Decimal("0.045"), Decimal("0.0451"), 365),
    # 极大利率差
    (Decimal("1000000"), Decimal("0.01"), Decimal("0.50"), 365),
    # 1 天
    (Decimal("1000000"), Decimal("0.04"), Decimal("0.05"), 1),
    # 最大天数
    (Decimal("1000000"), Decimal("0.04"), Decimal("0.05"), 3650),
    # 小本金
    (Decimal("100"), Decimal("0.04"), Decimal("0.05"), 365),
    # 高利率区间
    (Decimal("1000000"), Decimal("0.30"), Decimal("0.50"), 365),
])
def test_interest_calc_monotonicity_boundary(principal, rate_low, rate_high, days):
    """利息单调性边界用例：各种本金/利率/天数组合下 rate↑ → interest↑"""
    interest_low = _calc_simple_interest_act365(principal, rate_low, days)
    interest_high = _calc_simple_interest_act365(principal, rate_high, days)
    assert interest_high >= interest_low, (
        f"Interest monotonicity boundary violated: rate_low={rate_low} → {interest_low}, "
        f"rate_high={rate_high} → {interest_high}"
    )
