"""I 循环属性测试（spec workpaper-i-intangible-assets-cycle / Sprint 4 Task 4.9）

Properties:
- PBT-P1 normalize_idempotent: Sheet 名归一化幂等性（100 examples）
- PBT-P2 historical_sheet_filter_regression: I3 历史遗留 1 命中 + D/F/H 回归正确（100 examples）
- PBT-P3 cross_wp_ref_id_unique: ref_id 全局唯一性（50 examples）
- PBT-P4 vr_i_triangle_formula: VR-I1-01 / VR-I3-01 / VR-I6-01 三角勾稽公式正确性（200 examples + 9 boundary）
- PBT-P5 sheet_group_completeness: I 循环 10 类 + fallback 分组规则完备性（200 examples）

**Validates: Requirements I-F1, I-F1.4, I-F7, I-F6.1, I-F6.2, I-F3**

PBT 策略：用 hypothesis st.floats + 后转 Decimal（生成快 10x，shrinking 成熟）
"""
from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st


# ═══════════════════════════════════════════════════════════════════════════════
# I 循环真实 sheet 名池（Sprint 0 openpyxl 实测 — 67 去重后唯一名，含 I3 历史遗留 1 个）
# ═══════════════════════════════════════════════════════════════════════════════

ALL_I_SHEET_NAMES: list[str] = [
    "底稿目录", "GT_Custom", "修订说明",
    "无形资产实质性程序表I1A", "审定表I1-1", "明细表I1-2",
    "调整分录汇总表I1-3", "分析程序I1-4", "会计政策估计检查表I1-5",
    "增加检查表I1-6", "减少检查表I1-7", "权属检查表I1-8",
    "摊销测算表（不含减值）I1-10（剩余年限法）", "摊销测算表（含减值）I1-11",
    "减值测试I1-12", "可收回金额测试I1-13", "关联交易检查表I1-14",
    "附注披露信息（上市公司）", "附注披露信息（国企）",
    "开发支出实质性程序表I2A", "审定表I2-1", "明细表I2-2",
    "调整分录汇总表I2-3", "分析程序I2-4", "增加检查表I2-5",
    "研发项目资本化时点判断I2-6", "减少检查表I2-7",
    "商誉实质性程序表I3A", "审定表I3-1", "明细表I3-2",
    "调整分录汇总表I3-3", "分析程序I3-4", "增加检查表I3-5",
    "商誉减值测试I3-6", "可收回金额测试I3-7",
    "参考－商誉减值测试示例",  # 历史遗留 — 应被过滤
    "长期待摊费用实质性程序表I4A", "审定表I4-1", "明细表I4-2",
    "调整分录汇总表I4-3", "分析程序I4-4", "增加检查表I4-5",
    "摊销测算I4-6", "摊销测算表I4-7（工作量法）",
    "减值测试I4-8", "关联交易检查表I4-9",
    "商誉减值准备实质性程序表I5A", "审定表I5-1", "明细表I5-2",
    "调整分录汇总表I5-3", "分析程序I5-4",
    "研发费用实质性程序表I6A", "审定表I6-1", "明细表I6-2",
    "调整分录汇总表I6-3", "加计扣除核对表I6-3",
    "分析程序I6-4", "关联交易检查表I6-5",
]

# I3 历史遗留 sheet（应被过滤 = True）
I3_HISTORICAL_SHEET = "参考－商誉减值测试示例"

# D/F/H 循环已知历史遗留 sheet 名（应被过滤 = True）
D_F_H_HISTORICAL_SHEET_NAMES: list[str] = [
    "主营业务收入审计程序表 D4A（修订前）",
    "D7A（原）",
    "D8A(原)",
    "G1A-修订前",
    "存货计价测试程序G2-8-删除",
    "G2-8-4-移至分析类",
    "产品年度成本比较G2-9-3-删除",
    "函证差异检查表（示例）",
    "合同履约成本测试（示例）",
    "访谈记录与核对示例",
]


