"""F1 预付账款 注册契约测试."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.wp_classification_service import VALID_COMPONENT_TYPES

_JSON_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"

F1_MAPPINGS = {
    "F1": "f1-prepayment",
    "F1-1": "f1-prepayment",
    "F1-2": "f1-prepayment",
    "F1-3": "f1-prepayment",
    "F1-4": "f1-prepayment",
    "F1-5": "f1-prepayment",
    "F1-6": "f1-prepayment",
    "F1-7": "f1-prepayment",
}


def _load_overrides() -> dict[str, str]:
    with open(_JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_f1_wp_codes_mapped_to_f1_prepayment():
    overrides = _load_overrides()
    for code, expected in F1_MAPPINGS.items():
        assert overrides.get(code) == expected, f"{code} 应映射为 {expected}"


def test_f1_prepayment_in_valid_component_types():
    assert "f1-prepayment" in VALID_COMPONENT_TYPES


def test_f1_renderer_dispatch_registered():
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert "f1-prepayment" in RENDERER_DISPATCH
