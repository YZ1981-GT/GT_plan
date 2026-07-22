# -*- coding: utf-8 -*-
"""B60 plan API / QC unit tests (no DB required for pure helpers)."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.services.b60_plan_service import (
    FLAG_DEFS,
    NON_PIE_COLLAPSE_SECTIONS,
    default_flags_from_project,
    is_pie_project,
    normalize_flags,
    simplification_for_project,
)


class _P:
    def __init__(self, **kw):
        self.audit_type = kw.get("audit_type", "financial")
        self.scenario = kw.get("scenario", "normal")
        self.template_type = kw.get("template_type", "soe")
        self.business_category = kw.get("business_category")


def test_normalize_flags_it_team_implies_needs_it():
    f = normalize_flags({"it_team_executes": True, "uses_expert": True})
    assert f["it_team_executes"] is True
    assert f["needs_it_audit"] is True
    assert f["uses_expert"] is True


def test_default_flags_listed_ipo_integrated():
    f = default_flags_from_project(_P(template_type="listed", scenario="ipo", audit_type="integrated"))
    assert f["listed_or_ipo"] is True
    assert f["integrated_audit"] is True
    assert f["needs_regulatory_filing"] is True
    assert f["soe_annual"] is False


def test_default_flags_soe():
    f = default_flags_from_project(_P(template_type="soe", scenario="normal", audit_type="financial"))
    assert f["soe_annual"] is True
    assert f["listed_or_ipo"] is False
    assert f["integrated_audit"] is False


def test_flag_defs_cover_platform_attachments():
    assert set(FLAG_DEFS) >= {
        "integrated_audit",
        "listed_or_ipo",
        "soe_annual",
        "needs_regulatory_filing",
        "needs_it_audit",
        "it_team_executes",
        "uses_expert",
    }


def test_non_pie_simplification():
    s = simplification_for_project(_P(template_type="soe"))
    assert s.is_pie is False
    assert len(s.collapse_sections) == len(NON_PIE_COLLAPSE_SECTIONS)
    assert "十五、计划更新" in " ".join(s.must_keep_sections) or any(
        "十五" in x for x in s.must_keep_sections
    )


def test_pie_simplification_listed():
    assert is_pie_project(_P(template_type="listed")) is True
    s = simplification_for_project(_P(template_type="listed"))
    assert s.is_pie is True
    assert s.collapse_sections == []


def test_pie_by_business_category_a():
    assert is_pie_project(_P(template_type="soe", business_category="A1")) is True


@pytest.mark.asyncio
async def test_bump_requires_confirm(monkeypatch):
    from app.services import b60_plan_service as svc

    async def _fake_get(*_a, **_k):
        raise AssertionError("should not reach project load before confirm")

    monkeypatch.setattr(svc, "_get_project", _fake_get)
    with pytest.raises(HTTPException) as ei:
        await svc.bump_plan_version(
            "00000000-0000-0000-0000-000000000001",
            None,  # type: ignore
            reason="test",
            confirm_major_change=False,
        )
    assert ei.value.status_code == 422
    assert ei.value.detail["error_code"] == "CONFIRM_MAJOR_CHANGE_REQUIRED"


@pytest.mark.asyncio
async def test_bump_requires_reason(monkeypatch):
    from app.services import b60_plan_service as svc

    async def _fake_get(*_a, **_k):
        raise AssertionError("should not reach")

    monkeypatch.setattr(svc, "_get_project", _fake_get)
    with pytest.raises(HTTPException) as ei:
        await svc.bump_plan_version(
            "00000000-0000-0000-0000-000000000001",
            None,  # type: ignore
            reason="  ",
            confirm_major_change=True,
        )
    assert ei.value.detail["error_code"] == "REASON_REQUIRED"


def test_gate_rules_b60_register_importable():
    from app.services.gate_engine import rule_registry
    from app.models.phase14_enums import GateType
    import app.services.gate_rules_b60  # noqa: F401

    codes = {r.rule_code for r in rule_registry.get_rules(GateType.submit_review)}
    assert "B60-ATTACH-MATRIX" in codes
    assert "B60-MATERIALITY-REF" in codes
    assert "B60D-VERSION-CONSISTENCY" in codes
