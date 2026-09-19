"""MatchingRulesService.recommend_company_subtype 单元测试。

覆盖 requirements §7：
  - 唯一匹配（high confidence）
  - 歧义（多候选，low confidence）
  - 无匹配 fallback（listed → type_a / non_listed → type_d）

Validates: Requirements 1.4, 7.2, 7.5, 7.7
"""

from app.services.matching_rules_service import (
    backfill_company_subtype,
    recommend_company_subtype,
    reload_rules,
)


def setup_function() -> None:
    # 确保使用磁盘上最新的 matching_rules.json
    reload_rules()


def test_unique_match_listed_returns_type_a() -> None:
    """上市公司唯一命中模板A。"""
    result = recommend_company_subtype(
        {
            "entity_type": "listed",
            "scenario": "listed",
            "template_type": "listed",
            "company_name": "某上市股份有限公司",
        }
    )
    assert result.subtype == "type_a"
    assert result.confidence == "high"
    assert result.candidates == ["type_a"]
    assert result.source == "rule"


def test_unique_match_bank_returns_type_b() -> None:
    """银行（关键词命中）唯一命中模板B。"""
    result = recommend_company_subtype(
        {
            "entity_type": "private",
            "scenario": "normal",
            "company_name": "某某村镇银行股份有限公司",
        }
    )
    # 银行关键词命中 B；村镇银行同属 B，候选去重后唯一
    assert result.subtype == "type_b"
    assert result.confidence == "high"
    assert result.candidates == ["type_b"]


def test_ambiguous_returns_multiple_candidates() -> None:
    """同时含「上市」与「银行」关键词 → 歧义，返回多候选。"""
    result = recommend_company_subtype(
        {
            "company_name": "某上市银行股份有限公司",
        }
    )
    assert result.confidence == "low"
    assert len(result.candidates) >= 2
    assert "type_a" in result.candidates
    assert "type_b" in result.candidates
    # subtype 取最高优先级候选
    assert result.subtype in result.candidates


def test_no_match_fallback_non_listed_returns_type_d() -> None:
    """无任何关键词/属性命中 + company_type=non_listed → fallback type_d。"""
    result = recommend_company_subtype(
        {
            "company_type": "non_listed",
            "company_name": "某普通制造企业",
        }
    )
    assert result.subtype == "type_d"
    assert result.source == "fallback"
    assert result.confidence == "low"


def test_no_match_fallback_listed_company_type_returns_type_a() -> None:
    """company_type=listed 但无关键词命中 → fallback type_a。"""
    result = recommend_company_subtype(
        {
            "company_type": "listed",
            "company_name": "保密企业",
        }
    )
    assert result.subtype == "type_a"
    assert result.source == "fallback"


def test_empty_attrs_defaults_to_type_d() -> None:
    """完全无信息 → 默认最保守 type_d。"""
    result = recommend_company_subtype({})
    assert result.subtype == "type_d"
    assert result.source == "default"
    assert result.confidence == "none"


def test_central_enterprise_keyword_returns_type_c() -> None:
    """中央企业集团 → 模板C（其他公众利益实体）。"""
    result = recommend_company_subtype(
        {
            "company_name": "某中央企业集团有限公司",
        }
    )
    assert result.subtype == "type_c"
    assert "type_c" in result.candidates


# ===================================================================
# 14.3 存量项目回填顺序（需求 1.7/1.8）
# ===================================================================


def test_backfill_user_value_takes_precedence() -> None:
    """① 用户已手动设置 → confirmed，不显示横幅（需求 1.8 用户优先）。"""
    result = backfill_company_subtype(
        {"company_type": "listed"},  # 规则/兜底会推 type_a
        existing_subtype="type_c",  # 但用户手动选了 type_c
    )
    assert result.subtype == "type_c"
    assert result.confirmed is True
    assert result.needs_confirmation is False
    assert result.source == "user"


def test_backfill_user_value_normalized() -> None:
    """用户值大小写/空格归一化后采用。"""
    result = backfill_company_subtype({}, existing_subtype="  TYPE_B  ")
    assert result.subtype == "type_b"
    assert result.confirmed is True


def test_backfill_invalid_user_value_falls_through_to_inference() -> None:
    """非法 existing_subtype → 落到推断（needs_confirmation）。"""
    result = backfill_company_subtype(
        {"company_type": "non_listed"}, existing_subtype="garbage"
    )
    assert result.subtype == "type_d"
    assert result.confirmed is False
    assert result.needs_confirmation is True


def test_backfill_rule_recommendation_needs_confirmation() -> None:
    """② matching_rules 命中（银行→type_b）→ 建议值，needs_confirmation=True。"""
    result = backfill_company_subtype(
        {"entity_type": "private", "company_name": "某商业银行股份有限公司"},
        existing_subtype=None,
    )
    assert result.subtype == "type_b"
    assert result.confirmed is False
    assert result.needs_confirmation is True
    assert result.source == "rule"


def test_backfill_fallback_listed_to_type_a() -> None:
    """③ 无规则命中 + company_type=listed → fallback type_a（建议值，需确认）。"""
    result = backfill_company_subtype(
        {"company_type": "listed"}, existing_subtype=None
    )
    assert result.subtype == "type_a"
    assert result.confirmed is False
    assert result.needs_confirmation is True
    assert result.source == "fallback"


def test_backfill_fallback_non_listed_to_type_d() -> None:
    """③ 无规则命中 + company_type=non_listed → fallback type_d。"""
    result = backfill_company_subtype(
        {"company_type": "non_listed"}, existing_subtype=None
    )
    assert result.subtype == "type_d"
    assert result.confirmed is False
    assert result.needs_confirmation is True
    assert result.source == "fallback"


def test_backfill_empty_defaults_to_type_d_needs_confirmation() -> None:
    """完全无信息 → default type_d，仍需用户确认。"""
    result = backfill_company_subtype({}, existing_subtype=None)
    assert result.subtype == "type_d"
    assert result.confirmed is False
    assert result.needs_confirmation is True
    assert result.source == "default"


def test_backfill_order_rule_over_fallback() -> None:
    """需求 7.7：规则推荐优先于 company_type fallback。"""
    # 同时给 company_type=non_listed（fallback→type_d）和银行关键词（rule→type_b）
    result = backfill_company_subtype(
        {"company_type": "non_listed", "company_name": "某证券股份有限公司"},
        existing_subtype=None,
    )
    assert result.subtype == "type_b"
    assert result.source == "rule"
