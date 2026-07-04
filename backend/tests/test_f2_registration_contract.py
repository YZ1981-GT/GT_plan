"""F2 存货核心组 — 注册契约测试 (Task 1.2)."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.wp_classification_service import VALID_COMPONENT_TYPES

_JSON_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"

F2_MAIN_WP_CODES = (
    "F2",
    "F2A",
    "F2-1",
    "F2-2",
    "F2-3",
    "F2-4",
    "F2-5",
    "F2-6",
    "F2-7",
    "F2-8",
    "F2-9",
    "F2-10",
    "F2-11",
    "F2-12",
    "F2-13",
    "F2-14",
    "F2-16",
    "F2-18",
    "F2-19",
    "F2-20",
    "F2-29",
    "F2-30",
    "F2-31",
    "F2-32",
    "F2-note-listed",
    "F2-note-soe",
)


def _load_overrides() -> dict[str, str]:
    with open(_JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_f2_main_component_type_registered():
    assert "f2-inventory-main" in VALID_COMPONENT_TYPES


def test_f2_main_wp_code_overrides():
    overrides = _load_overrides()
    for code in F2_MAIN_WP_CODES:
        assert overrides.get(code) == "f2-inventory-main", f"{code} 应映射为 f2-inventory-main"


def test_f2_renderer_dispatch_registered():
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert "f2-inventory-main" in RENDERER_DISPATCH
