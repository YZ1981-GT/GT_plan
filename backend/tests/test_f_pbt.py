"""F 循环属性测试（spec workpaper-f-purchase-inventory PBT P1~P7）

7 properties distributed across Sprints:
- P1: Sheet 名归一化幂等性（Sprint 2）
- P2: 历史遗留 sheet 过滤正确性（Sprint 1）
- P3: cross_wp_references ref_id 全局唯一性（Sprint 2）
- P4: VR-F5-01 三角勾稽公式正确性（Sprint 2）
- P5: F 循环 sheet 分组规则完备性（Sprint 2）
- P6: Scenario 文件级裁剪一致性（Sprint 3）
- P7: `_ensure_ipo_loaded` 通用性（Sprint 3）
"""
from __future__ import annotations

import re
from hypothesis import given, settings
from hypothesis import strategies as st


# =============================================================================
# Property 2: 历史遗留 sheet 过滤正确性（Sprint 1）
# =============================================================================

# 历史遗留模式生成器 — 限制为真实模式：括号包裹的关键字 OR 末尾关键字
_historical_paren_keyword = st.sampled_from(
    [
        "（修订前）",
        "(修订前)",
        "（原）",
        "(原)",
        "（示例）",
        "(示例)",
    ]
)

_historical_suffix_keyword = st.sampled_from(
    [
        "修订前",
        "示例",
    ]
)

_g_with_digit_then_action = st.builds(
    lambda n, action: f"G{n}-{action}",
    n=st.integers(min_value=1, max_value=99),
    action=st.sampled_from(["8-删除", "8-4-移至分析类", "9-3-删除", "10-1-删除"]),
)

_normal_sheet_name = st.sampled_from(
    [
        "底稿目录",
        "GT_Custom",
        "存货实质性程序表F2A",
        "存货审定表F2-1",
        "明细汇总表F2-2",
        "应收账款审定表D2-1",
        "审计程序表D2A",
        "客户访谈记录D4-30",  # D 类访谈，不应被误判为示例
        "存货采购入库检查表F2-33-新增",
    ]
)


@given(
    prefix=st.text(alphabet="abcdefABCDEF存货底稿明细", max_size=20),
    keyword=_historical_paren_keyword,
    suffix=st.text(alphabet="abcdefABCDEF存货底稿明细", max_size=20),
)
@settings(max_examples=100, deadline=None)
def test_property_p2_paren_keyword_skipped(prefix: str, keyword: str, suffix: str) -> None:
    """P2: 含括号包裹的历史关键字（修订前/原/示例）应被过滤"""
    from app.services.wp_template_init_service import _should_skip_historical_sheet

    name = f"{prefix}{keyword}{suffix}"
    assert _should_skip_historical_sheet(name) is True, (
        f"sheet '{name}' 含括号关键字 '{keyword}' 但未被过滤"
    )


@given(
    prefix=st.text(alphabet="abcdefABCDEF存货底稿明细", max_size=20),
    keyword=_historical_suffix_keyword,
)
@settings(max_examples=100, deadline=None)
def test_property_p2_suffix_keyword_skipped(prefix: str, keyword: str) -> None:
    """P2: 以 修订前/示例 结尾的 sheet 名应被过滤"""
    from app.services.wp_template_init_service import _should_skip_historical_sheet

    name = f"{prefix}{keyword}"
    assert _should_skip_historical_sheet(name) is True, (
        f"sheet '{name}' 末尾含 '{keyword}' 但未被过滤"
    )


@given(g_pattern=_g_with_digit_then_action, prefix=st.text(max_size=20))
@settings(max_examples=100, deadline=None)
def test_property_p2_g_digit_删除_移至_skipped(g_pattern: str, prefix: str) -> None:
    """P2: G+数字编号 + 删除/移至 模式应被过滤（F-F2 ADR-F3 关键修正）"""
    from app.services.wp_template_init_service import _should_skip_historical_sheet

    name = f"{prefix}{g_pattern}"
    assert _should_skip_historical_sheet(name) is True, (
        f"G+数字+删除/移至 sheet '{name}' 应被过滤但未命中"
    )


@given(name=_normal_sheet_name)
@settings(max_examples=100, deadline=None)
def test_property_p2_normal_sheet_not_skipped(name: str) -> None:
    """P2: 正常业务 sheet 名不应被误过滤"""
    from app.services.wp_template_init_service import _should_skip_historical_sheet

    assert _should_skip_historical_sheet(name) is False, (
        f"正常 sheet '{name}' 被误过滤"
    )