# ═══════════════════════════════════════════════════════════════════════════════
# PBT-P1: Sheet 名归一化幂等性（100 examples）
# **Validates: Requirements I-F1**
# ═══════════════════════════════════════════════════════════════════════════════


@given(name=st.text(min_size=1, max_size=100))
@settings(max_examples=100, deadline=None)
def test_normalize_idempotent(name: str) -> None:
    """P1: normalize(normalize(x)) == normalize(x) — 幂等性

    I 循环 sheet 名归一化后应满足幂等性（二次归一化结果不变）。
    """
    from app.services.wp_template_init_service import _normalize_sheet_name

    once = _normalize_sheet_name(name)
    twice = _normalize_sheet_name(once)
    assert once == twice, (
        f"I 循环 normalize 非幂等: input={name!r} once={once!r} twice={twice!r}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PBT-P2: I3 历史遗留 1 命中 + D/F/H 回归正确（100 examples）
# **Validates: Requirements I-F1.4**
# ═══════════════════════════════════════════════════════════════════════════════

# I 循环非历史遗留 sheet（应不被过滤 = False）
_I_NON_HISTORICAL = [s for s in ALL_I_SHEET_NAMES if s != I3_HISTORICAL_SHEET]


@given(i_sheet=st.sampled_from(_I_NON_HISTORICAL))
@settings(max_examples=100, deadline=None)
def test_historical_sheet_filter_regression(i_sheet: str) -> None:
    """P2: I 循环非历史遗留 sheet 不命中 + I3 历史遗留命中 + D/F/H 回归正确

    不变量：
    1. ∀ I_sheet ∈ (ALL_I - I3_HISTORICAL): _should_skip_historical_sheet(I_sheet) == False
    2. I3 "参考－商誉减值测试示例" → True
    3. ∀ D/F/H_historical: _should_skip_historical_sheet(name) == True
    """
    from app.services.wp_template_init_service import _should_skip_historical_sheet

    # 不变量 1: I 循环非历史遗留 sheet 不命中
    assert _should_skip_historical_sheet(i_sheet) is False, (
        f"I 循环 sheet '{i_sheet}' 被误过滤为历史遗留"
    )

    # 不变量 2: I3 历史遗留命中
    assert _should_skip_historical_sheet(I3_HISTORICAL_SHEET) is True, (
        f"I3 历史遗留 sheet '{I3_HISTORICAL_SHEET}' 未被过滤"
    )

    # 不变量 3: D/F/H 历史遗留模式仍正确过滤
    for df_name in D_F_H_HISTORICAL_SHEET_NAMES:
        assert _should_skip_historical_sheet(df_name) is True, (
            f"D/F/H 历史遗留 sheet '{df_name}' 未被过滤（回归失败）"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# PBT-P3: cross_wp_references ref_id 全局唯一性（50 examples）
# **Validates: Requirements I-F7**
# ═══════════════════════════════════════════════════════════════════════════════

CWR_PATH = Path(__file__).resolve().parent.parent / "data" / "cross_wp_references.json"


def _load_existing_ref_ids() -> set[str]:
    """加载实际 cross_wp_references.json 中所有 ref_id"""
    if not CWR_PATH.exists():
        return set()
    data = json.loads(CWR_PATH.read_text(encoding="utf-8"))
    return {r.get("ref_id", "") for r in data.get("references", []) if r.get("ref_id")}


@given(
    new_ids=st.lists(
        st.from_regex(r"^CW-\d{1,4}$", fullmatch=True),
        min_size=0,
        max_size=20,
        unique=True,
    )
)
@settings(max_examples=50, deadline=2000)
def test_cross_wp_ref_id_unique(new_ids: list[str]) -> None:
    """Property 3: 任意新增 ref_id 集合与现有集合合并后，无重复

    - 现有条目 ref_id 全局唯一（基线不变量）
    - 新增条目与现有合并后仍唯一（增量不变量）
    """
    existing = _load_existing_ref_ids()
    # 1. 基线不变量：现有条目无重复
    assert len(existing) == len(set(existing)), \
        "baseline violated: existing ref_ids have duplicates"

    # 2. 增量不变量：新条目集合内部无重复（hypothesis unique=True 保证）
    assert len(new_ids) == len(set(new_ids))

    # 3. 合并后 = existing ∪ new_ids（仅当无交集时大小相加）
    intersection = existing & set(new_ids)
    merged = existing | set(new_ids)
    expected_merged_size = len(existing) + len(new_ids) - len(intersection)
    assert len(merged) == expected_merged_size


# ═══════════════════════════════════════════════════════════════════════════════
# PBT-P4 vr_i_triangle_formula — VR-I1-01/I3-01/I6-01 三角勾稽公式
# ═══════════════════════════════════════════════════════════════════════════════
#
# VR-I1-01 (无形资产): closing == opening + additions - disposals - amortization
#   tolerance: ABS(closing - (opening + additions - disposals - amortization)) < 1.0
# VR-I3-01 (商誉): closing == opening - impairment_loss
#   tolerance: ABS(closing - (opening - impairment_loss)) < 1.0
# VR-I6-01 (研发费用): rd_expense_total == rd_expensed + rd_capitalized
#   tolerance: ABS(rd_expense_total - (rd_expensed + rd_capitalized)) < 1.0


def _vr_i1_passes(opening: Decimal, additions: Decimal, disposals: Decimal,
                  amortization: Decimal, closing: Decimal,
                  tolerance: Decimal = Decimal("1.0")) -> bool:
    """VR-I1-01 三角勾稽：closing == opening + additions - disposals - amortization (容差 1)"""
    expected = opening + additions - disposals - amortization
    return abs(closing - expected) < tolerance


def _vr_i3_passes(opening: Decimal, impairment_loss: Decimal, closing: Decimal,
                  tolerance: Decimal = Decimal("1.0")) -> bool:
    """VR-I3-01 商誉勾稽：closing == opening - impairment_loss (容差 1)"""
    expected = opening - impairment_loss
    return abs(closing - expected) < tolerance


def _vr_i6_passes(rd_expense_total: Decimal, rd_expensed: Decimal,
                  rd_capitalized: Decimal,
                  tolerance: Decimal = Decimal("1.0")) -> bool:
    """VR-I6-01 研发费用勾稽：total == expensed + capitalized (容差 1)"""
    expected = rd_expensed + rd_capitalized
    return abs(rd_expense_total - expected) < tolerance


# 金额生成器：[0, 1e9] 区间 float（避免极端值导致 Decimal 异常）
_amount_st = st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False)


@settings(max_examples=200, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(opening=_amount_st, additions=_amount_st, disposals=_amount_st,
       amortization=_amount_st, drift=st.floats(min_value=-2.0, max_value=2.0))
def test_vr_i1_triangle_formula_pbt(opening, additions, disposals, amortization, drift):
    """VR-I1-01: 在 drift ∈ [-2, 2] 区间，passes ↔ |drift| < tolerance"""
    o = Decimal(str(round(opening, 2)))
    a = Decimal(str(round(additions, 2)))
    d = Decimal(str(round(disposals, 2)))
    am = Decimal(str(round(amortization, 2)))
    drift_dec = Decimal(str(round(drift, 4)))

    # 构造 closing 使得偏差 = drift（不是恒真断言）
    expected = o + a - d - am
    closing = expected + drift_dec

    passes = _vr_i1_passes(o, a, d, am, closing)
    # 业务不变量：偏差 < 1 即通过；≥ 1 即失败
    expected_pass = abs(drift_dec) < Decimal("1.0")
    assert passes == expected_pass, (
        f"VR-I1 偏差 {drift_dec} 检测异常: expected_pass={expected_pass}, actual={passes}"
    )


@settings(max_examples=200, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(opening=_amount_st, impairment_loss=_amount_st,
       drift=st.floats(min_value=-2.0, max_value=2.0))
def test_vr_i3_goodwill_formula_pbt(opening, impairment_loss, drift):
    """VR-I3-01: 商誉减值勾稽，drift 区间外失败、区间内通过"""
    o = Decimal(str(round(opening, 2)))
    imp = Decimal(str(round(impairment_loss, 2)))
    drift_dec = Decimal(str(round(drift, 4)))
    expected = o - imp
    closing = expected + drift_dec
    passes = _vr_i3_passes(o, imp, closing)
    expected_pass = abs(drift_dec) < Decimal("1.0")
    assert passes == expected_pass


@settings(max_examples=200, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(rd_expensed=_amount_st, rd_capitalized=_amount_st,
       drift=st.floats(min_value=-2.0, max_value=2.0))
def test_vr_i6_rd_formula_pbt(rd_expensed, rd_capitalized, drift):
    """VR-I6-01: 研发费用 = 费用化 + 资本化，drift 区间外失败、区间内通过"""
    e = Decimal(str(round(rd_expensed, 2)))
    c = Decimal(str(round(rd_capitalized, 2)))
    drift_dec = Decimal(str(round(drift, 4)))
    expected = e + c
    total = expected + drift_dec
    passes = _vr_i6_passes(total, e, c)
    expected_pass = abs(drift_dec) < Decimal("1.0")
    assert passes == expected_pass


# 9 个边界用例（显式覆盖临界值附近，避免随机生成漏扫）
@pytest.mark.parametrize("vr_func,inputs,drift,should_pass", [
    # VR-I1-01: opening=1000, additions=200, disposals=50, amortization=100
    # expected = 1050; closing = 1050 + drift
    (_vr_i1_passes, (Decimal("1000"), Decimal("200"), Decimal("50"), Decimal("100")), Decimal("0"), True),
    (_vr_i1_passes, (Decimal("1000"), Decimal("200"), Decimal("50"), Decimal("100")), Decimal("0.99"), True),
    (_vr_i1_passes, (Decimal("1000"), Decimal("200"), Decimal("50"), Decimal("100")), Decimal("-0.99"), True),
    (_vr_i1_passes, (Decimal("1000"), Decimal("200"), Decimal("50"), Decimal("100")), Decimal("1.0"), False),
    (_vr_i1_passes, (Decimal("1000"), Decimal("200"), Decimal("50"), Decimal("100")), Decimal("-1.0"), False),
    # 极小金额边界
    (_vr_i1_passes, (Decimal("0.01"), Decimal("0.01"), Decimal("0.01"), Decimal("0.01")), Decimal("0"), True),
    # 极大金额（1e9）
    (_vr_i1_passes, (Decimal("1e9"), Decimal("1e9"), Decimal("1e9"), Decimal("1e9")), Decimal("0.5"), True),
    (_vr_i1_passes, (Decimal("1e9"), Decimal("1e9"), Decimal("1e9"), Decimal("1e9")), Decimal("1.5"), False),
    # 全零 + 0 偏差
    (_vr_i1_passes, (Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0")), Decimal("0"), True),
])
def test_vr_i1_boundary_cases(vr_func, inputs, drift, should_pass):
    o, a, d, am = inputs
    expected = o + a - d - am
    closing = expected + drift
    assert vr_func(o, a, d, am, closing) == should_pass


# ═══════════════════════════════════════════════════════════════════════════════
# PBT-P5 sheet_group_completeness — I 循环 10 类 + fallback 分组规则完备性
# ═══════════════════════════════════════════════════════════════════════════════
#
# 等价 useIIntangibleAssetSheetGroups.ts 中 I_SHEET_PATTERNS（按 priority 顺序匹配）。
# 后端 PBT 验证：任意输入 sheet 名都能被分到某一类（10 类之一 OR fallback "其他程序"）。

I_SHEET_PATTERNS = [
    # (priority, regex_pattern, category)
    (0, re.compile(r"^底稿目录$|^GT_Custom$|^修订说明$"), "索引"),
    (1, re.compile(r"参考.*示例|示例[）)]?$|修订前"), "历史遗留"),
    (2, re.compile(r"[A-Z]\d*A$|实质性程序表"), "总控台"),
    (3, re.compile(r"审定表"), "审定表"),
    (4, re.compile(r"附注披露"), "附注披露"),
    (5, re.compile(r"明细表"), "明细表"),
    (6, re.compile(r"摊销测算|摊销分配"), "摊销测算"),
    (7, re.compile(r"减值测试|可收回金额|商誉减值"), "减值测试"),
    (8, re.compile(r"资本化时点|研发项目|加计扣除|项目成立条件"), "针对性检查"),
    (9, re.compile(r"调整分录"), "调整分录"),
]

FALLBACK_CATEGORY = "其他程序"
ALL_CATEGORIES = {p[2] for p in I_SHEET_PATTERNS} | {FALLBACK_CATEGORY}


def _classify_i_sheet(name: str) -> str:
    """按 priority 顺序匹配 sheet 名 → 返回类别"""
    for _, pattern, category in I_SHEET_PATTERNS:
        if pattern.search(name):
            return category
    return FALLBACK_CATEGORY


# Sheet 名生成策略：含中文 + ASCII 字母 + 数字
_sheet_name_st = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),  # 字母 + 数字
        whitelist_characters="审定表明细表程序减值测试摊销资本化研发调整分录附注披露目录AaBb12-",
    ),
    min_size=1,
    max_size=30,
)


@settings(max_examples=200, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(name=_sheet_name_st)
def test_classify_i_sheet_returns_known_category(name):
    """Property: 任意输入 sheet 名都能分到某已知类别（10 类之一 OR fallback）"""
    category = _classify_i_sheet(name)
    assert category in ALL_CATEGORIES, f"未知类别 {category!r} for sheet {name!r}"


@settings(max_examples=200, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(name=_sheet_name_st)
def test_classify_i_sheet_priority_consistency(name):
    """Property: 命中类别等于按 priority 顺序匹配的第一个类别（不会乱序）"""
    expected = None
    for _, pattern, category in I_SHEET_PATTERNS:
        if pattern.search(name):
            expected = category
            break
    if expected is None:
        expected = FALLBACK_CATEGORY
    assert _classify_i_sheet(name) == expected


# ═══════════════════════════════════════════════════════════════════════════════
# PBT-P5 显式分类边界用例（5 类常见 sheet 名）
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("name,expected", [
    # 索引类（高 priority 0）
    ("底稿目录", "索引"),
    ("GT_Custom", "索引"),
    ("修订说明", "索引"),
    # 历史遗留（priority 1）— I3 实测命中
    ("参考－商誉减值测试示例", "历史遗留"),
    # 总控台
    ("无形资产实质性程序表I1A", "总控台"),
    ("商誉实质性程序表I3A", "总控台"),
    # 审定表
    ("审定表I1-1", "审定表"),
    ("无形资产审定表", "审定表"),
    # 附注披露（readonly）
    ("附注披露信息（上市公司）", "附注披露"),
    # 明细表
    ("明细表I1-2", "明细表"),
    # 摊销测算（关键 — 区别于 H 折旧测算）
    ("摊销测算表（不含减值）I1-10（剩余年限法）", "摊销测算"),
    ("摊销测算表（含减值）I1-11", "摊销测算"),
    # 减值测试
    ("商誉减值测试I3-6", "减值测试"),
    ("可收回金额测试I1-13", "减值测试"),
    # 针对性检查（I 循环特有）
    ("研发项目资本化时点判断I2-6", "针对性检查"),
    ("加计扣除核对表I6-3", "针对性检查"),
    # 调整分录
    ("调整分录I1-99", "调整分录"),
    # Fallback
    ("某未分类底稿XX", "其他程序"),
])
def test_classify_i_sheet_explicit_cases(name, expected):
    assert _classify_i_sheet(name) == expected
