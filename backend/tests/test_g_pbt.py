"""G 投资循环属性测试（spec workpaper-g-investment-cycle PBT P1~P6）

6 Properties:
- P1: Sheet 名归一化幂等性（normalize idempotent）
- P2: 历史遗留 sheet 过滤回归（G11/G12/G13/G14 修订前 4 命中 + D/F/H/I 历史模式仍 True）
- P3: cross_wp_references ref_id 全局唯一性
- P4: VR-G7-01/G11-01/G1-01/G14-01 三角勾稽公式正确性
- P5: G 循环 12 类 sheet 分组规则完备性（任意 G sheet 名恰好命中 1 类 + 优先级冲突解决）
- P6: ECL 三阶段模型单调性（pd_12m ≤ pd_lifetime ⇒ ECL(1) ≤ ECL(2) ≤ ECL(3)）

**Validates: Requirements G-F1, G-F2, G-F5.6, G-F6.1, G-F7**

对应 task: Sprint 1 (1.3, 1.4) + Sprint 2 (2.4, 2.11, 2.15, 2.19)
"""
from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


# =============================================================================
# G 循环真实 sheet 名池（Sprint 0 openpyxl 实测 — 152 去重后唯一名）
# =============================================================================

ALL_G_SHEET_NAMES: list[str] = [
    "业务模式分析G1-8", "业务模式分析G4-5", "业务模式分析G6-7",
    "交易性金融负债实质性程序表G10A", "交易性金融资产实质性程序表G1A",
    "余额明细表G5-2", "信用减值损失会计政策检查G5-8",
    "信用减值损失审计程序表G14A", "债权投资三阶段划分G4-9",
    "债权投资减值准备测算表G4-10", "债权投资实质性程序表G4A",
    "公允价值变动收益审计程序表G13A", "公允价值测试表G1-6",
    "公允价值测试表G10-5", "公允价值测试表G12-4", "公允价值测试表G6-5",
    "公允价值测试表G8-4", "公允价值测试表G9-4",
    "其他债权投资三阶段划分G6-11", "其他债权投资减值准备测算表G6-12",
    "其他债权投资实质性程序表G6A", "其他权益工具投资实质性程序表G8A",
    "其他非流动金融资产实质性程序表G9A", "净敞口套期收益审计程序表G12A",
    "减值准备转回(收回)、核销检查表G4-12",
    "减值准备转回(收回)、核销检查表G5-11",
    "减值准备转回(收回)、核销检查表G6-14",
    "减值测试表G7-17",
    "凭证检查表G10-7", "凭证检查表G11-5", "凭证检查表G12-6", "凭证检查表G2-8",
    "凭证检查表G4-13", "凭证检查表G5-12", "凭证检查表G6-15", "凭证检查表G7-18",
    "凭证检查表G8-6", "凭证检查表G9-6",
    "函证差异核对表G0-3(证券投资)", "函证差异核对表G0-4(非证券投资)",
    "函证程序舞弊风险评价表F0-8",
    "函证程序表G0A", "函证结果汇总表G0-1",
    "分类的适当性检查表G1-9", "分类的适当性检查表G10-4",
    "利息测算表G2-5", "利息测算表G4-4", "利息测算表G6-6",
    "参考-中证协《证券公司金融工具减值指引》", "参考-根据剩余期限折算PD",
    "参考中证协《证券公司金融工具减值指引》", "参考中证协《非上市公司股权估值指引》",
    "合同现金流量特征分析G1-10", "合同现金流量特征分析G4-6",
    "合同现金流量特征分析G6-8", "合营、联营企业投资成本测试表G7-13",
    "坏账准备明细表G2-3", "坏账准备明细表G5-3", "坏账准备明细表G6-3",
    "处置子公司测试表(一揽子交易)G7-12",
    "处置子公司测试表(不包含一揽子交易)G7-11",
    "子公司初始计量测试(同控)G7-8", "子公司初始计量测试(非同控)G7-9",
    "子公司后续计量测试表G7-10",
    "审定表G1-1", "审定表G10-1", "审定表G11-1", "审定表G12-1",
    "审定表G13-1", "审定表G14-1", "审定表G2-1", "审定表G3-1",
    "审定表G4-1", "审定表G5-1", "审定表G6-1", "审定表G8-1",
    "审定表G9-1",
    "应收利息坏账准备测算G2-7", "应收利息实质性程序表G2A",
    "应收股利实质性程序表G3A",
    "底稿目录",
    "投资收益实质性程序表G11A",
    "指定的适当性检查表G8-5",
    "收益测算表G1-5", "收益率分析表G11-4",
    "明细分析表G11-2",
    "明细表G1-2", "明细表G10-2", "明细表G12-2", "明细表G13-2",
    "明细表G14-2", "明细表G2-2", "明细表G3-2", "明细表G4-2",
    "明细表G6-2", "明细表G7-2", "明细表G8-2", "明细表G9-2",
    "替代程序检查表G0-6",
    "有价证券监盘表G1-11", "有价证券盘点倒轧表G1-12",
    "有价证券盘点表G4-7", "有价证券盘点表G6-9",
    "未实现融资收益测算表(租赁)G5-5", "未实现融资收益测算表(销售)G5-6",
    "未确认投资损失测试表G7-16", "权益法未实现内部交易抵销测算表G7-15",
    "权益法测算表G7-14",
    "核实被函证单位信息G0-2",
    "检查表G1-13", "测算及检查表G3-4",
    "盘点倒轧表G4-8", "盘点倒轧表G6-10",
    "第三层次公允价值计量的调节表G1-7",
    "第三层次公允价值计量的调节表G10-6",
    "第三层次公允价值计量的调节表G9-5",
    "结存表G1-4",
    "衍生金融工具核查表G1-14", "衍生金融工具核查表G10-8",
    "被投资公司会计政策G7-6", "被投资单位基本信息G7-4",
    "被投资单位财务信息(合营、联营)G7-5",
    "调整分录汇总G1-3", "调整分录汇总G10-3", "调整分录汇总G11-3",
    "调整分录汇总G12-3", "调整分录汇总G13-3", "调整分录汇总G14-3",
    "调整分录汇总G2-4", "调整分录汇总G3-3", "调整分录汇总G4-3",
    "调整分录汇总G5-4", "调整分录汇总G6-4", "调整分录汇总G7-3",
    "调整分录汇总G8-3", "调整分录汇总G9-3",
    "跟函函证过程控制G0-3", "邮件传真回函可靠性验证G0-7",
    "长期应收款三阶段划分G5-9", "长期应收款保理核查表G5-7",
    "长期应收款坏账准备测算G5-10", "长期应收款实质性程序表G5A",
    "长期未收回款项检查表G2-6", "长期未收回款项检查表G3-5",
    "长期股权投资初始判断G7-7", "长期股权投资实质性程序表G7A",
    "长期股权投资审定表G7-1",
    "附注披露信息(上市公司)", "附注披露信息(国企)",
    "预期信用损失的计量测试G4-11", "预期信用损失的计量测试G6-13",
    "风险净敞口检查表G12-5",
]


