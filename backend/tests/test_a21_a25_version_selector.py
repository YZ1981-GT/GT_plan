"""a21_a25_version_selector 单元测试."""

from __future__ import annotations

from app.services.a21_a25_version_selector import (
    _determine_applicability,
    resolve_review_wp_code,
)


def test_a24_not_applicable_for_c_class():
    results = _determine_applicability("C1", "financial", False)
    a24 = [r for r in results if r["wp_code"].startswith("A24")]
    assert a24
    assert all(not r["applicable"] for r in a24)


def test_a21_1_applicable_for_b_class():
    results = _determine_applicability("B3", "financial", False)
    hit = next(r for r in results if r["wp_code"] == "A21-1")
    assert hit["applicable"] is True


def test_a21_2_na_for_financial_only():
    results = _determine_applicability("A1", "financial", False)
    hit = next(r for r in results if r["wp_code"] == "A21-2")
    assert hit["applicable"] is False


def test_resolve_review_wp_code_parent_to_sub():
    templates = _determine_applicability("A1", "financial", False)
    out = resolve_review_wp_code(templates, "A21")
    assert out["wp_code"] == "A21-1"
    assert out["applicable"] is True


def test_resolve_review_wp_code_a24_c_class_na():
    templates = _determine_applicability("C1", "financial", False)
    out = resolve_review_wp_code(templates, "A24")
    assert out["applicable"] is False


def test_validate_review_conclusion():
    from app.services.review_checklist_service import validate_review_conclusion

    assert validate_review_conclusion("A21-1-sign", "pass")
    assert validate_review_conclusion("A21-1-chk-01", "NA")
    assert not validate_review_conclusion("A21-1-sign", "signed")
