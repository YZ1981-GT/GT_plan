"""review_sign API + A17 preset hints 单元测试."""

from __future__ import annotations

import pytest

from app.services.a21_a25_version_selector import _determine_applicability
from app.services.review_checklist_service import (
    apply_auto_na,
    get_template_definition,
    validate_review_conclusion,
    _REVIEW_PRESET_PREFIXES,
)


def test_a24_hints_not_applicable_for_c_class():
    hints = _determine_applicability("C1", "financial", False)
    a24 = next(r for r in hints if r["wp_code"].startswith("A24-1"))
    assert a24["applicable"] is False


def test_sign_conclusion_values():
    assert validate_review_conclusion("A21-1-sign", "pass")
    assert validate_review_conclusion("A21-1-sign", "reject")
    assert validate_review_conclusion("A21-1-chk-01", "NA")
    assert not validate_review_conclusion("A21-1-sign", "signed")


def test_review_preset_prefixes_covered():
    assert "A22" in _REVIEW_PRESET_PREFIXES
    assert "A23" in _REVIEW_PRESET_PREFIXES


def test_auto_na_still_works():
    tpl = get_template_definition("A21-1")
    item = next(i for i in tpl["items"] if i.get("auto_na_condition") == "no_component_auditor")
    out = apply_auto_na({"items": [item]}, {"has_component_auditor": False})
    assert out["items"][0]["auto_na"] is True
