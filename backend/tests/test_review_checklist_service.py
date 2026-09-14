"""review_checklist_service 单元测试."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from app.services.review_checklist_service import (
    apply_auto_na,
    get_template_definition,
    invalidate_cache,
    resolve_template_key,
)

DEFS = Path(__file__).resolve().parents[1] / "data" / "a21_a25_review_definitions.json"


@pytest.fixture(autouse=True)
def _reset_cache():
    invalidate_cache()
    yield
    invalidate_cache()


def test_definitions_file_exists():
    assert DEFS.exists(), "run scripts/audit_a21_a25_xlsx.py --write-definitions first"


def test_a21_1_has_fifteen_plus_items():
    tpl = get_template_definition("A21-1")
    assert tpl is not None
    assert len(tpl["items"]) >= 15


def test_a24_1_variant_keys():
    assert resolve_template_key("A24-1", True, "financial") in ("A24-1:large_soe", "A24-1")
    key = resolve_template_key("A24-1", False, "financial")
    data = json.loads(DEFS.read_text(encoding="utf-8"))
    assert key in data["templates"]


def test_auto_na_component_auditor():
    tpl = get_template_definition("A21-1")
    assert tpl
    item = next(i for i in tpl["items"] if i.get("auto_na_condition") == "no_component_auditor")
    out = apply_auto_na(
        {"items": [item]},
        {"has_component_auditor": False, "has_it_audit": True, "is_large_soe": False, "audit_type": "financial"},
    )
    assert out["items"][0]["auto_na"] is True


@pytest.mark.asyncio
async def test_get_review_context_sqlite_skip():
    """无 DB 时仅测纯函数；集成测另补。"""
    ctx = {
        "has_component_auditor": True,
        "has_it_audit": False,
        "audit_type": "financial",
        "is_large_soe": False,
    }
    tpl = get_template_definition("A22-1")
    assert tpl and len(tpl["items"]) >= 10
    merged = apply_auto_na(tpl, ctx)
    assert len(merged["items"]) == len(tpl["items"])
