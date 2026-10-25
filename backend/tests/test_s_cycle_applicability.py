"""D2.3 backend contract: mapping, generation and render-config share rules."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.routers.wp_render_config import _render_applicability
from app.services.wp_classification_service import _WP_APPLICABLE_WHEN
from app.services.wp_generation_matching import (
    applicable_when_hit,
    business_category_flags,
    match_workpapers,
)

_MAPPING = json.loads(
    (Path(__file__).resolve().parents[1] / "data" / "wp_account_mapping.json").read_text(
        encoding="utf-8"
    )
)["mappings"]


@pytest.mark.parametrize(
    ("wp_code", "business_category", "template_type", "expected"),
    [
        ("S32", "IPO", "soe", True),
        ("S32", "C", "soe", False),
        ("S32", None, "soe", False),
        ("S32", None, "listed", True),
        ("S35", "C", "soe", False),
    ],
)
def test_render_applicability_uses_shared_flags_and_predicate(
    wp_code: str,
    business_category: str | None,
    template_type: str | None,
    expected: bool,
) -> None:
    """**Validates: Requirements 1.4, 1.5**"""
    applicable_when, not_applicable = _render_applicability(
        wp_code, business_category, template_type
    )

    assert applicable_when == _WP_APPLICABLE_WHEN[wp_code]
    assert not_applicable is (not expected)


def test_bundle_parent_applicability_is_aggregated_from_mapping_children() -> None:
    """父码声明来自 mapping 子码业务分类并集，而非 override 文件。"""
    assert _WP_APPLICABLE_WHEN["S32"] == {
        "business_category": ["ipo", "listed", "neeq"]
    }
    assert _WP_APPLICABLE_WHEN["S33"] == {
        "business_category": ["ipo", "listed", "neeq"]
    }
    assert _WP_APPLICABLE_WHEN["S34"] == {
        "business_category": ["ipo", "listed", "neeq", "refinancing"]
    }
    assert _WP_APPLICABLE_WHEN["S35"] == {
        "business_category": ["refinancing"]
    }


def test_refinancing_is_limited_to_pure_predicate_before_storage_decision() -> None:
    """String(10) 决策未批准前，只验证 flag/predicate，不宣称 PG/render 通过。"""
    flags = business_category_flags(" refinancing ", "soe")

    assert flags == {
        "biz_ipo": False,
        "biz_listed": False,
        "biz_neeq": False,
        "biz_refinancing": True,
    }
    assert applicable_when_hit(
        _WP_APPLICABLE_WHEN["S35"],
        flags,
        key_filter={"business_category"},
    ) is True


def test_render_config_does_not_hide_unknown_industry_declaration(monkeypatch) -> None:
    """缺少 Project.industry 时，行业限制不能被误判为不适用。"""
    monkeypatch.setitem(
        _WP_APPLICABLE_WHEN,
        "TEST-INDUSTRY-ONLY",
        {"industry": ["banking"]},
    )

    applicable_when, not_applicable = _render_applicability(
        "TEST-INDUSTRY-ONLY", "C", "soe"
    )

    assert applicable_when == {"industry": ["banking"]}
    assert not_applicable is False


@pytest.mark.parametrize(
    ("business_category", "template_type", "expected_codes"),
    [
        ("IPO", "soe", {"S32", "S33", "S34"}),
        ("C", "soe", set()),
        (None, "soe", set()),
        (None, "listed", {"S32", "S33", "S34"}),
    ],
)
def test_generation_chain_matching_uses_real_mapping_and_shared_flags(
    business_category: str | None,
    template_type: str | None,
    expected_codes: set[str],
) -> None:
    """**Validates: Requirements 1.4**"""
    matched, _ = match_workpapers(
        _MAPPING,
        set(),
        business_category_flags(business_category, template_type),
    )

    assert {"S32", "S33", "S34", "S35"}.intersection(matched) == expected_codes
