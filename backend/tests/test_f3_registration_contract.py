"""F3 应付票据 — 注册契约测试 (Task 1.2)."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.wp_classification_service import VALID_COMPONENT_TYPES

_JSON_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"

F3_WP_CODES = (
    "F3A",
    "F3-1",
    "F3-2",
    "F3-3",
    "F3-4",
    "F3-5",
    "F3-6",
    "F3-7",
    "F3-note-listed",
    "F3-note-soe",
)


def _load_overrides() -> dict[str, str]:
    with open(_JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_f3_component_type_registered():
    assert "f3-notes-payable" in VALID_COMPONENT_TYPES


def test_f3_ten_wp_code_overrides():
    overrides = _load_overrides()
    for code in F3_WP_CODES:
        assert overrides.get(code) == "f3-notes-payable", f"{code} 应映射为 f3-notes-payable"


def test_f3_renderer_dispatch_registered():
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert "f3-notes-payable" in RENDERER_DISPATCH
