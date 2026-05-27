"""单测：NoteColumnSemantics 列语义识别引擎.

Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 1 Task 1.2
Source: backend/app/services/note_column_semantics.py

覆盖：
- 25 个标准语义 ID 至少 1 个正例
- 边界：None / 空串 / 全角空格 / "（无单位）" 尾缀
- 优先级：父语义优先于子语义（current_year_increase > current_period_acquisition）
- 完全无意义字符串 → manual_text
- identify_headers 批量
- iter_synonyms / is_valid / VALID_SEMANTICS 长度
"""

from __future__ import annotations

import pytest

from backend.app.services.note_column_semantics import (
    DEFAULT_SEMANTIC,
    STANDARD_SEMANTICS,
    VALID_SEMANTICS,
    NoteColumnSemantics,
)


# ---------------------------------------------------------------------------
# 1) 25 个语义各 1 个正例（覆盖 R1.1 验收 2 ≥ 20 要求）
# ---------------------------------------------------------------------------

POSITIVE_CASES: list[tuple[str, str]] = [
    # 余额（含 "期末账面价值" 必须优先于 carrying_value）
    ("期末余额", "closing_balance"),
    ("期末账面价值", "closing_balance"),
    ("期初余额", "opening_balance"),
    ("期初账面价值", "opening_balance"),
    # 本期增减（变动表父列）
    ("本期增加", "current_year_increase"),
    ("本年增加", "current_year_increase"),
    ("本期减少", "current_year_decrease"),
    # 本期计提（应优先于 increase）
    ("本期计提", "current_year_provision"),
    ("本期计提坏账准备", "current_year_provision"),
    # 账龄 5 桶
    ("1年以内", "aging_bucket_within_1y"),
    ("一年以内", "aging_bucket_within_1y"),
    ("1-2年", "aging_bucket_1_2y"),
    ("2-3年", "aging_bucket_2_3y"),
    ("3-5年", "aging_bucket_3_5y"),
    ("5年以上", "aging_bucket_over_5y"),
    # 小计 / 计提比例
    ("小计", "category_subtotal"),
    ("计提比例", "provision_ratio"),
    # 行标识列 / 上年值
    ("项目", "manual_text"),
    ("上年金额", "prior_year_value"),
    # 原值 / 累计折旧 / 减值 / 账面价值
    ("账面原值", "original_value"),
    ("累计折旧", "accumulated_depreciation"),
    ("减值准备", "impairment_provision"),
    ("账面价值", "carrying_value"),
    # 具体动作（仅在父列未命中时）
    ("购置", "current_period_acquisition"),
    ("处置", "current_period_disposal"),
    ("核销", "current_period_writeoff"),
    ("收回", "current_period_recover"),
    # 存货 / 金融资产
    ("账面成本", "cost"),
    ("公允价值", "fair_value"),
]


@pytest.mark.parametrize("header,expected", POSITIVE_CASES)
def test_identify_positive_cases(header: str, expected: str) -> None:
    """每个标准语义至少 1 个正例都能识别."""
    assert NoteColumnSemantics.identify(header) == expected


# ---------------------------------------------------------------------------
# 2) 边界用例
# ---------------------------------------------------------------------------


def test_identify_empty_string_returns_manual_text() -> None:
    assert NoteColumnSemantics.identify("") == DEFAULT_SEMANTIC == "manual_text"


def test_identify_none_returns_manual_text() -> None:
    assert NoteColumnSemantics.identify(None) == "manual_text"


def test_identify_full_width_space_only_returns_manual_text() -> None:
    """全角空格 + 半角空格混合，归一化后为空 → 默认兜底."""
    assert NoteColumnSemantics.identify("\u3000  \u3000") == "manual_text"


def test_identify_full_width_space_inside_keyword() -> None:
    """全角空格切断关键词时仍能命中（"1 年以内" 等真实附注 header）."""
    assert NoteColumnSemantics.identify("1\u3000年以内") == "aging_bucket_within_1y"
    assert NoteColumnSemantics.identify("1 年 以 内") == "aging_bucket_within_1y"


def test_identify_with_unit_suffix() -> None:
    """致同附注实际 header 常带 '(无单位)' / '(元)' 尾缀，关键词在尾缀前应仍命中."""
    assert NoteColumnSemantics.identify("期末余额（无单位）") == "closing_balance"
    assert NoteColumnSemantics.identify("本期增加(元)") == "current_year_increase"


def test_identify_unknown_garbage_returns_manual_text() -> None:
    """完全无意义的字符串保守兜底."""
    assert NoteColumnSemantics.identify("foobarbaz123") == "manual_text"
    assert NoteColumnSemantics.identify("ＸＹＺ") == "manual_text"


def test_identify_formula_prefix_returns_formula_result() -> None:
    """以 '=' 起头视为公式列（合并表 / 交叉表）."""
    assert NoteColumnSemantics.identify("=SUM(B2:B5)") == "formula_result"
    assert NoteColumnSemantics.identify("=TB(\"货币资金\",\"期末\")") == "formula_result"


# ---------------------------------------------------------------------------
# 3) 优先级判定（父语义 > 子语义；具体短语 > 通用）
# ---------------------------------------------------------------------------


def test_priority_parent_over_child_increase() -> None:
    """变动表 '本期增加（购置）' 应优先父语义 current_year_increase，而非 acquisition."""
    assert (
        NoteColumnSemantics.identify("本期增加（购置）") == "current_year_increase"
    )


def test_priority_parent_over_child_decrease() -> None:
    """同理 '本期减少（核销）' 应命中 current_year_decrease."""
    assert (
        NoteColumnSemantics.identify("本期减少（核销）") == "current_year_decrease"
    )


