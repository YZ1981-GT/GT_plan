"""G5 长期应收款 — 注册契约测试."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.wp_classification_service import VALID_COMPONENT_TYPES

_COMPONENT = "g5-long-term-receivable"
_OVERRIDES_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"

_G5_WP_CODES = (
    "G5A",
    "G5",
    "G5-1",
    "G5-12",
    "G5-note-listed",
    "G5-note-soe",
    "G5-directory",
)


def _load_overrides() -> dict[str, str]:
    with open(_OVERRIDES_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_g5_in_valid_component_types():
    assert _COMPONENT in VALID_COMPONENT_TYPES


def test_g5_wp_code_overrides():
    overrides = _load_overrides()
    for code in _G5_WP_CODES:
        assert overrides.get(code) == _COMPONENT, f"{code} 应映射为 {_COMPONENT}"


def test_g5_renderer_dispatch():
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert _COMPONENT in RENDERER_DISPATCH
    assert callable(RENDERER_DISPATCH[_COMPONENT])


def test_g5_import_export_router_registered():
    from app.routers.wp_render_strategies._g5_long_term_receivable_import_export import (
        _G5_SPECS,
        router,
    )

    assert router is not None
    assert "G5-2" in _G5_SPECS
    assert "G5-10" not in _G5_SPECS  # 待 G4-10 完成后补齐


def test_g5_ai_sections():
    from app.routers.wp_render_strategies._g5_long_term_receivable_ai import _PROMPTS

    assert "adjudication-analysis" in _PROMPTS
    assert "stage-conclusion" not in _PROMPTS  # 待 G4-9 完成后补齐