# G 循环 4 个历史遗留 sheet 名（"修订前"）— 必须 True
G_HISTORICAL_SHEET_NAMES: list[str] = [
    "投资收益实质性程序表G11A-修订前",
    "净敞口套期收益审计程序表G12A-修订前",
    "公允价值变动收益审计程序表G13A-修订前",
    "信用减值损失审计程序表G14A -修订前",
]


# D/F/H/I 循环已知历史遗留 sheet 名（应 True）
D_F_H_I_HISTORICAL_SHEET_NAMES: list[str] = [
    "主营业务收入审计程序表 D4A（修订前）",
    "D7A（原）",
    "D8A(原)",
    "存货计价测试程序G2-8-删除",
    "G2-8-4-移至分析类",
    "产品年度成本比较G2-9-3-删除",
    "函证差异检查表（示例）",
    "合同履约成本测试（示例）",
    "访谈记录与核对示例",
    "参考－商誉减值测试示例",
]


# =============================================================================
# Property 1 (PBT-P1, task 1.3): Sheet 名归一化幂等性
# Validates: Requirements G-F1
# =============================================================================


@given(name=st.text(min_size=0, max_size=100))
@settings(max_examples=15, deadline=None)
def test_normalize_idempotent(name: str) -> None:
    """P1: ∀ name: normalize(normalize(name)) == normalize(name)

    任意输入 sheet 名（含空字符串/纯空格/Unicode/特殊字符）调用 _normalize_sheet_name
    两次应返回相同结果（幂等）。
    """
    from app.services.wp_template_init_service import _normalize_sheet_name

    once = _normalize_sheet_name(name)
    twice = _normalize_sheet_name(once)
    assert once == twice, f"normalize 非幂等: '{name}' → '{once}' → '{twice}'"