def test_priority_provision_over_increase() -> None:
    """'本期计提坏账准备' 是 increase 的特化形式，应命中 current_year_provision."""
    assert (
        NoteColumnSemantics.identify("本期计提坏账准备") == "current_year_provision"
    )


def test_priority_closing_balance_over_carrying_value() -> None:
    """'期末账面价值' 不能掉到 carrying_value 兜底."""
    assert NoteColumnSemantics.identify("期末账面价值") == "closing_balance"


def test_priority_accumulated_depreciation_over_impairment() -> None:
    """'累计减值' 应命中 accumulated_depreciation 而非 impairment_provision."""
    assert (
        NoteColumnSemantics.identify("累计减值") == "accumulated_depreciation"
    )


def test_priority_provision_ratio_over_provision() -> None:
    """'坏账计提比例' 命中 provision_ratio 而非 current_year_provision."""
    assert (
        NoteColumnSemantics.identify("坏账计提比例") == "provision_ratio"
    )


# ---------------------------------------------------------------------------
# 4) 批量识别 identify_headers（SOE 真实附注 4 列 header）
# ---------------------------------------------------------------------------


def test_identify_headers_batch_typical_3col() -> None:
    """3 列标准表 header："项目 / 期末余额 / 期初余额"."""
    result = NoteColumnSemantics.identify_headers(
        ["项目", "期末余额", "期初余额"]
    )
    assert result == ["manual_text", "closing_balance", "opening_balance"]


def test_identify_headers_batch_aging_table() -> None:
    """账龄表 6 列："项目 / 1年以内 / 1-2年 / 2-3年 / 3-5年 / 5年以上"."""
    result = NoteColumnSemantics.identify_headers(
        ["项目", "1年以内", "1-2年", "2-3年", "3-5年", "5年以上"]
    )
    assert result == [
        "manual_text",
        "aging_bucket_within_1y",
        "aging_bucket_1_2y",
        "aging_bucket_2_3y",
        "aging_bucket_3_5y",
        "aging_bucket_over_5y",
    ]


def test_identify_headers_batch_movement_table() -> None:
    """变动表 5 列："项目 / 期初余额 / 本期增加 / 本期减少 / 期末余额"."""
    result = NoteColumnSemantics.identify_headers(
        ["项目", "期初余额", "本期增加", "本期减少", "期末余额"]
    )
    assert result == [
        "manual_text",
        "opening_balance",
        "current_year_increase",
        "current_year_decrease",
        "closing_balance",
    ]


def test_identify_headers_batch_with_garbage_and_empty() -> None:
    """边界：空 / None / 未识别字符串混合."""
    result = NoteColumnSemantics.identify_headers(
        ["项目", "", None, "不存在的列名", "期末余额"]
    )
    assert result == [
        "manual_text",
        "manual_text",
        "manual_text",
        "manual_text",
        "closing_balance",
    ]


def test_identify_headers_rejects_non_list() -> None:
    """传字符串而非 list，应抛 TypeError 而非静默错误."""
    with pytest.raises(TypeError, match="must be a list"):
        NoteColumnSemantics.identify_headers("项目")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 5) 模块常量与 schema 校验辅助
# ---------------------------------------------------------------------------


def test_valid_semantics_covers_at_least_20() -> None:
    """R1.1 验收 2：≥ 20 个标准语义."""
    assert len(VALID_SEMANTICS) >= 20, (
        f"expected >= 20 semantics, got {len(VALID_SEMANTICS)}: {VALID_SEMANTICS}"
    )


def test_valid_semantics_unique() -> None:
    """语义 ID 不能重复（dict key 已保证，但显式断言以防回归）."""
    assert len(set(VALID_SEMANTICS)) == len(VALID_SEMANTICS)


def test_valid_semantics_contains_required_core_ids() -> None:
    """R1.1 验收 2 明确点名的核心语义都必须在."""
    required = {
        "closing_balance",
        "opening_balance",
        "current_year_increase",
        "current_year_decrease",
        "current_year_provision",
        "aging_bucket_within_1y",
        "aging_bucket_1_2y",
        "aging_bucket_2_3y",
        "aging_bucket_3_5y",
        "aging_bucket_over_5y",
        "category_subtotal",
        "provision_ratio",
        "manual_text",
        "formula_result",
        "prior_year_value",
    }
    missing = required - set(VALID_SEMANTICS)
    assert not missing, f"required semantics missing: {missing}"


def test_default_semantic_is_valid() -> None:
    assert DEFAULT_SEMANTIC in VALID_SEMANTICS
    assert NoteColumnSemantics.is_valid(DEFAULT_SEMANTIC)


def test_is_valid_rejects_unknown() -> None:
    assert not NoteColumnSemantics.is_valid("not_a_real_semantic")
    assert not NoteColumnSemantics.is_valid(None)  # type: ignore[arg-type]
    assert not NoteColumnSemantics.is_valid(123)  # type: ignore[arg-type]


def test_iter_synonyms_yields_all_semantics() -> None:
    """iter_synonyms 应迭代所有语义且每条带非空关键词列表."""
    seen_ids: list[str] = []
    for sid, kws in NoteColumnSemantics.iter_synonyms():
        assert sid in VALID_SEMANTICS
        assert isinstance(kws, list)
        assert kws, f"semantic {sid} has empty keyword list"
        seen_ids.append(sid)
    assert sorted(seen_ids) == sorted(VALID_SEMANTICS)


def test_standard_semantics_alias_on_class() -> None:
    """NoteColumnSemantics.STANDARD_SEMANTICS 与模块常量是同一对象."""
    assert NoteColumnSemantics.STANDARD_SEMANTICS is STANDARD_SEMANTICS
    assert NoteColumnSemantics.VALID_SEMANTICS is VALID_SEMANTICS
