# -*- coding: utf-8 -*-
"""B60 P3 platform fields / conditional mapping smoke tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def _load_json(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def test_b60_attachments_have_conditional_triggers():
    mappings = {m["wp_code"]: m for m in _load_json("wp_account_mapping.json")["mappings"]}
    assert mappings["B60"]["trigger"] == "must_have"
    assert mappings["B60-1"]["trigger"] == "must_have"
    expected = {
        "B60A": "integrated_audit",
        "B60B": "listed_or_ipo",
        "B60C": "soe_annual",
        "B60D": "needs_regulatory_filing",
        "B60-2-1": "needs_it_audit",
        "B60-2-2": "it_team_executes",
        "B60-2-3": "it_team_executes",
        "B60-3": "uses_expert",
    }
    for code, flag in expected.items():
        m = mappings[code]
        assert m.get("trigger") == "conditional", code
        assert m.get("applies_when") == flag, code


def test_b60_platform_fields_contract():
    pf = _load_json("wp_platform_fields/B60.json")
    assert pf["wp_code"] == "B60"
    assert "integrated_audit" in pf["attachment_flags"]
    assert "B60" in pf["always_generate"] and "B60-1" in pf["always_generate"]
    assert "CW-417" in pf["cross_refs"]
    assert pf["audit_plan_bindings"]["plan_version"].startswith("AuditPlan.plan_version")


def test_b60_cross_refs_p3_present():
    refs = {r["ref_id"]: r for r in _load_json("cross_wp_references.json")["references"]}
    for rid in ("CW-417", "CW-418", "CW-419", "CW-420", "CW-421", "CW-422"):
        assert rid in refs, rid
    # CW-96 no longer points at hours sheet
    t0 = refs["CW-96"]["targets"][0]
    assert "工时" not in t0.get("sheet", "")
    assert t0.get("wp_code") == "B60"
    assert "总体审计策略" in t0.get("sheet", "")


def test_b60_system_map_includes_strategy_group():
    sm = _load_json("wp_system_map.json")
    prepare = next(s for s in sm["stages"] if s["id"] == "prepare")
    groups = {g["id"]: g for g in prepare["groups"]}
    assert "B60_strategy" in groups
    assert "B60" in groups["B60_strategy"]["codes"]
    assert "B60A" in groups["B60_strategy"]["codes"]
    assert groups["B60_budget"]["codes"] == ["B60-1"]


def test_b60_attachment_flag_resolution_logic():
    """Mirror chain_orchestrator flag defaults (pure function smoke)."""

    def resolve(template_type, scenario, audit_type, wizard=None):
        audit_type_l = str(audit_type or "").lower()
        integrated = (
            "integrated" in audit_type_l
            or "内控" in str(audit_type or "")
            or "icfr" in audit_type_l
        )
        listed_or_ipo = template_type == "listed" or scenario in ("ipo", "listed")
        flags = {
            "integrated_audit": integrated,
            "listed_or_ipo": listed_or_ipo,
            "soe_annual": template_type == "soe",
            "needs_regulatory_filing": listed_or_ipo,
            "needs_it_audit": False,
            "it_team_executes": False,
            "uses_expert": False,
        }
        wizard = wizard or {}
        b60 = wizard.get("b60_attachment_flags") or {}
        for k, v in b60.items():
            if isinstance(v, bool):
                flags[k] = v
        if flags.get("it_team_executes"):
            flags["needs_it_audit"] = True
        return flags

    f = resolve("soe", "normal", "financial")
    assert f["soe_annual"] is True
    assert f["integrated_audit"] is False
    assert f["listed_or_ipo"] is False

    f = resolve("listed", "ipo", "integrated")
    assert f["listed_or_ipo"] is True
    assert f["integrated_audit"] is True
    assert f["needs_regulatory_filing"] is True

    f = resolve(
        "soe",
        "normal",
        "financial",
        {"b60_attachment_flags": {"it_team_executes": True, "uses_expert": True}},
    )
    assert f["it_team_executes"] is True
    assert f["needs_it_audit"] is True
    assert f["uses_expert"] is True