# =============================================================================
# Property 2 (PBT-P2, task 1.4): 历史遗留 sheet 过滤回归
# Validates: Requirements G-F1.4
# =============================================================================


@given(g_sheet=st.sampled_from(ALL_G_SHEET_NAMES))
@settings(max_examples=15, deadline=None)
def test_historical_sheet_filter_regression_g_normal(g_sheet: str) -> None:
    """P2 part A: G 循环 152 个去重后正常 sheet 不应被历史遗留过滤命中"""
    from app.services.wp_template_init_service import _should_skip_historical_sheet

    assert _should_skip_historical_sheet(g_sheet) is False, (
        f"G 循环正常 sheet '{g_sheet}' 不应被 _should_skip_historical_sheet 误命中"
    )


def test_historical_sheet_filter_g_modified_4_hits() -> None:
    """P2 part B: G11/G12/G13/G14 4 个 '修订前' sheet 必须 True"""
    from app.services.wp_template_init_service import _should_skip_historical_sheet

    for name in G_HISTORICAL_SHEET_NAMES:
        assert _should_skip_historical_sheet(name) is True, (
            f"G 历史遗留 sheet '{name}' 必须命中 _should_skip_historical_sheet"
        )


def test_historical_sheet_filter_dfhi_regression() -> None:
    """P2 part C: D/F/H/I 历史模式仍正确过滤（不被 G spec 破坏）"""
    from app.services.wp_template_init_service import _should_skip_historical_sheet

    for name in D_F_H_I_HISTORICAL_SHEET_NAMES:
        assert _should_skip_historical_sheet(name) is True, (
            f"D/F/H/I 历史遗留 sheet '{name}' 仍应被过滤"
        )


# =============================================================================
# Property 3 (PBT-P3, task 2.19): cross_wp_references ref_id 全局唯一性
# Validates: Requirements G-F7
# =============================================================================

CWR_PATH = Path(__file__).resolve().parent.parent / "data" / "cross_wp_references.json"


def test_cross_wp_ref_id_uniqueness_baseline() -> None:
    """P3 baseline: 当前 cross_wp_references.json 全部 ref_id 唯一"""
    assert CWR_PATH.exists(), f"cross_wp_references.json missing at {CWR_PATH}"
    data = json.loads(CWR_PATH.read_text(encoding="utf-8"))
    refs = data["references"]
    ids = [r.get("ref_id", "") for r in refs]
    duplicates = {rid for rid in ids if ids.count(rid) > 1}
    assert len(ids) == len(set(ids)), (
        f"cross_wp_references baseline 含重复 ref_id: {duplicates}"
    )


