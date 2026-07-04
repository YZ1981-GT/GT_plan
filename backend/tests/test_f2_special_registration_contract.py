"""F2 特殊组 — 注册契约测试."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.wp_classification_service import VALID_COMPONENT_TYPES

_JSON_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"

F2_SPECIAL_WP_CODES = (
    "F2-55A",
    "F2-55",
    "F2-56",
    "F2-57",
    "F2-58",
    "F2-61A",
    "F2-61",
    "F2-62",
    "F2-63",
    "F2-64",
    "F2-65",
    "F2-66",
    "F2-67",
    "F2-68",
    "F2-69",
    "F2-70",
    "F2-71",
    "F2-72",
)


def _load_overrides() -> dict[str, str]:
    with open(_JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_f2_special_component_type_registered():
    assert "f2-inventory-special" in VALID_COMPONENT_TYPES


def test_f2_special_wp_code_overrides():
    overrides = _load_overrides()
    for code in F2_SPECIAL_WP_CODES:
        assert overrides.get(code) == "f2-inventory-special", (
            f"{code} 应映射为 f2-inventory-special"
        )


def test_f2_special_renderer_dispatch():
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert "f2-inventory-special" in RENDERER_DISPATCH
