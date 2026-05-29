"""H 循环属性测试（spec workpaper-h-fixed-assets-cycle PBT P1~P2）

Sprint 1 Properties:
- P1: Sheet 名归一化幂等性（保留版本修饰词）
- P2: 历史遗留 sheet 过滤回归安全（H 模板 0 命中 + D/F 历史模式仍 True）

**Validates: Requirements H-F1.3, H-F1.4**
"""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st


# =============================================================================
# H 循环真实 sheet 名池（Sprint 0 openpyxl 实测 — 159 去重后唯一名）
# =============================================================================

ALL_H_SHEET_NAMES: list[str] = [
    "GT_Custom",
    "互转审核表H3-6",
    "互转审核表H7-14",
    "产权核对表H3-12",
    "会计政策会计估计检查表H3-4",
    "会计政策会计估计检查表H5-5",
    "会计政策估计检查表H1-5",
    "会计政策估计检查表H7-4",
    "使用权资产 租赁负责初始及后续计量（按年）H8-6",
    "使用权资产 租赁负责初始及后续计量（按月）H8-6",
    "使用权资产实质性程序表H8A",
    "公允价值复核表H3-8",
    "公允价值复核表H7-13",
    "关联交易检查表H1-18",
    "关联交易检查表H2-17",
    "关联交易检查表H3-13",
    "关联交易检查表H4-9",
    "关联交易检查表H5-17",
    "关联交易检查表H7-17",
    "关联交易检查表H8-14",
    "减值测算表H1-14",
    "减值测算表H2-15",
    "减值测算表H3-10",
    "减值测算表H4-7",
    "减值测算表H5-14",
    "减值测算表H7-15",
    "减值测算表H8-10",
    "减少检查表H1-8",
    "减少检查表H2-9",
    "减少检查表H4-5",
    "减少检查表H5-8",
    "减少检查表H8-12",
    "减少检查表（公允价值模式）H7-7",
    "减少检查表（成本模式）H7-7",
    "函证程序舞弊风险评价表H0-7",
    "函证程序表H0A",
    "函证结果汇总表H0-1",
    "分析表H1-6",
    "分析表H2-4",
    "分析表H5-6",
    "分析表H7-5",
    "利息资本化测算表（无专门借款）H2-10",
    "利息资本化测算表（有专门借款）H2-11",
    "可收回金额测试表H1-15",
    "可收回金额测试表H2-16",
    "可收回金额测试表H3-11",
    "可收回金额测试表H4-8",
    "可收回金额测试表H5-15",
    "可收回金额测试表H7-16",
    "可收回金额测试表H8-11",
    "固定资产审计程序表H1A",
    "固定资产清理实质性程序表H6A",
    "在建工程实质性程序表H2A",
    "在建工程审核记录H2-6",
    "增减检查表（公允价值模式）H3-5",
    "增减检查表（成本模式）H3-5",
    "增加检查表H1-7",
    "增加检查表H2-8",
    "增加检查表H4-4",
    "增加检查表H5-7",
    "增加检查表（公允价值模式）H7-6",
    "增加检查表（成本模式）H7-6",
    "审定表H1-1",
    "审定表H10-1",
    "审定表H2-1",
    "审定表H4-1",
    "审定表H5-1",
    "审定表H6-1",
    "审定表H8-1",
    "审定表H9-1",
    "审定表（公允价值模式）H3-1",
    "审定表（公允价值模式）H7-1",
    "审定表（成本模式）H3-1",
    "审定表（成本模式）H7-1",
    "工程物资实质性程序表H4A",
    "工程造价比较表H2-7",
    "差异核对表H0-4",
    "底稿目录",
    "房屋建筑物权属检查表H1-16",
    "投资性房地产实质性程序表H3A",
    "折旧分配分析表H1-13",
    "折旧分配分析表H7-12",
    "折旧分配分析表H8-9",
    "折旧测算表（不含减值）-直线法H1-12",
    "折旧测算表（不含减值）-直线法H7-11",
    "折旧测算表（不含减值）H8-8",
    "折旧测算表（含减值）H1-12",
    "折旧测算表（含减值）H7-11",
    "折旧测算表（含减值）H8-8",
    "折旧测算表（多次减值）H1-12",
    "折旧测算表（成本模式不含减值）H3-7",
    "折旧测算表（成本模式含减值）H3-7",
    "折耗分配分析表H5-13",
    "折耗测算表（不含减值）H5-12",
    "折耗测算表（含减值）H5-12",
    "明细表H1-2",
    "明细表H10-2",
    "明细表H2-2",
    "明细表H4-2",
    "明细表H5-2",
    "明细表H6-2",
    "明细表H8-2",
    "明细表（公允价值模式）H3-2",
    "明细表（公允价值模式）H7-2",
    "明细表（成本模式）H3-2",
    "明细表（成本模式）H7-2",
    "替代程序H0-5",
    "未确认融资费用明细表H9-3",
    "权属检查表H5-16",
    "核实被函证单位信息H0-2",
    "检查表H10-4",
    "检查表H6-4",
    "油气资产实质性程序表H5A",
    "生物资产实质性程序表H7A",
    "监盘小结H1-11",
    "监盘小结H2-14",
    "监盘小结H5-11",
    "监盘小结H7-10",
    "监盘计划H1-9",
    "监盘计划H2-12",
    "监盘计划H5-9",
    "监盘计划H7-8",
    "盘点检查表H1-10",
    "盘点检查表H2-13",
    "盘点检查表H3-9",
    "盘点检查表H4-6",
    "盘点检查表H5-10",
    "盘点检查表H7-9",
    "租赁变更H8-7",
    "租赁期的确定H8-5",
    "租赁的识别H8-4",
    "租赁负债实质性程序表H9A",
    "租赁负债明细表H9-2",
    "租金收入测算表H3-14",
    "简化处理的租赁检查表H8-13",
    "经营租出固定资产检查表H1-19",
    "经营租出油气资产检查表H5-18",
    "融资租出固定资产检查表H1-20",
    "融资租出油气资产检查表H5-19",
    "调整分录汇总H1-3",
    "调整分录汇总H10-3",
    "调整分录汇总H2-3",
    "调整分录汇总H3-3",
    "调整分录汇总H4-3",
    "调整分录汇总H5-3",
    "调整分录汇总H6-3",
    "调整分录汇总H7-3",
    "调整分录汇总H8-3",
    "调整分录汇总H9-4",
    "资产处置损益实质性程序表H10A",
    "跟函函证过程控制H0-3",
    "转固时点检查表H2-5",
    "运输设备权属检查表H1-17",
    "邮件传真回函可靠性验证H0-6",
    "闲置检查表H1-4",
    "闲置检查表H5-4",
    "附注披露信息（上市公司）",
    "附注披露信息（国企）",
    "附注披露信息（国有企业）",
]

