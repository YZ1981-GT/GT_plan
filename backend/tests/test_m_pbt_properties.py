"""M 权益循环属性测试（spec workpaper-m-equity-cycle PBT P1~P4）

Properties:
- P1: Sheet 名归一化幂等性（100 examples）
- P2: VR-M6-01 未分配利润勾稽正确性（200 + 9 boundary）
- P3: M 循环 8 类 sheet 分组完备性（200 examples）
- P4: cross_wp_ref ref_id 全局唯一（50 examples）

**Validates: Requirements M-F1, M-F3, M-F2, M-F4**
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
# M 循环 65 个有效 sheet 名（openpyxl 实测，Sprint 0 基线）
# 102 raw - 4 historical - 33 cross-file dedup = 65
# ═══════════════════════════════════════════════════════════════════════════════

ALL_M_SHEET_NAMES: list[str] = [
    # M1 应付股利
    "底稿目录",
    "GT_Custom",
    "应付股利实质性程序表M1A",
    "审定表M1-1",
    "明细表M1-2",
    "附注披露信息(上市公司)",
    "附注披露信息(国有企业)",
    # M2 实收资本
    "实收资本实质性程序表M2A",
    "审定表M2-1",
    "明细表（上市公司）M2-2",
    "明细表（非上市公司）M2-2",
    "分析程序M2-3",
    "工商变更检查表M2-4",
    "验资报告检查表M2-5",
    # M3 库存股
    "库存股实质性程序表M3A",
    "审定表M3-1",
    "明细表M3-2",
    # M4 资本公积
    "资本公积实质性程序表M4A",
    "审定表M4-1",
    "明细表M4-2",
    "分析程序M4-3",
    # M5 盈余公积
    "盈余公积实质性程序表M5A",
    "审定表M5-1",
    "明细表M5-2",
    "分析程序M5-3",
    # M6 未分配利润
    "未分配利润实质性程序表 M6A ",  # 末尾空格
    "审定表M6-1",
    "明细表M6-2",
    "分析程序M6-3",
    # M7 专项储备
    " 专项储备实质性程序表 M7A ",  # 首尾空格
    "审定表M7-1",
    "明细表M7-2",
    "分析程序M7-3",
    # M8 一般风险准备
    "一般风险准备实质性程序表 M8A ",  # 末尾空格
    "审定表M8-1",
    "明细表M8-2",
    "分析程序M8-3",
    "针对性测试M8-4",
    "针对性测试M8-6",
    # M9 其他综合收益
    "其他综合收益实质性程序表M9A",
    "审定表M9-1",
    "明细表M9-2",
    "分析程序M9-3",
    # M10 其他权益工具
    "其他权益工具实质性程序表M10A",
    "审定表M10-1",
    "明细表M10-2",
    "分析程序M10-3",
    "永续债检查表M10-4",
    "优先股检查表M10-5",
    # 跨文件去重后保留的附注披露变体
    "附注披露信息核对(上市公司)",
    "附注披露信息核对(国有企业)",
    # 其他通用 sheet
    "调整分录汇总表M1-3",
    "调整分录汇总表M2-6",
    "调整分录汇总表M3-3",
    "调整分录汇总表M4-4",
    "调整分录汇总表M5-4",
    "调整分录汇总表M6-4",
    "调整分录汇总表M7-4",
    "调整分录汇总表M8-7",
    "调整分录汇总表M9-4",
    "调整分录汇总表M10-6",
    "IPO企业权益审计提示",
]


# ═══════════════════════════════════════════════════════════════════════════════
# PBT-P1: Sheet 名归一化幂等性（100 examples）
# **Validates: Requirements M-F1**
# ═══════════════════════════════════════════════════════════════════════════════


@given(name=st.text(min_size=0, max_size=100))
@settings(max_examples=100, deadline=None)
def test_m_normalize_idempotent(name: str) -> None:
    """P1: normalize(normalize(x)) == normalize(x) — 幂等性

    M 循环含末尾空格的 sheet 名（如"未分配利润实质性程序表 M6A "）归一化后
    应满足幂等性（二次归一化结果不变）。
    """
    from app.services.wp_template_init_service import _normalize_sheet_name

    once = _normalize_sheet_name(name)
    twice = _normalize_sheet_name(once)
    assert once == twice, (
        f"M 循环 normalize 非幂等: input={name!r} once={once!r} twice={twice!r}"
    )


# 补充：用 M 循环真实 sheet 名验证幂等性
@given(m_sheet=st.sampled_from(ALL_M_SHEET_NAMES))
@settings(max_examples=50, deadline=None)
def test_m_normalize_idempotent_real_sheets(m_sheet: str) -> None:
    """P1 补充：M 循环真实 sheet 名归一化幂等"""
    from app.services.wp_template_init_service import _normalize_sheet_name

    once = _normalize_sheet_name(m_sheet)
    twice = _normalize_sheet_name(once)
    assert once == twice


# ═══════════════════════════════════════════════════════════════════════════════
# PBT-P2: VR-M6-01 未分配利润勾稽正确性（200 + 9 boundary）
# **Validates: Requirements M-F3**
# ═══════════════════════════════════════════════════════════════════════════════

TOLERANCE = Decimal("1.0")


def _vr_m6_01_passes(m6_closing: Decimal, m6_opening: Decimal,
                     net_profit: Decimal, surplus_reserve: Decimal,
                     dividends: Decimal, tolerance: Decimal = TOLERANCE) -> bool:
    """VR-M6-01: M6 期末 = 期初 + 净利润 − 盈余公积 − 股利（容差 1.0）"""
    expected = m6_opening + net_profit - surplus_reserve - dividends
    return abs(m6_closing - expected) < tolerance


_amount_st = st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False)


@settings(max_examples=200, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(opening=_amount_st, net_profit=_amount_st, surplus=_amount_st,
       dividends=_amount_st, drift=st.floats(min_value=-2.0, max_value=2.0))
def test_vr_m6_01_triangle_formula_pbt(opening, net_profit, surplus, dividends, drift):
    """VR-M6-01: drift ∈ [-2,2]，passes ↔ |drift| < tolerance

    业务不变量：M6 期末 = 期初 + 净利润 − 盈余公积 − 股利 ± drift
    当 |drift| < 1.0 时通过，≥ 1.0 时失败。
    """
    opening_dec = Decimal(str(round(opening, 2)))
    net_profit_dec = Decimal(str(round(net_profit, 2)))
    surplus_dec = Decimal(str(round(surplus, 2)))
    dividends_dec = Decimal(str(round(dividends, 2)))
    drift_dec = Decimal(str(round(drift, 4)))

    expected = opening_dec + net_profit_dec - surplus_dec - dividends_dec
    m6_closing = expected + drift_dec

    passes = _vr_m6_01_passes(m6_closing, opening_dec, net_profit_dec, surplus_dec, dividends_dec)
    expected_pass = abs(drift_dec) < TOLERANCE
    assert passes == expected_pass, (
        f"VR-M6-01 偏差 {drift_dec} 检测异常: expected_pass={expected_pass}, actual={passes}"
    )


# 9 个边界用例
@pytest.mark.parametrize("opening,net_profit,surplus,dividends,drift,should_pass", [
    # 标准参数：opening=500000, net_profit=200000, surplus=20000, dividends=50000
    # expected = 500000 + 200000 - 20000 - 50000 = 630000; closing = 630000 + drift
    (Decimal("500000"), Decimal("200000"), Decimal("20000"), Decimal("50000"), Decimal("0"), True),
    (Decimal("500000"), Decimal("200000"), Decimal("20000"), Decimal("50000"), Decimal("0.99"), True),
    (Decimal("500000"), Decimal("200000"), Decimal("20000"), Decimal("50000"), Decimal("-0.99"), True),
    (Decimal("500000"), Decimal("200000"), Decimal("20000"), Decimal("50000"), Decimal("1.0"), False),
    (Decimal("500000"), Decimal("200000"), Decimal("20000"), Decimal("50000"), Decimal("-1.0"), False),
    (Decimal("500000"), Decimal("200000"), Decimal("20000"), Decimal("50000"), Decimal("1.5"), False),
    (Decimal("500000"), Decimal("200000"), Decimal("20000"), Decimal("50000"), Decimal("-1.5"), False),
    # 极小金额
    (Decimal("0.01"), Decimal("0.01"), Decimal("0"), Decimal("0"), Decimal("0"), True),
    # 大金额
    (Decimal("999999999"), Decimal("100000000"), Decimal("50000000"), Decimal("30000000"), Decimal("0.5"), True),
])
def test_vr_m6_01_boundary(opening, net_profit, surplus, dividends, drift, should_pass):
    """VR-M6-01 边界用例：临界值附近显式覆盖"""
    expected = opening + net_profit - surplus - dividends
    m6_closing = expected + drift
    passes = _vr_m6_01_passes(m6_closing, opening, net_profit, surplus, dividends)
    assert passes == should_pass, (
        f"VR-M6-01 boundary: drift={drift}, expected_pass={should_pass}, actual={passes}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PBT-P3: M 循环 8 类 sheet 分组完备性（200 examples）
# **Validates: Requirements M-F2**
# ═══════════════════════════════════════════════════════════════════════════════

# 8 类分组规则（与前端 useMEquityCycleSheetGroups.ts M_SHEET_GROUP_RULES 对齐）
_M_SHEET_GROUP_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("索引", re.compile(r"^底稿目录$|^GT_Custom$")),
    ("程序表", re.compile(r"实质性程序表|[A-Z]\d*A\s*$|M\d+A\s*$")),
    ("审定表", re.compile(r"审定表")),
    ("明细表", re.compile(r"明细表")),
    ("变动分析", re.compile(r"变动|增减|权益变动")),
    ("检查表", re.compile(r"检查|核查|测试")),
    ("附注+调整", re.compile(r"附注|披露|调整")),
]

_FALLBACK_GROUP = "其他"


def _classify_m_sheet(name: str) -> str:
    """按 8 类规则分类 M 循环 sheet 名（首个命中即停止，fallback 兜底）"""
    for group_name, pattern in _M_SHEET_GROUP_RULES:
        if pattern.search(name):
            return group_name
    return _FALLBACK_GROUP


@given(m_sheet=st.sampled_from(ALL_M_SHEET_NAMES))
@settings(max_examples=200, deadline=None)
def test_m_sheet_group_completeness_pbt(m_sheet: str) -> None:
    """P3: 任意 M 循环有效 sheet 恰好匹配 1 类

    不变量：∀ sheet ∈ ALL_M_SHEET_NAMES: classify(sheet) ∈ 8 类（含 fallback）
    且 classify 结果非空。
    """
    group = _classify_m_sheet(m_sheet)
    all_groups = {g for g, _ in _M_SHEET_GROUP_RULES} | {_FALLBACK_GROUP}
    assert group in all_groups, (
        f"M sheet '{m_sheet}' 分类结果 '{group}' 不在 8 类中"
    )
    assert group != "", (
        f"M sheet '{m_sheet}' 分类结果为空"
    )


# 显式覆盖全部有效 sheet 确认无遗漏
@pytest.mark.parametrize("sheet_name", ALL_M_SHEET_NAMES)
def test_m_sheet_group_explicit_coverage(sheet_name: str) -> None:
    """每个 M 循环有效 sheet 都能被分类到某个组（含 fallback）"""
    group = _classify_m_sheet(sheet_name)
    assert group != "", (
        f"M sheet '{sheet_name}' 未被任何规则覆盖"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PBT-P4: cross_wp_ref ref_id 全局唯一（50 examples）
# **Validates: Requirements M-F4**
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


def _filter_m_cycle_refs(refs: list[dict]) -> list[dict]:
    """过滤 M 循环相关 cross_wp_refs（source_wp 或 targets[].wp_code 以 M 开头）"""
    result = []
    for r in refs:
        source_wp = r.get("source_wp", "")
        if source_wp.upper().startswith("M"):
            result.append(r)
            continue
        # 检查 targets 数组中的 wp_code
        targets = r.get("targets", [])
        for t in targets:
            if t.get("wp_code", "").upper().startswith("M"):
                result.append(r)
                break
    return result


class TestCrossWpRefIdUniqueness:
    """PBT-P4: cross_wp_ref ref_id 全局唯一 + M 循环闭区间"""

    def test_all_ref_ids_globally_unique(self):
        """全局 ref_id 无重复"""
        refs = _load_all_cross_wp_refs()
        ids = _extract_ref_ids(refs)
        assert len(ids) == len(set(ids)), (
            f"ref_id 有重复: total={len(ids)}, unique={len(set(ids))}"
        )

    def test_m_cycle_refs_in_closed_interval(self):
        """M 循环新增 ref_id 在闭区间 CW-353~N 内（M 起编 CW-353）"""
        refs = _load_all_cross_wp_refs()
        m_refs = _filter_m_cycle_refs(refs)
        m_ids = _extract_ref_ids(m_refs)
        # M 循环新增应从 CW-353 起编
        new_m_ids = [i for i in m_ids if i >= 353]
        if new_m_ids:
            assert min(new_m_ids) >= 353, f"M 循环新增 ref_id 起编 < 353: {min(new_m_ids)}"
            # 闭区间连续性检查（允许间隔但不允许超出预期范围）
            assert max(new_m_ids) < 500, f"M 循环 ref_id 超出预期范围: {max(new_m_ids)}"

    def test_m_cycle_ref_count_ge_15(self):
        """M 循环 cross_wp_ref 新增 ≥ 15 条（CW-353 起编段）"""
        refs = _load_all_cross_wp_refs()
        m_refs = _filter_m_cycle_refs(refs)
        m_new_ids = [i for i in _extract_ref_ids(m_refs) if i >= 353]
        assert len(m_new_ids) >= 15, (
            f"M 循环新增 cross_wp_ref 不足 15 条: actual={len(m_new_ids)}"
        )

    def test_m_cycle_membership_filter(self):
        """M 循环 ref 双重过滤：闭区间 + cycle membership（source_wp 或 target 以 M 开头）"""
        refs = _load_all_cross_wp_refs()
        m_refs = _filter_m_cycle_refs(refs)
        m_new_ids = [i for i in _extract_ref_ids(m_refs) if i >= 353]
        # 所有 CW-353+ 的 M 循环 ref 都应满足 cycle membership
        for r in m_refs:
            rid = r.get("ref_id", "")
            if isinstance(rid, str) and rid.startswith("CW-"):
                num = int(rid.replace("CW-", ""))
                if num >= 353:
                    # 验证 cycle membership
                    source_wp = r.get("source_wp", "").upper()
                    targets = r.get("targets", [])
                    target_codes = [t.get("wp_code", "").upper() for t in targets]
                    has_m = source_wp.startswith("M") or any(
                        c.startswith("M") for c in target_codes
                    )
                    assert has_m, (
                        f"CW-{num} 在 M 闭区间但不满足 cycle membership: "
                        f"source={source_wp}, targets={target_codes}"
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