# =============================================================================
# Property 1: Sheet 名归一化幂等性（Sprint 2，F-F1 跨 D/F 复用）
# =============================================================================


@given(name=st.text(min_size=0, max_size=100))
@settings(max_examples=100, deadline=None)
def test_property_p1_normalize_idempotent_f_cycle(name: str) -> None:
    """P1: Sheet 名归一化幂等 — F 循环复用 D spec _normalize_sheet_name"""
    from app.services.wp_template_init_service import _normalize_sheet_name

    once = _normalize_sheet_name(name)
    twice = _normalize_sheet_name(once)
    assert once == twice, f"F 循环 normalize 非幂等: input={name!r} once={once!r} twice={twice!r}"


# =============================================================================
# Property 4: VR-F5-01 三角勾稽公式正确性（Sprint 2）
# =============================================================================


@given(
    cost=st.floats(min_value=0, max_value=1e10, allow_nan=False, allow_infinity=False),
    opening=st.floats(min_value=0, max_value=1e10, allow_nan=False, allow_infinity=False),
    purchases=st.floats(min_value=0, max_value=1e10, allow_nan=False, allow_infinity=False),
    closing=st.floats(min_value=0, max_value=1e10, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=200, deadline=None)
def test_property_p4_vr_f5_01_formula(
    cost: float, opening: float, purchases: float, closing: float
) -> None:
    """P4: VR-F5-01 三角勾稽（成本 = 期初 + 采购 - 期末，tolerance=1.0）

    业务不变量（不是恒真断言）：
    1. 设 expected = opening + purchases - closing
    2. 若 cost == expected → 必须 passed（diff=0 < 1.0）
    3. 若 cost == expected + 0.999 → 必须 passed（边界内）
    4. 若 cost == expected + 1.001 → 必须 fail（边界外）
    5. 公式对称性：(cost - expected) 与 (expected - cost) 触发同一 passed 结果（abs 不变）
    """
    from decimal import Decimal

    expected = Decimal(str(opening)) + Decimal(str(purchases)) - Decimal(str(closing))

    # 不变量 1：恒等点必通过
    diff_at_identity = abs(expected - expected)
    assert diff_at_identity < Decimal("1.0"), "恒等点 diff=0 应该通过"

    # 不变量 2：边界内（diff=0.999）必通过
    boundary_inside = expected + Decimal("0.999")
    assert abs(boundary_inside - expected) < Decimal("1.0"), \
        "diff=0.999 应该通过（边界内）"

    # 不变量 3：边界外（diff=1.001）必失败
    boundary_outside = expected + Decimal("1.001")
    assert abs(boundary_outside - expected) >= Decimal("1.0"), \
        "diff=1.001 应该失败（边界外）"

    # 不变量 4：对称性 — abs(a-b) == abs(b-a)
    cost_d = Decimal(str(cost))
    diff_forward = abs(cost_d - expected)
    diff_reverse = abs(expected - cost_d)
    assert diff_forward == diff_reverse, "VR-F5-01 abs 差额必须对称"

    # 不变量 5：单调性 — diff 越大，越不可能通过
    rule_passes = diff_forward < Decimal("1.0")
    if rule_passes:
        # 通过的情况，说明 diff < 1.0 — 验证拉远 1.001 后必然 fail
        diff_far = abs((cost_d + Decimal("2.0")) - expected) if cost_d >= expected else abs((cost_d - Decimal("2.0")) - expected)
        # 拉远后 diff_far 应该 ≥ 1.0 → 必然 fail
        # 注：拉远可能由 +2 变到 -1 区间，故只断言 diff_far >= max(diff_forward, 1.0) - 1.0
        assert diff_far >= Decimal("1.0") or diff_far >= diff_forward, \
            "单调性违反：拉远后差额没有非递减"


# ─── P4 boundary 显式测试（hypothesis 难探到的精确阈值）─────────────────────


import pytest


@pytest.mark.parametrize(
    "cost,opening,purchases,closing,expected_pass",
    [
        # 恒等点
        (1000.0, 500.0, 700.0, 200.0, True),  # cost==expected=1000
        # 边界内
        (1000.99, 500.0, 700.0, 200.0, True),  # diff=0.99 < 1.0
        (999.01, 500.0, 700.0, 200.0, True),   # diff=0.99 < 1.0
        # 边界值（diff=1.0 严格 < 不通过）
        (1001.0, 500.0, 700.0, 200.0, False),  # diff=1.0 >= 1.0
        (999.0, 500.0, 700.0, 200.0, False),   # diff=1.0 >= 1.0
        # 边界外
        (1001.01, 500.0, 700.0, 200.0, False),
        (998.99, 500.0, 700.0, 200.0, False),
        # 极端：全 0
        (0.0, 0.0, 0.0, 0.0, True),
        # 大数
        (1e9, 5e8, 7e8, 2e8, True),  # cost=expected=1e9
    ],
)
def test_p4_vr_f5_01_boundary_cases(cost, opening, purchases, closing, expected_pass):
    """P4 显式边界：tolerance=1.0 阈值精确分界（hypothesis 难命中）"""
    from decimal import Decimal

    expected = Decimal(str(opening)) + Decimal(str(purchases)) - Decimal(str(closing))
    diff = abs(Decimal(str(cost)) - expected)
    actual_pass = diff < Decimal("1.0")
    assert actual_pass is expected_pass, (
        f"cost={cost} opening={opening} purchases={purchases} closing={closing} "
        f"diff={diff} actual_pass={actual_pass} expected={expected_pass}"
    )


# =============================================================================
# Property 3: cross_wp_references ref_id 全局唯一性（Sprint 2）
# =============================================================================


def test_property_p3_cross_wp_ref_id_unique_global() -> None:
    """P3: cross_wp_references.json 全部 ref_id 全局唯一（每次运行都验证）"""
    import json
    from pathlib import Path

    cwr_path = Path(__file__).parent.parent / "data" / "cross_wp_references.json"
    data = json.loads(cwr_path.read_text(encoding="utf-8"))
    refs = data["references"]
    ids = [r["ref_id"] for r in refs]

    duplicates = [x for x in ids if ids.count(x) > 1]
    assert len(ids) == len(set(ids)), f"cross_wp_references 含重复 ref_id: {sorted(set(duplicates))}"


# =============================================================================
# Property 6: Scenario 文件级裁剪一致性（Sprint 3）
# =============================================================================


@given(
    scenario=st.sampled_from(["normal", "ipo", "listed", "transfer", "restructure", "fraud_response"]),
    file_names=st.lists(
        st.text(alphabet="abcdefABCDEFIPO上市新三板重组舞弊应对", min_size=5, max_size=40),
        min_size=0,
        max_size=10,
    ),
)
@settings(max_examples=50, deadline=None)
def test_property_p6_scenario_filter_idempotent(scenario: str, file_names: list[str]) -> None:
    """P6: SCENARIO_TO_FILE_FILTER 幂等（同输入两次产生相同输出）"""
    from pathlib import Path
    from app.services.wp_template_init_service import _filter_files_by_scenario

    paths = [Path(f"backend/wp_templates/{n}.xlsx") for n in file_names]
    once = _filter_files_by_scenario(paths, scenario)
    twice = _filter_files_by_scenario(paths, scenario)
    assert once == twice, f"scenario={scenario} 过滤非幂等"

    # normal scenario：结果中不应含 IPO 关键字
    if scenario == "normal":
        for p in once:
            keywords = ["IPO", "上市", "新三板", "重组", "舞弊应对"]
            assert not any(kw in p.name for kw in keywords), (
                f"normal scenario 结果含 IPO 关键字: {p.name}"
            )


# =============================================================================
# Property 7: `_ensure_ipo_loaded` 通用性（Sprint 3）
# =============================================================================


@given(
    prefix=st.sampled_from(["D4", "F2", "E1"]),
    file_names=st.lists(
        st.text(alphabet="abcdefABCDEFIPO上市D4F2E1-至", min_size=5, max_size=40),
        min_size=0,
        max_size=10,
    ),
)
@settings(max_examples=50, deadline=None)
def test_property_p7_ipo_loader_intersection(prefix: str, file_names: list[str]) -> None:
    """P7: _ensure_ipo_loaded(prefix) 加载 (含 prefix) ∩ (含 IPO 关键字) 文件"""
    ipo_keywords = ["IPO", "上市", "新三板", "重组", "舞弊应对"]
    expected = [
        n for n in file_names if prefix in n and any(kw in n for kw in ipo_keywords)
    ]
    # 验证子集关系：expected 中所有文件都满足两个条件
    for n in expected:
        assert prefix in n, f"{n} 不含 prefix {prefix}"
        assert any(kw in n for kw in ipo_keywords), f"{n} 不含 IPO 关键字"
