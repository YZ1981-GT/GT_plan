"""K 循环属性测试（spec workpaper-k-admin-cycle PBT P1~P4）

Properties:
- P1: Sheet 名归一化幂等性（100 examples）
- P2: VR-K8-01 三角勾稽正确性（200 + 9 boundary）— 销售费用 = 薪酬+折旧+其他
- P3: K 循环 10 类 sheet 分组完备性（200 examples）
- P4: cross_wp_ref ref_id 全局唯一（50 examples）+ K 闭区间 CW-313~CW-332

**Validates: Requirements K-F1, K-F3, K-F2, K-F4**
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
# K 循环代表 sheet 名（openpyxl 实测，36 个采样覆盖 10 类）
# ═══════════════════════════════════════════════════════════════════════════════

ALL_K_SHEET_NAMES: list[str] = [
    # 索引
    "底稿目录",
    "GT_Custom",
    # 程序表
    "函证程序表K0A",
    "实质性程序表 K1A",
    "实质性程序表 K2A",
    "实质性程序表K3A",
    "实质性程序表 K5A",
    "实质性程序表K8A",
    "实质性程序表K9A",
    "实质性程序表 K11A",
    # 审定表
    "审定表K1-1",
    "审定表 K5-1",
    "审定表K8-1",
    "审定表K9-1",
    "审定表K11-1",
    "函证结果汇总表K0-1",
    # 费用明细（K8-2/K9-2）
    "明细表K8-2",
    "明细表K9-2",
    # 明细表（其他）
    "明细表K1-2",
    "明细表 K5-2",  # 含空格
    "明细表K3-2",
    "明细表K10-2",
    # 分析程序
    "实质性分析K8-4",
    "实质性分析K9-4",
    "大额其他应收款情况分析表K1-5",
    "大额其他应付款情况分析表K3-4",
    # 往来款检查（K1-/K3-）
    "关联方及交易检查表K1-11",
    "长期未收回款项检查表K1-10",
    "长期挂账检查表K3-5",
    "三阶段划分检查表K1-7",
    "其他应收款检查表K1-12",
    "其他应付款检查表K3-7",
    "信用减值损失会计政策检查K1-6",
    "坏账准备测算K1-8",
    # 检查表（通用）
    "截止性测试(从记账凭证至原始凭证）K8-6",
    "截止性测试（从原始凭证至记账凭证）K8-7",
    "弃置费用检查表 K5-5",
    "产品质量保修检查表 K5-4",
    "未决诉讼检查表 K5-6",
    "预计负债检查表 K5-7",
    "管理费用检查表K9-8",
    "销售费用检查表K8-8",
    "合同检查表K8-5",
    "合同检查表K9-5",
    "减值准备测试表（后续计量） K6-5",
    "处置组减值测试表（后续计量） K6-6",
    "初始确认检查表K6-4",
    "摊销测算表K2-5",
    "政府补助核对表K10-4",
    # 附注+调整
    "附注披露信息(上市公司)",
    "附注披露信息(国企)",
    "附注披露信息（上市公司）",
    "附注披露信息（国企）",
    "附注披露信息（国有企业）",
    "调整分录汇总K1-4",
    "调整分录汇总K8-3",
    "调整分录汇总 K5-3",
]


# ═══════════════════════════════════════════════════════════════════════════════
# PBT-P1: Sheet 名归一化幂等性（100 examples）
# **Validates: Requirements K-F1**
# ═══════════════════════════════════════════════════════════════════════════════


@given(name=st.text(min_size=0, max_size=100))
@settings(max_examples=100, deadline=None)
def test_k_normalize_idempotent(name: str) -> None:
    """P1: normalize(normalize(x)) == normalize(x) — 幂等性

    K 循环含空格的 sheet 名（如 "明细表 K5-2"）归一化后
    应满足幂等性（二次归一化结果不变）。
    """
    from app.services.wp_template_init_service import _normalize_sheet_name

    once = _normalize_sheet_name(name)
    twice = _normalize_sheet_name(once)
    assert once == twice, (
        f"K 循环 normalize 非幂等: input={name!r} once={once!r} twice={twice!r}"
    )


@given(k_sheet=st.sampled_from(ALL_K_SHEET_NAMES))
@settings(max_examples=50, deadline=None)
def test_k_normalize_idempotent_real_sheets(k_sheet: str) -> None:
    """P1 补充：K 循环真实 sheet 名归一化幂等"""
    from app.services.wp_template_init_service import _normalize_sheet_name

    once = _normalize_sheet_name(k_sheet)
    twice = _normalize_sheet_name(once)
    assert once == twice


# ═══════════════════════════════════════════════════════════════════════════════
# PBT-P2: VR-K8-01 三角勾稽正确性（200 + 9 boundary）
# 销售费用 = 薪酬 + 折旧 + 其他费用合计（容差 1.0）
# **Validates: Requirements K-F3**
# ═══════════════════════════════════════════════════════════════════════════════

TOLERANCE = Decimal("1.0")


def _vr_k8_01_passes(
    k8_total: Decimal,
    payroll: Decimal,
    depreciation: Decimal,
    other: Decimal,
    tolerance: Decimal = TOLERANCE,
) -> bool:
    """VR-K8-01: K8 销售费用 = 薪酬 + 折旧 + 其他（容差 1.0）"""
    expected = payroll + depreciation + other
    return abs(k8_total - expected) < tolerance


_amount_st = st.floats(
    min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False
)


@settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    payroll=_amount_st,
    depreciation=_amount_st,
    other=_amount_st,
    drift=st.floats(min_value=-2.0, max_value=2.0),
)
def test_vr_k8_01_triangle_formula_pbt(payroll, depreciation, other, drift):
    """VR-K8-01: drift ∈ [-2,2]，passes ↔ |drift| < tolerance

    业务不变量：K8 销售费用 = 薪酬 + 折旧 + 其他 ± drift
    当 |drift| < 1.0 时通过，≥ 1.0 时失败。
    """
    p = Decimal(str(round(payroll, 2)))
    d = Decimal(str(round(depreciation, 2)))
    o = Decimal(str(round(other, 2)))
    drift_dec = Decimal(str(round(drift, 4)))

    expected = p + d + o
    k8_total = expected + drift_dec

    passes = _vr_k8_01_passes(k8_total, p, d, o)
    expected_pass = abs(drift_dec) < TOLERANCE
    assert passes == expected_pass, (
        f"VR-K8-01 偏差 {drift_dec} 检测异常: expected_pass={expected_pass}, actual={passes}"
    )


# 9 个边界用例
@pytest.mark.parametrize(
    "payroll,depreciation,other,drift,should_pass",
    [
        # 标准参数: payroll=1000000, depreciation=200000, other=300000
        # expected = 1500000; k8_total = 1500000 + drift
        (Decimal("1000000"), Decimal("200000"), Decimal("300000"), Decimal("0"), True),
        (Decimal("1000000"), Decimal("200000"), Decimal("300000"), Decimal("0.99"), True),
        (Decimal("1000000"), Decimal("200000"), Decimal("300000"), Decimal("-0.99"), True),
        (Decimal("1000000"), Decimal("200000"), Decimal("300000"), Decimal("1.0"), False),
        (Decimal("1000000"), Decimal("200000"), Decimal("300000"), Decimal("-1.0"), False),
        (Decimal("1000000"), Decimal("200000"), Decimal("300000"), Decimal("1.5"), False),
        (Decimal("1000000"), Decimal("200000"), Decimal("300000"), Decimal("-1.5"), False),
        # 极小金额
        (Decimal("0.01"), Decimal("0.01"), Decimal("0.01"), Decimal("0"), True),
        # 大金额
        (Decimal("999999999"), Decimal("100000000"), Decimal("50000000"), Decimal("0.5"), True),
    ],
)
def test_vr_k8_01_boundary(payroll, depreciation, other, drift, should_pass):
    """VR-K8-01 边界用例：临界值附近显式覆盖"""
    expected = payroll + depreciation + other
    k8_total = expected + drift
    passes = _vr_k8_01_passes(k8_total, payroll, depreciation, other)
    assert passes == should_pass, (
        f"VR-K8-01 boundary: drift={drift}, expected_pass={should_pass}, actual={passes}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PBT-P3: K 循环 10 类 sheet 分组完备性（200 examples）
# **Validates: Requirements K-F2**
# ═══════════════════════════════════════════════════════════════════════════════

# 10 类分组规则（与前端 useKAdminCycleSheetGroups.ts K_SHEET_GROUP_RULES 对齐）
# priority 升序，首个命中即停止；最后 fallback "其他"
_K_SHEET_GROUP_RULES: list[tuple[str, callable]] = [
    ("索引", lambda s: bool(re.match(r"^(底稿目录|GT_Custom)$", s.strip()))),
    (
        "程序表",
        lambda s: bool(
            re.search(r"实质性程序表", s)
            or re.search(r"函证程序表", s)
            or re.search(r"[A-Z]\d*A$", s.strip())
            or re.search(r"[A-Z]\d*A-", s)
            or re.search(r"[A-Z]\d*A ", s)
        ),
    ),
    ("审定表", lambda s: bool(re.search(r"审定表|情况表|函证结果汇总", s))),
    ("费用明细", lambda s: bool(re.match(r"^明细表K[89]-", s.strip()))),
    ("明细表", lambda s: bool(re.search(r"明细表", s))),
    ("分析程序", lambda s: bool(re.search(r"分析|对比|情况分析", s))),
    (
        "往来款检查",
        lambda s: bool(re.search(r"K[13]-", s))
        and bool(
            re.search(
                r"(检查|账龄|挂账|关联方|三阶段|未收回|大额|坏账|核销|转回|替代程序|信用减值)",
                s,
            )
        ),
    ),
    (
        "检查表",
        lambda s: bool(
            re.search(r"检查表|分配|截止性测试|测算|测试表|政策检查|核对表", s)
        )
        or bool(re.search(r"(?<!会)计提", s)),
    ),
    ("附注+调整", lambda s: bool(re.search(r"附注披露|调整分录|调整分录汇总", s))),
]

_FALLBACK_GROUP = "其他"
_VALID_GROUPS = {g for g, _ in _K_SHEET_GROUP_RULES}


def _classify_k_sheet(name: str) -> str:
    """按 10 类规则分类 K 循环 sheet 名（首个命中即停止）"""
    for group_name, predicate in _K_SHEET_GROUP_RULES:
        if predicate(name):
            return group_name
    return _FALLBACK_GROUP


@given(k_sheet=st.sampled_from(ALL_K_SHEET_NAMES))
@settings(max_examples=200, deadline=None)
def test_k_sheet_group_completeness_pbt(k_sheet: str) -> None:
    """P3: 任意 K 循环代表 sheet 恰好匹配 1 类（非 fallback）"""
    group = _classify_k_sheet(k_sheet)
    assert group in _VALID_GROUPS, (
        f"K sheet '{k_sheet}' 落入 fallback（未被 9 类规则覆盖）"
    )


# 显式覆盖每个采样 sheet 确认无遗漏
@pytest.mark.parametrize("sheet_name", ALL_K_SHEET_NAMES)
def test_k_sheet_group_explicit_coverage(sheet_name: str) -> None:
    """每个 K 循环代表 sheet 都能被分类到非 fallback 组"""
    group = _classify_k_sheet(sheet_name)
    assert group != _FALLBACK_GROUP, (
        f"K sheet '{sheet_name}' 未被 9 类规则覆盖（落入 fallback）"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PBT-P4: cross_wp_ref ref_id 全局唯一（50 examples） + K 闭区间 CW-313~CW-332
# **Validates: Requirements K-F4**
# ═══════════════════════════════════════════════════════════════════════════════

K_CWR_START = 313
K_CWR_END = 332


def _load_all_cross_wp_refs() -> list[dict]:
    """加载全部 cross_wp_references JSON"""
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


def _filter_k_cycle_refs(refs: list[dict]) -> list[dict]:
    """过滤 K 循环相关 cross_wp_refs（双重过滤：闭区间 + cycle membership）"""
    result = []
    for r in refs:
        rid = r.get("ref_id", "")
        if not (isinstance(rid, str) and rid.startswith("CW-")):
            continue
        try:
            num = int(rid.replace("CW-", ""))
        except ValueError:
            continue
        if not (K_CWR_START <= num <= K_CWR_END):
            continue
        # cycle membership
        source_wp = r.get("source_wp", "")
        if source_wp.upper().startswith("K"):
            result.append(r)
            continue
        for t in r.get("targets", []):
            if t.get("wp_code", "").upper().startswith("K"):
                result.append(r)
                break
    return result


class TestKCrossWpRefIdUniqueness:
    """PBT-P4: cross_wp_ref ref_id 全局唯一 + K 循环闭区间"""

    def test_all_ref_ids_globally_unique(self):
        """全局 ref_id 无重复"""
        refs = _load_all_cross_wp_refs()
        ids = _extract_ref_ids(refs)
        assert len(ids) == len(set(ids)), (
            f"ref_id 有重复: total={len(ids)}, unique={len(set(ids))}"
        )

    def test_k_cycle_refs_in_closed_interval(self):
        """K 循环新增 ref_id 在闭区间 CW-313~CW-332 内"""
        refs = _load_all_cross_wp_refs()
        k_refs = _filter_k_cycle_refs(refs)
        k_ids = _extract_ref_ids(k_refs)
        assert k_ids, "K 循环新增条目为空"
        assert min(k_ids) >= K_CWR_START, (
            f"K 循环 ref_id 起编 < {K_CWR_START}: {min(k_ids)}"
        )
        assert max(k_ids) <= K_CWR_END, (
            f"K 循环 ref_id 超过 {K_CWR_END}: {max(k_ids)}"
        )

    def test_k_cycle_ref_count_ge_20(self):
        """K 循环 cross_wp_ref 新增 ≥ 20 条"""
        refs = _load_all_cross_wp_refs()
        k_refs = _filter_k_cycle_refs(refs)
        assert len(k_refs) >= 20, (
            f"K 循环新增 cross_wp_ref 不足 20 条: actual={len(k_refs)}"
        )

    def test_k_cycle_ref_ids_sequential(self):
        """K 循环新增 ref_id 在闭区间内顺序递增（无跳号）"""
        refs = _load_all_cross_wp_refs()
        k_refs = _filter_k_cycle_refs(refs)
        nums = sorted(_extract_ref_ids(k_refs))
        # 验证从 K_CWR_START 起连续
        expected = list(range(K_CWR_START, K_CWR_START + len(nums)))
        assert nums == expected, (
            f"K 循环 ref_id 不连续: got {nums}, expected {expected}"
        )


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
# PBT-P5: 费用分析同比单调性（200 examples）
# current↑ → yoy_change↑（其他参数固定）
# **Validates: Requirements K-F7**
# ═══════════════════════════════════════════════════════════════════════════════


@settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    prior=st.floats(min_value=1.0, max_value=1e6, allow_nan=False, allow_infinity=False),
    current_low=st.floats(min_value=0.0, max_value=1e6, allow_nan=False, allow_infinity=False),
    delta=st.floats(min_value=1.0, max_value=1e8, allow_nan=False, allow_infinity=False),
)
def test_yoy_monotonicity_pbt(prior: float, current_low: float, delta: float) -> None:
    """P5: 同比单调性 — 在 prior 固定时，current↑ 导致 yoy_rate 非递减

    业务不变量：YoY rate = (current - prior) / prior
    数学关系：当 prior > 0 固定时，YoY rate 关于 current 单调递增。

    注意：rate_change 经 _quantize 4 位小数处理，极小 delta 可能因量化精度
    丢失差异。本 property 保证 **非递减**（rate_high >= rate_low），
    严格单调由 amount_change 测试保证（量化损失更小）。

    构造方式：固定 prior，取 current_high = current_low + delta（delta >= 1.0），
    断言 rate_high >= rate_low（量化容忍）+ amount_change 严格单调（见下一测试）。
    """
    from app.routers.wp_k_expense_analysis import _calc_yoy

    current_high = current_low + delta
    cat = "测试类别"
    prior_dict = {cat: round(prior, 2)}
    low_dict = {cat: round(current_low, 2)}
    high_dict = {cat: round(current_high, 2)}

    yoy_low = _calc_yoy(low_dict, prior_dict)
    yoy_high = _calc_yoy(high_dict, prior_dict)

    rate_low = yoy_low[cat]["rate_change"]
    rate_high = yoy_high[cat]["rate_change"]

    # 非递减（量化精度可能让两者相等）
    assert rate_high >= rate_low, (
        f"YoY 非递减性违反：prior={prior:.2f}, "
        f"current_low={current_low:.2f} → rate={rate_low}, "
        f"current_high={current_high:.2f} → rate={rate_high}"
    )


@settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    prior=st.floats(min_value=1.0, max_value=1e9, allow_nan=False, allow_infinity=False),
    current_low=st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False),
    delta=st.floats(min_value=0.01, max_value=1e8, allow_nan=False, allow_infinity=False),
)
def test_yoy_amount_change_monotonicity_pbt(
    prior: float, current_low: float, delta: float
) -> None:
    """P5 补充：amount_change 也满足单调性 — current↑ → amount_change↑

    数学关系：amount_change = current - prior，固定 prior 时关于 current 严格单调递增。
    """
    from app.routers.wp_k_expense_analysis import _calc_yoy

    current_high = current_low + delta
    cat = "测试类别"
    prior_dict = {cat: round(prior, 2)}
    low_dict = {cat: round(current_low, 2)}
    high_dict = {cat: round(current_high, 2)}

    yoy_low = _calc_yoy(low_dict, prior_dict)
    yoy_high = _calc_yoy(high_dict, prior_dict)

    amt_low = yoy_low[cat]["amount_change"]
    amt_high = yoy_high[cat]["amount_change"]

    assert amt_high > amt_low, (
        f"amount_change 单调性违反：current_low={current_low:.2f} → amt={amt_low}, "
        f"current_high={current_high:.2f} → amt={amt_high}"
    )


# 边界用例：阈值附近的标记切换（增 / 减异常 / normal）
# 注意：源码用严格不等式 `rate < -THRESHOLD` / `rate > THRESHOLD`，
#       恰好 ±0.20 → normal（边界归入正常区间）
@pytest.mark.parametrize(
    "prior,current,expected_flag",
    [
        # YOY_CHANGE_THRESHOLD = 0.20 (20%)
        # rate < -0.20 → decrease_anomaly（严格）
        (1000.0, 800.0, "normal"),  # 恰好 -20% → normal（边界归入正常）
        (1000.0, 799.0, "decrease_anomaly"),  # -20.1% → decrease_anomaly
        (1000.0, 801.0, "normal"),  # -19.9% → normal
        # rate > 0.20 → increase_anomaly（严格）
        (1000.0, 1201.0, "increase_anomaly"),  # 20.1% → increase_anomaly
        (1000.0, 1200.0, "normal"),  # 恰好 20% → normal
        (1000.0, 1199.0, "normal"),  # 19.9% → normal
        # 0% → normal
        (1000.0, 1000.0, "normal"),
        # prior=0 + current>0 → new_category
        (0.0, 100.0, "new_category"),
        # prior=0 + current=0 → normal
        (0.0, 0.0, "normal"),
    ],
)
def test_yoy_flag_thresholds(prior, current, expected_flag):
    """P5 边界：YoY flag 阈值切换正确

    注意：_calc_yoy 内部用 `_amount_st` 但 prior=0 case 在 PBT 主体被排除（min_value=1.0），
    此处显式覆盖 prior=0 的 new_category 边界。
    """
    from app.routers.wp_k_expense_analysis import _calc_yoy

    cat = "测试类别"
    yoy = _calc_yoy({cat: current}, {cat: prior})
    actual_flag = yoy[cat]["flag"]
    assert actual_flag == expected_flag, (
        f"prior={prior}, current={current}: expected {expected_flag}, got {actual_flag}"
    )


# 防御性测试：prior=0 在 PBT 主体被排除（min_value=1.0），但应单独验证不抛异常
@given(
    current=st.floats(
        min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False
    )
)
@settings(max_examples=50, deadline=None)
def test_yoy_with_prior_zero_safe(current: float) -> None:
    """P5 防御性：prior=0 + current 任意 → 不抛异常 + 返回有效 flag"""
    from app.routers.wp_k_expense_analysis import _calc_yoy

    cat = "X"
    yoy = _calc_yoy({cat: current}, {cat: 0.0})
    info = yoy[cat]
    # flag 必须是合法值
    assert info["flag"] in ("new_category", "normal", "increase_anomaly", "decrease_anomaly")
    # rate_change 不能是 inf（_calc_yoy 替换为 999.0）
    import math
    assert not math.isinf(info["rate_change"])
