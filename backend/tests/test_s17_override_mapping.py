"""S17 模板 sheet 到专属前端组件的精确 override 契约。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


_OVERRIDES_PATH = (
    Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"
)
_EXPECTED_S17_OVERRIDES = {
    "S17-1": "s17-nonrecurring-detail",
    "S17-2": "s17-nonrecurring-detail",
    "S17-3": "s17-nonrecurring-detail",
    "S17-11": "s17-reconciliation",
    "S17-21": "s17-tax-impact",
}


def _load_overrides() -> dict[str, str]:
    return json.loads(_OVERRIDES_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("wp_code", "component_type"),
    tuple(_EXPECTED_S17_OVERRIDES.items()),
)
def test_s17_overrides_match_template_component_mapping(
    wp_code: str, component_type: str
) -> None:
    """五个 S17 模板 sheet 必须精确路由到对应的专属组件。"""
    overrides = _load_overrides()
    assert overrides.get(wp_code) == component_type


def test_s17_reconciliation_and_tax_impact_are_not_program_console() -> None:
    """S17-11/S17-21 不得退回通用程序表组件。"""
    overrides = _load_overrides()
    assert overrides["S17-11"] != "a-program-console"
    assert overrides["S17-21"] != "a-program-console"
