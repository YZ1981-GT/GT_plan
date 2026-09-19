"""H 类循环科目规格守卫 — Property 1/2/3/5/6。

Property 1: 语义槽完备且互斥（各循环槽键唯一）
Property 2: 否决词有效（移除后原值槽命中备抵科目）
Property 3: 裸备抵名不跨循环误命中
Property 5: 点号边界（`1601` 不命中 `16010`）
Property 6: 宁缺勿造（空科目表→兜底码；有科目表但无命中→`found=False`）

spec: .kiro/specs/h-cycle-four-table-extraction-and-account-mapping/
"""
from __future__ import annotations

import pytest

from app.services.four_table.semantic_account_resolver import (
    SemanticAccountSlot,
    SemanticAccountSpec,
    match_slot_in_chart,
)
from app.services.four_table.h_cycle_specs import H_CYCLE_SPECS, H_CYCLE_SLOT_PREFIXES


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures: 实证客户科目表（含跨循环干扰项）
# ──────────────────────────────────────────────────────────────────────────────

class _ChartRow:
    """轻量替身，与 `ChartRow` 协议兼容。"""
    def __init__(self, account_code: str, account_name: str, direction: str = "debit", source: str = "standard"):
        self.account_code = account_code
        self.account_name = account_name
        self.direction = direction
        self.source = source


# 含 H1~H10 全部真实科目 + 跨循环干扰项
FULL_CHART = [
    # H1 固定资产族
    _ChartRow("1601", "固定资产"),
    _ChartRow("1602", "累计折旧", "credit"),
    _ChartRow("1603", "固定资产减值准备", "credit"),
    _ChartRow("1606", "固定资产清理"),
    # H2 在建工程族
    _ChartRow("1604", "在建工程"),
    _ChartRow("1605", "工程物资"),
    # H3 投资性房地产族
    _ChartRow("1521", "投资性房地产"),
    _ChartRow("1525", "投资性房地产累计折旧", "debit"),   # direction 标注异常
    _ChartRow("1526", "投资性房地产累计摊销", "debit"),
    _ChartRow("1527", "投资性房地产减值准备", "debit"),
    # H5 油气资产族
    _ChartRow("1631", "油气资产"),
    _ChartRow("1632", "油气资产累计折耗", "credit"),
    # H7 生产性生物资产族
    _ChartRow("1621", "生产性生物资产"),
    _ChartRow("1622", "生产性生物资产累计折旧", "credit"),
    # H8 使用权资产族
    _ChartRow("1641", "使用权资产"),
    _ChartRow("1642", "使用权资产累计折旧", "credit"),
    _ChartRow("1643", "使用权资产减值准备", "credit"),
    # H9 租赁负债族
    _ChartRow("2601", "租赁负债", "credit"),
    _ChartRow("2602", "未确认融资费用"),
    # H10 损益
    _ChartRow("6115", "资产处置损益"),
    # 旧准则干扰项（不应被任何 H 循环命中）
    _ChartRow("1503", "可供出售金融资产"),
    _ChartRow("1504", "债权投资"),
    _ChartRow("1901", "待处理财产损溢"),
    _ChartRow("2205", "合同负债", "credit"),
    _ChartRow("1611", "融资租赁资产"),
    # 跨循环同名干扰（无形资产累计摊销）
    _ChartRow("1702", "无形资产累计摊销", "credit"),
]


# ──────────────────────────────────────────────────────────────────────────────
# Property 1: 语义槽完备且互斥
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("cycle", sorted(H_CYCLE_SPECS.keys()))
def test_slot_keys_unique(cycle: str):
    """各循环内槽键唯一。"""
    spec = H_CYCLE_SPECS[cycle]
    keys = [s.key for s in spec.slots]
    assert len(keys) == len(set(keys)), f"{cycle}: 重复槽键 {keys}"


@pytest.mark.parametrize("cycle", sorted(H_CYCLE_SPECS.keys()))
def test_slots_mutually_exclusive(cycle: str):
    """对完整科目表，各槽命中集互不相交。"""
    spec = H_CYCLE_SPECS[cycle]
    all_hit: dict[str, set[str]] = {}
    for slot in spec.slots:
        rows, _ = match_slot_in_chart(slot, FULL_CHART)
        codes = {r.account_code for r in rows}
        all_hit[slot.key] = codes

    keys = list(all_hit.keys())
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            overlap = all_hit[keys[i]] & all_hit[keys[j]]
            assert not overlap, (
                f"{cycle}: 槽 {keys[i]} 与 {keys[j]} 有交集 {overlap}"
            )


# ──────────────────────────────────────────────────────────────────────────────
# Property 2: 否决词有效（反向自检）
# ──────────────────────────────────────────────────────────────────────────────