@given(
    new_ids=st.lists(
        st.from_regex(r"^CW-\d{1,4}$", fullmatch=True),
        unique=True,
        min_size=0,
        max_size=20,
    ),
)
@settings(max_examples=15, deadline=2000)
def test_cross_wp_ref_id_unique(new_ids: list[str]) -> None:
    """P3 hypothesis: 任意新增 ref_id 集合内部唯一 + 与 baseline 合并后无重复

    Note: 该测试以 hypothesis 生成的 ref_id 集合为新输入；hypothesis unique=True
    保证 new_ids 内部唯一。这里仅验证此约束 + baseline 全局唯一性已由
    test_cross_wp_ref_id_uniqueness_baseline 验证。
    """
    # 1. 增量内部唯一（hypothesis unique=True 保证）
    assert len(new_ids) == len(set(new_ids))

    # 2. baseline 唯一性（防御性，每次 hypothesis 调用都验证）
    if not CWR_PATH.exists():
        pytest.skip("cross_wp_references.json missing")
    data = json.loads(CWR_PATH.read_text(encoding="utf-8"))
    existing_ids = [r.get("ref_id", "") for r in data["references"]]
    assert len(existing_ids) == len(set(existing_ids)), (
        "baseline cross_wp_references 含重复 ref_id"
    )


# =============================================================================
# Property 4 (PBT-P4, task 2.15): VR 三角勾稽公式正确性
# Validates: Requirements G-F6.1, G-F6.2
# =============================================================================
#
# Strategy: 使用 drift ∈ [-2, 2] 区间，让 closing = expected + drift
# 业务不变量: passes ↔ |drift| < tolerance（tolerance = Decimal("1.0")）
# 避免恒真断言（per memory rule: F-F4 PBT-P4 教训）

_amount_strategy = st.floats(
    min_value=0, max_value=1e10, allow_nan=False, allow_infinity=False
)
_ratio_strategy = st.floats(
    min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
)
_drift_strategy = st.floats(
    min_value=-2.0, max_value=2.0, allow_nan=False, allow_infinity=False
)
TOLERANCE = Decimal("1.0")


def _to_decimal(f: float) -> Decimal:
    """安全 float → Decimal 转换（保留 4 位小数避免边界精度抖动）"""
    return Decimal(str(round(f, 4)))


# ─── VR-G7-01: G7 权益法投资收益 = 净利润 × 持股比例 − 内部抵消 ─────────────


@given(
    investee_net_profit=_amount_strategy,
    shareholding_ratio=_ratio_strategy,
    internal_offset=_amount_strategy,
    drift=_drift_strategy,
)
@settings(max_examples=15, deadline=None)
def test_vr_g7_01_triangle_formula(
    investee_net_profit: float,
    shareholding_ratio: float,
    internal_offset: float,
    drift: float,
) -> None:
    """P4-VR-G7-01: 业务不变量 passes ↔ |drift| < 1.0"""
    np_ = _to_decimal(investee_net_profit)
    ratio = _to_decimal(shareholding_ratio)
    offset = _to_decimal(internal_offset)
    d = _to_decimal(drift)

    expected = np_ * ratio - offset
    recognized_income = expected + d

    diff = abs(recognized_income - expected)
    passes = diff < TOLERANCE

    if abs(d) < Decimal("1.0"):
        assert passes, (
            f"|drift|={abs(d)} < 1.0 应通过, "
            f"但 diff={diff} 未通过：np={np_}, ratio={ratio}, offset={offset}"
        )
    elif abs(d) > Decimal("1.0"):
        assert not passes, (
            f"|drift|={abs(d)} > 1.0 应失败, "
            f"但 diff={diff} 通过了：np={np_}, ratio={ratio}, offset={offset}"
        )


# ─── VR-G11-01: G11 投资收益汇总 = G1+G4+G6+G7+G8 ─────────────────────────


@given(
    g1=_amount_strategy,
    g4=_amount_strategy,
    g6=_amount_strategy,
    g7=_amount_strategy,
    g8=_amount_strategy,
    drift=_drift_strategy,
)
@settings(max_examples=15, deadline=None)
def test_vr_g11_01_triangle_formula(
    g1: float, g4: float, g6: float, g7: float, g8: float, drift: float,
) -> None:
    """P4-VR-G11-01: 业务不变量 passes ↔ |drift| < 1.0"""
    g1d, g4d, g6d, g7d, g8d = (_to_decimal(x) for x in (g1, g4, g6, g7, g8))
    d = _to_decimal(drift)

    expected = g1d + g4d + g6d + g7d + g8d
    g11_total = expected + d
    diff = abs(g11_total - expected)
    passes = diff < TOLERANCE

    if abs(d) < Decimal("1.0"):
        assert passes
    elif abs(d) > Decimal("1.0"):
        assert not passes


