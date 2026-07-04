"""F2 计价减值组 — 注册契约测试."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.wp_classification_service import VALID_COMPONENT_TYPES

_JSON_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"

F2_VAL_WP_CODES = (
    "F2-33",
    "F2-34",
    "F2-35",
    "F2-38",
    "F2-39",
    "F2-40",
    "F2-41",
    "F2-42",
    "F2-43",
    "F2-44",
    "F2-47",
    "F2-48",
    "F2-49",
    "F2-52",
)


def _load_overrides() -> dict[str, str]:
    with open(_JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_f2_valuation_component_type_registered():
    assert "f2-inventory-valuation-impairment" in VALID_COMPONENT_TYPES


def test_f2_valuation_wp_code_overrides():
    overrides = _load_overrides()
    for code in F2_VAL_WP_CODES:
        assert overrides.get(code) == "f2-inventory-valuation-impairment", (
            f"{code} 应映射为 f2-inventory-valuation-impairment"
        )


def test_f2_valuation_renderer_dispatch():
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert "f2-inventory-valuation-impairment" in RENDERER_DISPATCH