# ─── Property 2 用例说明 ───
# `match_slot_in_chart` 有精确匹配优先逻辑：科目表里有裸「固定资产」时精确命中，
# 不会走包含匹配 → 否决词在此场景"看似冗余"。但客户科目表可能只有子科目形态
# （如「固定资产-XX部门」无裸名），此时退化到包含匹配，否决词才是唯一防线。
# 故反向自检使用**只有包含匹配能命中的科目表**（去掉精确项）。

# 循环 → (备抵科目名, 备抵码, 与原值名有包含关系的精确项码)
_EXCLUDE_EFFECTIVENESS_CASES = [
    # 科目表里去掉「固定资产」精确项后，「固定资产减值准备」等被包含匹配命中
    ("H1", "固定资产减值准备", "1603", "1601"),
    ("H1", "固定资产清理", "1606", "1601"),
    # 去掉「投资性房地产」后命中子串
    ("H3", "投资性房地产累计折旧", "1525", "1521"),
    ("H3", "投资性房地产累计摊销", "1526", "1521"),
    # 去掉「生产性生物资产」后命中子串
    ("H7", "生产性生物资产累计折旧", "1622", "1621"),
    # 去掉「使用权资产」后命中子串
    ("H8", "使用权资产累计折旧", "1642", "1641"),
    ("H8", "使用权资产减值准备", "1643", "1641"),
]