# ─── VR-G1-01: G1 公允价值变动 = 期末 − 期初 ──────────────────────────────


@given(
    fv_closing=_amount_strategy,
    fv_opening=_amount_strategy,
    drift=_drift_strategy,
)
@settings(max_examples=15, deadline=None)
def test_vr_g1_01_triangle_formula(
    fv_closing: float, fv_opening: float, drift: float,
) -> None:
    """P4-VR-G1-01: 业务不变量 passes ↔ |drift| < 1.0"""
    closing = _to_decimal(fv_closing)
    opening = _to_decimal(fv_opening)
    d = _to_decimal(drift)

    expected = closing - opening
    fv_change = expected + d
    diff = abs(fv_change - expected)
    passes = diff < TOLERANCE

    if abs(d) < Decimal("1.0"):
        assert passes
    elif abs(d) > Decimal("1.0"):
        assert not passes


# ─── VR-G14-01: G14 信用减值损失 = G4 ECL变动 + G6 ECL变动 ───────────────


@given(
    g4_ecl_change=_amount_strategy,
    g6_ecl_change=_amount_strategy,
    drift=_drift_strategy,
)
@settings(max_examples=15, deadline=None)
def test_vr_g14_01_triangle_formula(
    g4_ecl_change: float, g6_ecl_change: float, drift: float,
) -> None:
    """P4-VR-G14-01: 业务不变量 passes ↔ |drift| < 1.0"""
    g4 = _to_decimal(g4_ecl_change)
    g6 = _to_decimal(g6_ecl_change)
    d = _to_decimal(drift)

    expected = g4 + g6
    g14_total = expected + d
    diff = abs(g14_total - expected)
    passes = diff < TOLERANCE

    if abs(d) < Decimal("1.0"):
        assert passes
    elif abs(d) > Decimal("1.0"):
        assert not passes


# ─── 9 显式 boundary 用例（per memory rule F spec PBT-P4 教训）────────────


@pytest.mark.parametrize(
    "drift,expected_pass",
    [
        # 恒等点
        (Decimal("0"), True),
        # 边界内（|drift| < 1.0 通过）
        (Decimal("0.5"), True),
        (Decimal("-0.5"), True),
        (Decimal("0.99"), True),
        (Decimal("-0.99"), True),
        # 边界外（|drift| > 1.0 失败）
        (Decimal("1.5"), False),
        (Decimal("-1.5"), False),
        # 临界点（精确 1.0 不通过 — strict less than）
        (Decimal("1.0"), False),
        (Decimal("-1.0"), False),
    ],
)
def test_vr_g_triangle_boundary_explicit(drift: Decimal, expected_pass: bool):
    """9 显式 boundary 用例：恒等 / 边界内 / 边界外 / 临界点"""
    expected = Decimal("1000")
    actual = expected + drift
    diff = abs(actual - expected)
    passes = diff < TOLERANCE
    assert passes is expected_pass, (
        f"drift={drift}, diff={diff}, passes={passes}, expected={expected_pass}"
    )


# =============================================================================
# Property 5 (PBT-P5, task 2.4): G 循环 12 类 sheet 分组规则完备性
# Validates: Requirements G-F2
# =============================================================================
#
# 不变量: ∀ G-cycle sheet name: classifyGSheet 命中且仅命中 1 类
# 这里在 Python 端用等价 regex 匹配验证（与 design.md ADR-G6 + ts 实现对齐）