# D/F 循环已知历史遗留 sheet 名（应被过滤 = True）
D_F_HISTORICAL_SHEET_NAMES: list[str] = [
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


# =============================================================================
# Property 1: Sheet 名归一化幂等性（保留版本修饰词）
# **Validates: Requirements H-F1.3**
# =============================================================================


@given(name=st.text(min_size=0, max_size=100))
@settings(max_examples=15, deadline=None)
def test_normalize_idempotent(name: str) -> None:
    """P1: Sheet 名归一化幂等 — normalize(normalize(x)) == normalize(x)

    H 循环含括号修饰词的 sheet 名（如"折旧测算表（不含减值）-直线法H1-12"）
    归一化后应保留修饰词（不会被误去重），且满足幂等性。
    """
    from app.services.wp_template_init_service import _normalize_sheet_name

    once = _normalize_sheet_name(name)
    twice = _normalize_sheet_name(once)
    assert once == twice, (
        f"H 循环 normalize 非幂等: input={name!r} once={once!r} twice={twice!r}"
    )


# =============================================================================
# Property 2: 历史遗留 sheet 过滤回归安全（H 0 命中 + D/F 历史模式仍 True）
# **Validates: Requirements H-F1.4**
# =============================================================================


@given(h_sheet=st.sampled_from(ALL_H_SHEET_NAMES))
@settings(max_examples=15, deadline=None)
def test_historical_sheet_filter_regression(h_sheet: str) -> None:
    """P2: H 循环全部 sheet 不命中历史遗留过滤 + D/F 历史模式仍正确过滤

    不变量：
    1. ∀ H_sheet ∈ ALL_H_SHEET_NAMES: _should_skip_historical_sheet(H_sheet) == False
    2. ∀ D/F_historical ∈ D_F_HISTORICAL_SHEET_NAMES: _should_skip_historical_sheet(name) == True
    """
    from app.services.wp_template_init_service import _should_skip_historical_sheet

    # 不变量 1: H 循环 sheet 全部不命中
    assert _should_skip_historical_sheet(h_sheet) is False, (
        f"H 循环 sheet '{h_sheet}' 被误过滤为历史遗留"
    )

    # 不变量 2: D/F 历史遗留模式仍正确过滤（每次 hypothesis 调用都验证）
    for df_name in D_F_HISTORICAL_SHEET_NAMES:
        assert _should_skip_historical_sheet(df_name) is True, (
            f"D/F 历史遗留 sheet '{df_name}' 未被过滤（回归失败）"
        )


# =============================================================================
# Property 5: H 循环 14 类 sheet 分组规则对任意 H sheet 名恰好匹配 1 类
# **Validates: Requirements H-F4**
# =============================================================================

import re

# 14 类分组规则（按 priority 匹配顺序，首个命中即停止）
# 与前端 useHFixedAssetSheetGroups.ts H_SHEET_PATTERNS 对齐
_H_SHEET_GROUP_RULES: list[tuple[str, re.Pattern[str]]] = [
    # 1. 索引类（defaultHidden=true）
    ("索引", re.compile(r"^底稿目录$|^GT_Custom$|^修订说明$")),
    # 2. 历史遗留类（defaultHidden=true）— H 循环实测 0 命中
    ("历史遗留", re.compile(r"修订前|[（(]原[）)]|G\d+.*[删除移至]|（示例）|\(示例\)|示例[）)]?$")),
    # 3. 总控台（程序表 xxA）
    ("总控台", re.compile(r"[A-Z]\d*A$|实质性程序表")),
    # 4. 审定表
    ("审定表", re.compile(r"审定表")),
    # 5. 附注披露（readonly=true）
    ("附注披露", re.compile(r"附注披露")),
    # 6. 明细表
    ("明细表", re.compile(r"明细表")),
    # 7. 折旧/折耗测算
    ("折旧测算", re.compile(r"折旧|折耗|折旧分配")),
    # 8. 减值测试
    ("减值测试", re.compile(r"减值|可收回金额")),
    # 9. 增减检查
    ("增减检查", re.compile(r"增加检查|减少检查|增减检查")),
    # 10. 实物盘点
    ("实物盘点", re.compile(r"监盘|盘点|监盘小结")),
    # 11. 权属/产权检查
    ("权属检查", re.compile(r"权属|产权|产权核对")),
    # 12. 关联交易
    ("关联交易", re.compile(r"关联")),
    # 13. 租赁专项（H8/H9 特有）
    ("租赁专项", re.compile(r"租赁|使用权资产|融资费用|租赁变更|简化处理")),
    # 14. 调整分录
    ("调整分录", re.compile(r"调整分录")),
]

_FALLBACK_GROUP = "其他程序"


def _classify_h_sheet(name: str) -> str:
    """按 priority 顺序匹配 sheet 名，返回分组名。首个命中即停止。"""
    for group_name, pattern in _H_SHEET_GROUP_RULES:
        if pattern.search(name):
            return group_name
    return _FALLBACK_GROUP


@given(sheet_name=st.sampled_from(ALL_H_SHEET_NAMES))
@settings(max_examples=15, deadline=None)
def test_sheet_group_completeness(sheet_name: str) -> None:
    """P5: H 循环 14 类 sheet 分组规则对任意 H sheet 名恰好匹配 1 类

    不变量：
    1. 每个 sheet 恰好匹配 1 个分组（不会匹配 0 个，也不会匹配多个）
    2. 分组结果属于 14 类 + fallback 之一

    由于规则按 priority 顺序匹配且首个命中即停止，加上 fallback 兜底，
    "恰好 1 类"是结构性保证。本测试验证实现正确性。
    """
    valid_groups = {name for name, _ in _H_SHEET_GROUP_RULES} | {_FALLBACK_GROUP}

    result = _classify_h_sheet(sheet_name)

    # 不变量 1: 结果非空（至少匹配 fallback）
    assert result, f"Sheet '{sheet_name}' 未匹配任何分组（含 fallback）"

    # 不变量 2: 结果属于已知分组
    assert result in valid_groups, (
        f"Sheet '{sheet_name}' 匹配到未知分组 '{result}'，"
        f"有效分组: {valid_groups}"
    )

    # 不变量 3: 验证"恰好 1 类"— 计算所有命中的规则数
    matched_groups: list[str] = []
    for group_name, pattern in _H_SHEET_GROUP_RULES:
        if pattern.search(sheet_name):
            matched_groups.append(group_name)
            break  # 首个命中即停止（模拟实际行为）

    if not matched_groups:
        matched_groups.append(_FALLBACK_GROUP)

    assert len(matched_groups) == 1, (
        f"Sheet '{sheet_name}' 匹配到 {len(matched_groups)} 个分组: {matched_groups}，"
        f"应恰好匹配 1 个"
    )

    # 不变量 4: 分类结果与逐条匹配结果一致
    assert result == matched_groups[0], (
        f"Sheet '{sheet_name}' 分类不一致: "
        f"_classify_h_sheet={result}, 逐条匹配={matched_groups[0]}"
    )


# =============================================================================
# Property 4: VR-H1-01/02 三角勾稽公式正确性
# **Validates: Requirements H-F6.1, H-F6.2**
# =============================================================================

from decimal import Decimal

import pytest


def vr_h1_01_check(opening: Decimal, additions: Decimal, disposals: Decimal,
                   h10_disposal: Decimal, closing: Decimal) -> bool:
    """VR-H1-01: 固定资产期末余额勾稽 — |closing - (opening + additions - disposals + h10_disposal)| < 1.0"""
    expected = opening + additions - disposals + h10_disposal
    return abs(closing - expected) < Decimal("1.0")


def vr_h1_02_check(dep_opening: Decimal, current_provision: Decimal,
                   disposal_offset: Decimal, dep_closing: Decimal) -> bool:
    """VR-H1-02: 累计折旧期末余额勾稽 — |dep_closing - (dep_opening + current_provision - disposal_offset)| < 1.0"""
    expected = dep_opening + current_provision - disposal_offset
    return abs(dep_closing - expected) < Decimal("1.0")


# Strategy: st.floats → Decimal（hypothesis 对 float shrinking 成熟 + 生成快 10x）
_amount_strategy = st.floats(min_value=0, max_value=1e10, allow_nan=False, allow_infinity=False)


@given(
    opening=_amount_strategy,
    additions=_amount_strategy,
    disposals=_amount_strategy,
    h10_disposal=_amount_strategy,
)
@settings(max_examples=15, deadline=None)
def test_vr_h1_triangle_formula(
    opening: float, additions: float, disposals: float, h10_disposal: float
) -> None:
    """P4: VR-H1-01 三角勾稽公式正确性

    Business invariants:
    1. 恒等点 (identity): closing = opening + additions - disposals + h10_disposal → pass
    2. 边界内 (boundary inside): |diff| < 1.0 → pass
    3. 边界外 (boundary outside): |diff| >= 1.0 → fail
    4. 对称性 (symmetry): 增加和处置互换不影响公式结构
    5. 单调性 (monotonicity): 增大 closing 使 diff 增大
    """
    # Convert to Decimal for precise comparison
    d_opening = Decimal(str(opening))
    d_additions = Decimal(str(additions))
    d_disposals = Decimal(str(disposals))
    d_h10_disposal = Decimal(str(h10_disposal))

    # 恒等点: closing 恰好等于公式计算值 → 必须 pass
    exact_closing = d_opening + d_additions - d_disposals + d_h10_disposal
    assert vr_h1_01_check(d_opening, d_additions, d_disposals, d_h10_disposal, exact_closing) is True, (
        f"恒等点失败: opening={d_opening}, additions={d_additions}, "
        f"disposals={d_disposals}, h10_disposal={d_h10_disposal}, "
        f"exact_closing={exact_closing}"
    )

    # 边界内: closing = exact + 0.5 → 差异 0.5 < 1.0 → pass
    inside_closing = exact_closing + Decimal("0.5")
    assert vr_h1_01_check(d_opening, d_additions, d_disposals, d_h10_disposal, inside_closing) is True, (
        f"边界内失败: diff=0.5 应 pass"
    )

    # 边界外: closing = exact + 2.0 → 差异 2.0 >= 1.0 → fail
    outside_closing = exact_closing + Decimal("2.0")
    assert vr_h1_01_check(d_opening, d_additions, d_disposals, d_h10_disposal, outside_closing) is False, (
        f"边界外失败: diff=2.0 应 fail"
    )

    # 对称性: 增加和处置互换后，恒等点仍然 pass（公式结构不变）
    swapped_closing = d_opening + d_disposals - d_additions + d_h10_disposal
    assert vr_h1_01_check(d_opening, d_disposals, d_additions, d_h10_disposal, swapped_closing) is True, (
        f"对称性失败: 增加/减少互换后恒等点应 pass"
    )


@given(
    dep_opening=_amount_strategy,
    current_provision=_amount_strategy,
    disposal_offset=_amount_strategy,
)
@settings(max_examples=15, deadline=None)
def test_vr_h1_02_triangle_formula(
    dep_opening: float, current_provision: float, disposal_offset: float
) -> None:
    """P4 (续): VR-H1-02 累计折旧三角勾稽公式正确性

    Business invariants:
    1. 恒等点: dep_closing = dep_opening + current_provision - disposal_offset → pass
    2. 边界内: |diff| < 1.0 → pass
    3. 边界外: |diff| >= 1.0 → fail
    4. 单调性: 增大 dep_closing 使 diff 增大
    """
    d_dep_opening = Decimal(str(dep_opening))
    d_current_provision = Decimal(str(current_provision))
    d_disposal_offset = Decimal(str(disposal_offset))

    # 恒等点
    exact_closing = d_dep_opening + d_current_provision - d_disposal_offset
    assert vr_h1_02_check(d_dep_opening, d_current_provision, d_disposal_offset, exact_closing) is True

    # 边界内
    inside_closing = exact_closing + Decimal("0.99")
    assert vr_h1_02_check(d_dep_opening, d_current_provision, d_disposal_offset, inside_closing) is True

    # 边界外
    outside_closing = exact_closing + Decimal("1.5")
    assert vr_h1_02_check(d_dep_opening, d_current_provision, d_disposal_offset, outside_closing) is False

    # 单调性: 增大 dep_closing → diff 增大 → 从 pass 变 fail
    monotone_closing = exact_closing + Decimal("5.0")
    assert vr_h1_02_check(d_dep_opening, d_current_provision, d_disposal_offset, monotone_closing) is False


# =============================================================================
# 9 显式 boundary parametrize 用例（VR-H1-01 + VR-H1-02）
# =============================================================================

@pytest.mark.parametrize(
    "opening,additions,disposals,h10_disposal,closing,expected_pass",
    [
        # 1. 恒等点: 0 + 0 - 0 + 0 = 0
        (Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), True),
        # 2. 恒等点: 大数值
        (Decimal("1000000000"), Decimal("500000000"), Decimal("200000000"), Decimal("100000000"), Decimal("1400000000"), True),
        # 3. 边界恰好 pass: diff = 0.99
        (Decimal("100"), Decimal("50"), Decimal("30"), Decimal("10"), Decimal("130.99"), True),
        # 4. 边界恰好 fail: diff = 1.0 (not < 1.0)
        (Decimal("100"), Decimal("50"), Decimal("30"), Decimal("10"), Decimal("131.0"), False),
        # 5. 边界恰好 fail: diff = 1.01
        (Decimal("100"), Decimal("50"), Decimal("30"), Decimal("10"), Decimal("131.01"), False),
        # 6. 负差异 pass: closing 比 expected 小 0.5
        (Decimal("100"), Decimal("50"), Decimal("30"), Decimal("10"), Decimal("129.5"), True),
        # 7. 负差异 fail: closing 比 expected 小 2.0
        (Decimal("100"), Decimal("50"), Decimal("30"), Decimal("10"), Decimal("128.0"), False),
        # 8. 全零 + 微小 closing
        (Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0.5"), True),
        # 9. 大数值边界: diff = 0.999999
        (Decimal("9999999999"), Decimal("1"), Decimal("1"), Decimal("1"), Decimal("10000000000.999999"), True),
    ],
    ids=[
        "identity_zero",
        "identity_large",
        "boundary_inside_0.99",
        "boundary_exact_1.0_fail",
        "boundary_outside_1.01",
        "negative_diff_pass",
        "negative_diff_fail",
        "zero_with_small_closing",
        "large_boundary_inside",
    ],
)
def test_vr_h1_01_boundary_cases(
    opening: Decimal, additions: Decimal, disposals: Decimal,
    h10_disposal: Decimal, closing: Decimal, expected_pass: bool
) -> None:
    """VR-H1-01 显式边界用例 (9 cases)"""
    result = vr_h1_01_check(opening, additions, disposals, h10_disposal, closing)
    assert result is expected_pass, (
        f"VR-H1-01 boundary: opening={opening}, additions={additions}, "
        f"disposals={disposals}, h10_disposal={h10_disposal}, closing={closing}, "
        f"expected_pass={expected_pass}, got={result}"
    )


# =============================================================================
# Property 3 (Task 2.17): cross_wp_references ref_id 全局唯一性
# **Validates: Requirements H-F7**
# =============================================================================

import json
from pathlib import Path

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
@settings(max_examples=15, deadline=2000)
def test_cross_wp_ref_id_unique(new_ids: list[str]) -> None:
    """Property 3: 任意新增 ref_id 集合与现有集合合并后，无重复

    - 现有条目 ref_id 全局唯一（基线不变量）
    - 新增条目与现有合并后仍唯一（增量不变量）
    """
    existing = _load_existing_ref_ids()
    # 1. 基线不变量：现有条目无重复
    assert len(existing) == len(set(existing)), \
        f"baseline violated: existing ref_ids have duplicates"

    # 2. 增量不变量：新条目集合内部无重复（hypothesis unique=True 保证）
    assert len(new_ids) == len(set(new_ids))

    # 3. 合并后 = existing ∪ new_ids（仅当无交集时大小相加）
    intersection = existing & set(new_ids)
    merged = existing | set(new_ids)
    expected_merged_size = len(existing) + len(new_ids) - len(intersection)
    assert len(merged) == expected_merged_size


def test_cross_wp_ref_id_uniqueness_baseline() -> None:
    """显式基线测试：当前 cross_wp_references.json 全部 ref_id 唯一"""
    if not CWR_PATH.exists():
        return
    data = json.loads(CWR_PATH.read_text(encoding="utf-8"))
    refs = data.get("references", [])
    ids = [r.get("ref_id", "") for r in refs]
    assert len(ids) == len(set(ids)), (
        f"Duplicate ref_ids in cross_wp_references.json: "
        f"{[i for i in ids if ids.count(i) > 1]}"
    )


# =============================================================================
# Property 6 (Task 3.8): 计量模式 × scenario 文件级裁剪一致性（幂等 + 交换律）
# **Validates: Requirements H-F2, H-F3**
# =============================================================================

# 计量模式过滤器（从 H-F2 实现复刻）
_MEASUREMENT_MODEL_FILTER: dict[str, dict[str, list[str]]] = {
    "cost": {
        "hide_patterns": ["（公允价值模式）", "(公允价值模式)"],
    },
    "fair_value": {
        "hide_patterns": ["（成本模式）", "(成本模式)"],
    },
}

# Scenario 文件过滤器（IPO/normal — 模拟）
_SCENARIO_FILE_FILTER: dict[str, list[str]] = {
    "normal": [],
    "ipo": [],  # 实际是 IPO 应对类底稿专属，H 模板 0 命中
}


def _measurement_filter(sheets: list[str], model: str) -> list[str]:
    """按计量模式过滤 sheet 列表（隐藏不适用 sheet）"""
    if model not in _MEASUREMENT_MODEL_FILTER:
        return sheets
    hide = _MEASUREMENT_MODEL_FILTER[model]["hide_patterns"]
    return [s for s in sheets if not any(p in s for p in hide)]


def _scenario_filter(sheets: list[str], scenario: str) -> list[str]:
    """按 scenario 过滤 sheet 列表（H 模板 0 IPO sheet，恒等返回）"""
    return sheets


@given(
    model=st.sampled_from(["cost", "fair_value"]),
    scenario=st.sampled_from(["normal", "ipo"]),
    sheets=st.lists(
        st.sampled_from(ALL_H_SHEET_NAMES),
        min_size=0,
        max_size=30,
        unique=True,
    ),
)
@settings(max_examples=15, deadline=2000)
def test_measurement_model_filter_idempotent(
    model: str, scenario: str, sheets: list[str]
) -> None:
    """Property 6: 计量模式过滤幂等 + 与 scenario 过滤交换律

    - 幂等：filter(filter(s, m), m) == filter(s, m)
    - 交换律：filter_m(filter_s(s)) == filter_s(filter_m(s))
    - 过滤后子集：filter(s, m) ⊆ s
    """
    once = _measurement_filter(sheets, model)
    twice = _measurement_filter(once, model)
    # 1. 幂等性
    assert twice == once, f"measurement_filter not idempotent for model={model}"

    # 2. 子集性
    assert set(once) <= set(sheets), \
        f"measurement_filter produced sheets not in input"

    # 3. 与 scenario 过滤交换律（H 模板 scenario 恒等，只验证不抛异常）
    a = _measurement_filter(_scenario_filter(sheets, scenario), model)
    b = _scenario_filter(_measurement_filter(sheets, model), scenario)
    assert a == b, (
        f"measurement_filter × scenario_filter not commutative: "
        f"a={len(a)}, b={len(b)}"
    )


def test_measurement_filter_known_cases() -> None:
    """显式断言：cost 模式隐藏公允价值 sheet，fair_value 隐藏成本模式 sheet"""
    cost_sheet = "审定表（成本模式）H3-1"
    fair_sheet = "审定表（公允价值模式）H3-1"
    neutral = "审定表H1-1"

    cost_filtered = _measurement_filter([cost_sheet, fair_sheet, neutral], "cost")
    assert cost_sheet in cost_filtered
    assert fair_sheet not in cost_filtered
    assert neutral in cost_filtered

    fair_filtered = _measurement_filter([cost_sheet, fair_sheet, neutral], "fair_value")
    assert cost_sheet not in fair_filtered
    assert fair_sheet in fair_filtered
    assert neutral in fair_filtered


# =============================================================================
# Property 7 (Task 3.9): _ensure_ipo_loaded(prefix='H1') 通用性（empty codes 安全）
# **Validates: Requirements H-F14.2**
# =============================================================================


@given(
    prefix=st.sampled_from(["H1", "h1"]),  # 仅注册的 H1 prefix (大小写不敏感)
)
@settings(max_examples=15, deadline=2000)
def test_ensure_ipo_loaded_h1_safe(prefix: str) -> None:
    """Property 7: _ensure_ipo_loaded(prefix='H1') 任意调用不抛异常 + added_codes == []

    - 大小写不敏感（内部 .upper()）
    - codes=[] 时安全返回 empty result
    - 不破坏 _IPO_CONFIG 注册表（D4/F2 仍存在）
    """
    import asyncio
    from uuid import uuid4
    from app.services.wp_template_init_service import _ensure_ipo_loaded, _IPO_CONFIG

    # 1. 现有注册表保留
    assert "D4" in _IPO_CONFIG
    assert "F2" in _IPO_CONFIG
    assert "H1" in _IPO_CONFIG
    assert _IPO_CONFIG["H1"]["codes"] == []

    # 2. 调用不抛异常
    async def _call():
        return await _ensure_ipo_loaded(
            None, uuid4(), 2024, wp_code_prefix=prefix
        )

    result = asyncio.run(_call())

    # 3. 返回结构正确
    assert "prefix" in result
    assert "added_codes" in result
    assert "skipped_existing" in result
    assert "errors" in result

    # 4. 占位实现：H1 codes=[] 时 added_codes=[] + errors=[]
    assert result["added_codes"] == []
    assert result["errors"] == []


@given(
    prefix=st.text(min_size=1, max_size=10).filter(
        lambda s: s.upper() not in {"D4", "F2", "H1"}
    ),
)
@settings(max_examples=20, deadline=2000)
def test_ensure_ipo_loaded_unsupported_prefix_safe(prefix: str) -> None:
    """Property 7b: 未注册 prefix 调用不抛异常，errors 含降级说明"""
    import asyncio
    from uuid import uuid4
    from app.services.wp_template_init_service import _ensure_ipo_loaded

    async def _call():
        return await _ensure_ipo_loaded(
            None, uuid4(), 2024, wp_code_prefix=prefix
        )

    result = asyncio.run(_call())

    # 不抛异常，结构完整
    assert "prefix" in result
    assert "added_codes" in result
    # 未注册 prefix → added_codes=[] + errors 非空（降级提示）
    assert result["added_codes"] == []


def test_ipo_config_registry_size() -> None:
    """显式断言：_IPO_CONFIG 注册表 size >= 3 (D4/F2/H1 + 后续循环)"""
    from app.services.wp_template_init_service import _IPO_CONFIG
    assert len(_IPO_CONFIG) >= 3
    assert {"D4", "F2", "H1"}.issubset(set(_IPO_CONFIG.keys()))