@pytest.mark.parametrize("cycle,contra_name,contra_code,exact_code", _EXCLUDE_EFFECTIVENESS_CASES)
def test_exclude_names_effective(cycle: str, contra_name: str, contra_code: str, exact_code: str):
    """在只有包含匹配能命中的科目表中，否决词阻止原值槽命中备抵科目。"""
    spec = H_CYCLE_SPECS[cycle]
    gross_slot = next(s for s in spec.slots if s.key == "gross")

    # 构造一份去掉精确项的科目表（只剩包含匹配的候选）
    chart_without_exact = [r for r in FULL_CHART if r.account_code != exact_code]

    # 带否决词：不应命中备抵科目
    rows_with, _ = match_slot_in_chart(gross_slot, chart_without_exact)
    hit_codes = {r.account_code for r in rows_with}
    assert contra_code not in hit_codes, (
        f"{cycle}: 原值槽带否决词仍命中 {contra_code}({contra_name})"
    )

    # 移除否决词：应命中备抵科目（反向自检证明否决词有效）
    naked_slot = SemanticAccountSlot(
        key=gross_slot.key,
        names=gross_slot.names,
        exclude_names=(),  # 移除否决词
        fallback_standard_codes=gross_slot.fallback_standard_codes,
        label=gross_slot.display_label,
    )
    rows_without, _ = match_slot_in_chart(naked_slot, chart_without_exact)
    naked_codes = {r.account_code for r in rows_without}
    assert contra_code in naked_codes, (
        f"{cycle}: 反向自检失败 — 移除否决词后原值槽仍不命中 {contra_code}({contra_name})，"
        "说明否决词对该科目无效（该备抵科目可能名称不含原值名作子串）"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Property 3: 裸备抵名不跨循环误命中
# ──────────────────────────────────────────────────────────────────────────────

# H1 的 accum_dep（裸「累计折旧」）不应命中 1525/1622/1642/1632
_CROSS_CYCLE_EXCLUSION_CASES = [
    ("H1", "accum_dep", {"1525", "1622", "1632", "1642"}),
    ("H7", "accum_dep", {"1525", "1602", "1642"}),
    ("H8", "accum_dep", {"1525", "1602", "1622", "1632"}),
]


@pytest.mark.parametrize("cycle,slot_key,forbidden_codes", _CROSS_CYCLE_EXCLUSION_CASES)
def test_no_cross_cycle_hit(cycle: str, slot_key: str, forbidden_codes: set[str]):
    """备抵槽的否决词阻止跨循环误命中。"""
    spec = H_CYCLE_SPECS[cycle]
    slot = next(s for s in spec.slots if s.key == slot_key)
    rows, _ = match_slot_in_chart(slot, FULL_CHART)
    hit_codes = {r.account_code for r in rows}
    overlap = hit_codes & forbidden_codes
    assert not overlap, (
        f"{cycle}.{slot_key} 跨循环误命中 {overlap}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Property 5: 点号边界
# ──────────────────────────────────────────────────────────────────────────────

def test_dot_boundary_not_matching_longer_code():
    """`filter_by_prefixes` 的点号边界：`1601` 不匹配 `16010`。"""
    from app.services.four_table.leaf_aggregation import filter_by_prefixes

    # 构造含无点号同前缀的行
    class FakeRow:
        def __init__(self, code):
            self.account_code = code

    rows = [FakeRow("1601"), FakeRow("1601.01"), FakeRow("16010"), FakeRow("1602")]
    result = filter_by_prefixes(rows, ["1601"])
    result_codes = [r.account_code for r in result]
    assert "16010" not in result_codes, "点号边界失效：`1601` 命中了 `16010`"
    assert "1601" in result_codes
    assert "1601.01" in result_codes


# ──────────────────────────────────────────────────────────────────────────────
# Property 6: 宁缺勿造
# ──────────────────────────────────────────────────────────────────────────────

def test_no_match_in_empty_chart():
    """空科目表时所有槽不命中。"""
    for cycle, spec in H_CYCLE_SPECS.items():
        for slot in spec.slots:
            rows, exact = match_slot_in_chart(slot, [])
            assert rows == [], f"{cycle}.{slot.key}: 空表不应命中"


def test_no_match_for_irrelevant_chart():
    """科目表不含 H 类科目时所有槽不命中。"""
    irrelevant = [
        _ChartRow("1001", "库存现金"),
        _ChartRow("1002", "银行存款"),
        _ChartRow("2201", "应付票据", "credit"),
    ]
    for cycle, spec in H_CYCLE_SPECS.items():
        for slot in spec.slots:
            rows, _ = match_slot_in_chart(slot, irrelevant)
            assert rows == [], f"{cycle}.{slot.key}: 无关科目表不应命中"


# ──────────────────────────────────────────────────────────────────────────────
# 旧错误码必须不被命中（反向自检）
# ──────────────────────────────────────────────────────────────────────────────

_OLD_ERROR_CODES = {"1503", "1504", "1901", "2205", "1611"}


def test_old_error_codes_not_hit_by_any_slot():
    """旧错误码在完整科目表中不被任何 H 循环的任何槽命中。"""
    for cycle, spec in H_CYCLE_SPECS.items():
        for slot in spec.slots:
            rows, _ = match_slot_in_chart(slot, FULL_CHART)
            hit_codes = {r.account_code for r in rows}
            overlap = hit_codes & _OLD_ERROR_CODES
            assert not overlap, (
                f"{cycle}.{slot.key} 命中旧错误码 {overlap}"
            )


# ──────────────────────────────────────────────────────────────────────────────
# 空兜底槽的语义（2026-08-03 复盘建议 5）
#
# 平台标准科目表无「在建工程减值准备」独立编码 → H2.impairment 的
# `fallback_standard_codes=()`。这是**有意为之**：
#   - 客户自建该科目 → 按名称命中，取数正常
#   - 客户没有       → found=False，界面显示「本项目无此科目」（宁缺勿造）
# 若硬塞一个兜底码，在客户没有该科目时会取到别的科目的钱 —— 即本 spec 修的 P0 类缺陷。
# ──────────────────────────────────────────────────────────────────────────────

_EMPTY_FALLBACK_SLOTS = [
    ("H2", "impairment", "在建工程减值准备"),
    ("H5", "impairment", "油气资产减值准备"),
    ("H7", "impairment", "生产性生物资产减值准备"),
]


@pytest.mark.parametrize("cycle,slot_key,account_name", _EMPTY_FALLBACK_SLOTS)
def test_empty_fallback_slot_has_no_fallback_code(cycle: str, slot_key: str, account_name: str):
    """这些槽必须保持空兜底 —— 塞兜底码会在客户无该科目时取错科目的钱。"""
    spec = H_CYCLE_SPECS[cycle]
    slot = next((s for s in spec.slots if s.key == slot_key), None)
    assert slot is not None, f"{cycle} 缺少 {slot_key} 槽"
    assert not slot.fallback_standard_codes, (
        f"{cycle}.{slot_key}（{account_name}）不得声明兜底码 —— "
        "平台标准科目表无该科目独立编码，硬塞兜底会在客户无此科目时取错科目"
    )


@pytest.mark.parametrize("cycle,slot_key,account_name", _EMPTY_FALLBACK_SLOTS)
def test_empty_fallback_slot_still_matches_client_account(
    cycle: str, slot_key: str, account_name: str
):
    """反向自检：客户自建该科目时仍能按名称命中（证明保留该槽有意义）。"""
    spec = H_CYCLE_SPECS[cycle]
    slot = next(s for s in spec.slots if s.key == slot_key)
    # 构造一份含该科目的客户科目表（用一个不与任何兜底码冲突的编码）
    chart = list(FULL_CHART) + [_ChartRow("1699", account_name, "credit", "client")]
    rows, _ = match_slot_in_chart(slot, chart)
    hit = {r.account_code for r in rows}
    assert "1699" in hit, (
        f"{cycle}.{slot_key} 未能按名称命中客户自建的「{account_name}」 → "
        "该槽形同虚设，应重新评估 names/exclude_names"
    )