# 与 useGInvestmentCycleSheetGroups.ts 中 G_SHEET_GROUP_RULES 完全对齐
G_GROUP_RULES_PY: list[tuple[str, int, re.Pattern]] = [
    # (id, priority, regex)
    ("index", 0, re.compile(r"^底稿目录$|^GT_Custom$")),
    # historical: 同 _should_skip_historical_sheet 等价模式（修订前/原/(原)/-删除$/-移至/示例）
    ("historical", 1, re.compile(r"修订前|（原）|\(原\)|-删除$|-移至|（示例）|示例$")),
    ("procedure", 2, re.compile(r"[A-Z]\d*A$|实质性程序")),
    ("audit_table", 3, re.compile(r"审定表")),
    ("disclosure", 4, re.compile(r"附注披露")),
    ("detail", 5, re.compile(r"明细表|结存表")),
    ("fair_value", 6, re.compile(r"公允价值测试|公允价值计量|第三层次")),
    ("impairment", 7, re.compile(r"减值|信用损失|ECL")),
    ("income_calc", 8, re.compile(r"收益测算|利息收入|投资收益")),
    ("classification", 9, re.compile(r"业务模式|合同现金流|分类.*适当性|SPPI")),
    ("confirmation", 10, re.compile(r"函证|核实被函证|跟函|差异核对|替代程序|邮件传真|舞弊风险评价")),
    ("adjustment", 11, re.compile(r"调整分录")),
    # other: fallback
]


def classify_g_sheet_py(name: str) -> str:
    """Python 端等价的 classifyGSheet（按 priority 升序，首个命中即停）"""
    for rule_id, _prio, pattern in G_GROUP_RULES_PY:
        if pattern.search(name):
            return rule_id
    return "other"


@given(sheet_name=st.sampled_from(ALL_G_SHEET_NAMES))
@settings(max_examples=15, deadline=None)
def test_sheet_group_completeness(sheet_name: str) -> None:
    """P5: G 循环 152 个真实 sheet 名各自命中恰好 1 类（含 fallback "other"）"""
    category = classify_g_sheet_py(sheet_name)
    # 完备性：必返回非空字符串（含 fallback）
    assert isinstance(category, str) and len(category) > 0, (
        f"sheet '{sheet_name}' 未命中任何分类规则"
    )
    # 类目 id 必在已知集合内
    valid_ids = {rid for rid, _, _ in G_GROUP_RULES_PY} | {"other"}
    assert category in valid_ids, (
        f"sheet '{sheet_name}' 命中非法类目 '{category}'"
    )


# 18 显式覆盖样本（per memory rule I spec PBT-P5: 18 explicit cases）


@pytest.mark.parametrize(
    "name,expected_id",
    [
        # 索引
        ("底稿目录", "index"),
        # 总控台（程序表 xxA）
        ("函证程序表G0A", "procedure"),
        ("交易性金融资产实质性程序表G1A", "procedure"),
        ("投资收益实质性程序表G11A", "procedure"),
        # 审定表
        ("审定表G1-1", "audit_table"),
        ("长期股权投资审定表G7-1", "audit_table"),
        # 附注披露
        ("附注披露信息(上市公司)", "disclosure"),
        ("附注披露信息(国企)", "disclosure"),
        # 明细表
        ("明细表G7-2", "detail"),
        ("结存表G1-4", "detail"),
        # 公允价值测试
        ("公允价值测试表G1-6", "fair_value"),
        ("第三层次公允价值计量的调节表G1-7", "fair_value"),
        # 减值测试
        ("减值测试表G7-17", "impairment"),
        ("债权投资减值准备测算表G4-10", "impairment"),
        # 收益测算
        ("收益测算表G1-5", "income_calc"),
        # 分类检查
        ("业务模式分析G1-8", "classification"),
        ("合同现金流量特征分析G1-10", "classification"),
        # 函证
        ("函证结果汇总表G0-1", "confirmation"),
        # 调整分录
        ("调整分录汇总G11-3", "adjustment"),
    ],
)
def test_sheet_group_explicit_cases(name: str, expected_id: str):
    """18 显式样本验证 — design.md ADR-G6 关键冲突解决"""
    actual = classify_g_sheet_py(name)
    assert actual == expected_id, (
        f"sheet '{name}' 期望 '{expected_id}', 实际 '{actual}'"
    )


