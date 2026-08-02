"""L 类科目定位与叶子分类守卫.

覆盖 Property 1（叶子聚合守恒）/ Property 2（科目码属本循环）/ Property 6（否决词生效）。

**不连库**：科目语义一律以 `backend/data/standard_account_chart.json` 裁决，故可进 CI。

spec: .kiro/specs/l-cycle-four-table-extraction-and-disclosure-alignment/
      Requirements 1.1, 2.1, 2.2, 3.2~3.4, 5.2, 11.3, 11.4
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.services.l_cycle_extraction.account_scope import (
    BUCKET_CURRENT_PORTION,
    BUCKET_OTHER,
    L_CYCLE_SPECS,
    bucket_defs_payload,
    classify_l_leaf,
    is_current_portion,
    pick_row_codes,
)

_CHART_PATH = Path(__file__).resolve().parents[2] / "data" / "standard_account_chart.json"


@pytest.fixture(scope="module")
def standard_chart() -> dict[str, str]:
    """标准科目表 ``{code: name}``（企业会计准则口径）。"""
    data = json.loads(_CHART_PATH.read_text(encoding="utf-8"))
    return {
        str(a["code"]).strip(): str(a.get("name") or "").strip()
        for a in data["accounts"]
        if a.get("code")
    }


# ---------------------------------------------------------------------------
# 反向自检：标准科目表确实被读到，且确实包含本文件依赖的判据
# ---------------------------------------------------------------------------


def test_standard_chart_loaded_and_meaningful(standard_chart):
    """自检：科目表非空且含本文件用作判据的关键码。"""
    assert len(standard_chart) > 100
    for code in ("2001", "2231", "2501", "2502", "2601", "2701", "2711", "2801", "2901", "6603"):
        assert code in standard_chart, f"标准科目表缺 {code}，本文件判据失效"


# ---------------------------------------------------------------------------
# Property 2: 兜底码属标准科目表且语义正确
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("wp_code", sorted(L_CYCLE_SPECS))
def test_fallback_codes_exist_in_standard_chart(wp_code, standard_chart):
    """每个循环的兜底码都必须是真科目（L7 无兜底码，跳过）。"""
    spec = L_CYCLE_SPECS[wp_code]
    for code in spec.fallback_codes:
        assert code in standard_chart, f"{wp_code} 兜底码 {code} 不在标准科目表"


@pytest.mark.parametrize(
    ("wp_code", "expected_name"),
    [
        ("L1", "短期借款"),
        ("L2", "应付利息"),
        ("L3", "长期借款"),
        ("L4", "应付债券"),
        ("L5", "长期应付款"),
        ("L6", "专项应付款"),
        ("L8", "财务费用"),
    ],
)
def test_fallback_code_semantics_match_cycle(wp_code, expected_name, standard_chart):
    """兜底码的标准科目**名称**必须就是该循环的科目（防「取错科目族」）。"""
    spec = L_CYCLE_SPECS[wp_code]
    assert spec.fallback_codes, f"{wp_code} 应有兜底码"
    names = [standard_chart[c] for c in spec.fallback_codes]
    assert expected_name in names, f"{wp_code} 兜底码语义为 {names}，期望含 {expected_name}"


def test_l7_declares_no_fallback_code(standard_chart):
    """L7 其他非流动负债宁缺勿造：不得声明兜底码。

    依据：CAS 标准科目表无「其他非流动负债」科目；``report_config``
    ``BS-071/BS-097`` 引用的 ``2901`` 语义是递延所得税负债。
    """
    spec = L_CYCLE_SPECS["L7"]
    assert spec.fallback_codes == ()
    assert "其他非流动负债" not in set(standard_chart.values())


# ---------------------------------------------------------------------------
# 旧口径反证（这两条在改造前的实现下必红）
# ---------------------------------------------------------------------------


def test_2601_is_lease_liability_not_special_payable(standard_chart):
    """反证：``2601`` 是租赁负债（H 循环），不是专项应付款。

    🔴 改造前 `_l6_special_payables` 硬编码 ``2601`` → 取错整个科目族，
    且 ``tb_balance`` 该前缀 0 行 → 取数恒空。
    """
    assert standard_chart["2601"] == "租赁负债"
    assert standard_chart["2711"] == "专项应付款"
    assert "2601" not in L_CYCLE_SPECS["L6"].fallback_codes
    assert "2711" in L_CYCLE_SPECS["L6"].fallback_codes


def test_2901_is_deferred_tax_not_other_noncurrent(standard_chart):
    """反证：``2901`` 是递延所得税负债，``2801`` 是预计负债。

    🔴 改造前 `_l7_other_noncurrent_liabilities` 硬编码 ``2801``；
    ``report_config`` 该行又写 ``TB('2901')`` 且与 ``BS-070/BS-096`` 撞码。
    两者都不得成为 L7 的取数科目。
    """
    assert standard_chart["2901"] == "递延所得税负债"
    assert standard_chart["2801"] == "预计负债"
    for bad in ("2801", "2901"):
        assert bad not in L_CYCLE_SPECS["L7"].fallback_codes


# ---------------------------------------------------------------------------
# Property 6: 分类器（真实 tb_balance 科目名）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("wp_code", "account_name", "expected"),
    [
        # L2 应付利息 —— tb_balance 2231.01~.04 实测名
        ("L2", "应付利息_分期付息到期还本的长期借款利息", "long_term_loan_interest"),
        ("L2", "应付利息_企业债券利息", "bond_interest"),
        ("L2", "应付利息_短期借款应付利息", "short_term_loan_interest"),
        ("L2", "应付利息_应收账款出表利息", "ar_derecognition_interest"),
        # L3 长期借款 —— 2501.01/.02
        ("L3", "长期借款_长期借款", "non_current"),
        ("L3", "长期借款_一年内到期的长期借款", BUCKET_CURRENT_PORTION),
        # L4 应付债券 —— 2502.01~.03
        ("L4", "应付债券_面值", "face_value"),
        ("L4", "应付债券_利息调整", "interest_adjustment"),
        ("L4", "应付债券_应计利息", "accrued_interest"),
        # L5 长期应付款 —— 2701.01~.03/.99
        ("L5", "长期应付款_应付融资租赁款", "finance_lease"),
        ("L5", "长期应付款_应付长期保证金", "long_term_deposit"),
        ("L5", "长期应付款_应付长期借款", "long_term_loan"),
        ("L5", "长期应付款_一年内到期的长期应付款", BUCKET_CURRENT_PORTION),
        # L8 财务费用 —— 6603.01~.99
        ("L8", "财务费用_利息支出", "interest_expense"),
        ("L8", "财务费用_利息支出_借款利息（金融机构）", "interest_expense"),
        ("L8", "财务费用_利息支出_债券利息", "interest_expense"),
        ("L8", "财务费用_利息支出_租赁负债利息", "interest_expense"),
        ("L8", "财务费用_利息收入", "interest_income"),
        ("L8", "财务费用_利息收入_金融机构", "interest_income"),
        ("L8", "财务费用_手续费支出", "handling_fee"),
        ("L8", "财务费用_汇兑损益", "exchange_gain_loss"),
        ("L8", "财务费用_现金折扣支出", "cash_discount_expense"),
        ("L8", "财务费用_现金折扣收取", "cash_discount_received"),
        ("L8", "财务费用_担保费", "guarantee_fee"),
        ("L8", "财务费用_金融工具转移_保理利息及手续费", "financial_instrument_transfer"),
        ("L8", "财务费用_金融工具转移_ABS支出及手续费", "financial_instrument_transfer"),
        ("L8", "财务费用_其他", BUCKET_OTHER),
    ],
)
def test_classify_l_leaf_real_account_names(wp_code, account_name, expected):
    """按 `tb_balance` 实测科目名分类（名称优先，禁按编码）。"""
    assert classify_l_leaf(wp_code, account_name) == expected


def test_current_portion_takes_precedence_over_business_bucket():
    """「一年内到期」判定必须前置于业务桶。

    🔴 ``2701.99 长期应付款_一年内到期的长期应付款`` 同时含「长期应付款」，
    若先过业务桶会被 ``long_term_loan`` 吞掉 → 「减一年内到期」列恒 0。
    """
    name = "长期应付款_一年内到期的长期应付款"
    assert is_current_portion(name) is True
    assert classify_l_leaf("L5", name) == BUCKET_CURRENT_PORTION
    assert classify_l_leaf("L5", name) != "long_term_loan"


def test_exclude_keywords_are_required_for_interest_direction():
    """反证：去掉 L8 「利息收入」桶后，收入类会被「利息支出」误吞。

    直接构造替身 spec 验证「桶顺序 + 关键字」的必要性（不改真实真源）。
    """
    from app.services.l_cycle_extraction import account_scope as mod

    original = mod.L_CYCLE_SPECS["L8"]
    # 去掉 interest_income 桶，模拟"只按『利息』宽匹配"的错误实现
    broken_buckets = tuple(
        replace(b, keywords=("利息",)) if b.key == "interest_expense" else b
        for b in original.buckets
        if b.key != "interest_income"
    )
    mod.L_CYCLE_SPECS["L8"] = replace(original, buckets=broken_buckets)
    try:
        assert classify_l_leaf("L8", "财务费用_利息收入_金融机构") == "interest_expense"
    finally:
        mod.L_CYCLE_SPECS["L8"] = original
    # 恢复后正确
    assert classify_l_leaf("L8", "财务费用_利息收入_金融机构") == "interest_income"


def test_cash_discount_received_not_swallowed_by_expense():
    """「现金折扣收取」不得被「现金折扣支出」桶吞掉（否决词 + 顺序双保险）。"""
    assert classify_l_leaf("L8", "财务费用_现金折扣收取") == "cash_discount_received"
    assert classify_l_leaf("L8", "财务费用_现金折扣支出") == "cash_discount_expense"


def test_classify_unknown_cycle_and_empty_name():
    """未登记循环 / 空名称一律归 other（金额不丢弃）。"""
    assert classify_l_leaf("L9", "任意") == BUCKET_OTHER
    assert classify_l_leaf("L8", "") == BUCKET_OTHER
    assert is_current_portion("") is False


# ---------------------------------------------------------------------------
# 桶定义下发 & 报表行挑选
# ---------------------------------------------------------------------------


def test_bucket_labels_are_chinese_and_unique():
    """桶标签中文且同循环内唯一（前端不抄第二份）。"""
    for wp_code in L_CYCLE_SPECS:
        payload = bucket_defs_payload(wp_code)
        labels = [p["label"] for p in payload]
        keys = [p["key"] for p in payload]
        assert len(labels) == len(set(labels)), f"{wp_code} 桶标签重复"
        assert len(keys) == len(set(keys)), f"{wp_code} 桶键重复"
        for p in payload:
            assert p["label"].strip(), f"{wp_code} 桶 {p['key']} 标签为空"
            assert not p["label"].isascii(), f"{wp_code} 桶 {p['key']} 标签非中文"


def test_split_current_portion_cycles_expose_the_bucket():
    """需拆一年内到期的循环，桶定义里必须含该桶（前端才有列可渲染）。"""
    for wp_code, spec in L_CYCLE_SPECS.items():
        keys = {p["key"] for p in bucket_defs_payload(wp_code)}
        if spec.split_current_portion:
            assert BUCKET_CURRENT_PORTION in keys, f"{wp_code} 缺一年内到期桶"
        else:
            assert BUCKET_CURRENT_PORTION not in keys


@pytest.mark.parametrize(
    ("standards", "expected_first"),
    [
        (["listed_standalone", "listed", "standalone"], "BS-044"),
        (["soe_standalone", "soe", "standalone"], "BS-055"),
        ([], "BS-055"),
    ],
)
def test_pick_row_codes_follows_standard(standards, expected_first):
    """报表行编码按准则挑选（同科目两准则编码不同）。"""
    codes = pick_row_codes("L1", standards)
    assert codes[0] == expected_first
    assert set(codes) == {"BS-044", "BS-055"}


def test_pick_row_codes_skips_missing_variant():
    """某准则无该报表行时不产出空项（L2 soe 无「其中：应付利息」行）。"""
    assert L_CYCLE_SPECS["L2"].row_code_soe is None
    codes = pick_row_codes("L2", ["soe_standalone"])
    assert codes == ["BS-054"]


def test_pick_row_codes_empty_for_cycle_without_report_line():
    """L6 无报表行 → 返回空（走纯兜底路径）。"""
    assert pick_row_codes("L6", ["soe_standalone"]) == []


# ---------------------------------------------------------------------------
# spec 完整性
# ---------------------------------------------------------------------------


def test_all_eight_cycles_registered():
    assert sorted(L_CYCLE_SPECS) == ["L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8"]


@pytest.mark.parametrize("wp_code", sorted(L_CYCLE_SPECS))
def test_spec_has_source_ref(wp_code):
    """每条规格必须写明实证依据（供反查，防"按常识"改动）。"""
    spec = L_CYCLE_SPECS[wp_code]
    assert spec.source_ref.strip(), f"{wp_code} 缺 source_ref"
    assert spec.account_label.strip()


@pytest.mark.parametrize("wp_code", sorted(L_CYCLE_SPECS))
def test_buckets_have_source_ref(wp_code):
    """每个桶必须写明来源单元格/科目码。"""
    for bucket in L_CYCLE_SPECS[wp_code].buckets:
        assert bucket.source_ref.strip(), f"{wp_code}.{bucket.key} 缺 source_ref"
        assert bucket.keywords, f"{wp_code}.{bucket.key} 无命中词"


def test_only_l8_is_income_kind():
    """仅财务费用是损益类（取本期发生额），其余是余额类。"""
    income = {k for k, v in L_CYCLE_SPECS.items() if v.kind == "income"}
    assert income == {"L8"}