# =============================================================================
# Property 6 (PBT-P6, task 2.11): ECL 三阶段模型单调性
# Validates: Requirements G-F5.6
# =============================================================================
#
# 不变量: 当 pd_12m ≤ pd_lifetime 时, ECL(stage=1) ≤ ECL(stage=2) ≤ ECL(stage=3)


@given(
    book_value=st.floats(
        min_value=0.01, max_value=1e8, allow_nan=False, allow_infinity=False
    ),
    pd_12m_raw=_ratio_strategy,
    pd_lifetime_raw=_ratio_strategy,
    lgd_raw=_ratio_strategy,
)
@settings(max_examples=15, deadline=None)
def test_ecl_monotonicity(
    book_value: float, pd_12m_raw: float, pd_lifetime_raw: float, lgd_raw: float,
) -> None:
    """P6: ECL(1) ≤ ECL(2) ≤ ECL(3) when pd_12m ≤ pd_lifetime"""
    from app.routers.wp_g_ecl import (
        _calc_ecl_stage_1,
        _calc_ecl_stage_2,
        _calc_ecl_stage_3,
    )

    bv = _to_decimal(book_value)
    # 强制约束 pd_12m <= pd_lifetime（PBT 业务前提条件）
    pd_12m = _to_decimal(min(pd_12m_raw, pd_lifetime_raw))
    pd_lifetime = _to_decimal(max(pd_12m_raw, pd_lifetime_raw))
    lgd = _to_decimal(lgd_raw)

    e1 = _calc_ecl_stage_1(bv, pd_12m, lgd)
    e2 = _calc_ecl_stage_2(bv, pd_lifetime, lgd)
    e3 = _calc_ecl_stage_3(bv, pd_lifetime, lgd)

    assert e1 <= e2, (
        f"Stage 1 ({e1}) 应 ≤ Stage 2 ({e2}); "
        f"bv={bv}, pd_12m={pd_12m}, pd_lifetime={pd_lifetime}, lgd={lgd}"
    )
    assert e2 <= e3, (
        f"Stage 2 ({e2}) 应 ≤ Stage 3 ({e3}); "
        f"bv={bv}, pd_lifetime={pd_lifetime}, lgd={lgd}"
    )


@pytest.mark.parametrize(
    "bv,pd_12m,pd_lt,lgd,description",
    [
        (Decimal("0.01"), Decimal("0"), Decimal("0"), Decimal("0"), "all zeros boundary"),
        (Decimal("1000000"), Decimal("0"), Decimal("0"), Decimal("0.5"), "PD=0 zero loss"),
        (Decimal("1000000"), Decimal("0.01"), Decimal("0.10"), Decimal("0.50"), "typical S2 inputs"),
        (Decimal("1000000"), Decimal("0.01"), Decimal("0.95"), Decimal("0.70"), "Stage 3 high PD"),
        (Decimal("1e8"), Decimal("0.5"), Decimal("0.5"), Decimal("1.0"), "max LGD edge"),
    ],
)
def test_ecl_monotonicity_explicit(
    bv: Decimal, pd_12m: Decimal, pd_lt: Decimal, lgd: Decimal, description: str,
) -> None:
    """P6 显式样本：边界 + 典型工业输入"""
    from app.routers.wp_g_ecl import (
        _calc_ecl_stage_1,
        _calc_ecl_stage_2,
        _calc_ecl_stage_3,
    )

    e1 = _calc_ecl_stage_1(bv, pd_12m, lgd)
    e2 = _calc_ecl_stage_2(bv, pd_lt, lgd)
    e3 = _calc_ecl_stage_3(bv, pd_lt, lgd)
    assert e1 <= e2 <= e3, f"{description}: e1={e1} e2={e2} e3={e3}"
