"""G14 信用减值损失 — 注册契约测试 (tasks 1.2)."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.wp_classification_service import VALID_COMPONENT_TYPES

_COMPONENT = "g14-credit-impairment-loss"
_OVERRIDES_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"

# tasks 1.1：至少这些短码应映射到 G14 组件（bundle 内多 sheet 共用）
_G14_WP_CODES = ("G14", "G14-1", "G14-2", "G14-3")


def _load_overrides() -> dict[str, str]:
    with open(_OVERRIDES_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_g14_in_valid_component_types():
    assert _COMPONENT in VALID_COMPONENT_TYPES


def test_g14_wp_code_overrides():
    overrides = _load_overrides()
    for code in _G14_WP_CODES:
        assert overrides.get(code) == _COMPONENT, f"{code} 应映射为 {_COMPONENT}"


def test_g14_renderer_dispatch():
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert _COMPONENT in RENDERER_DISPATCH
    assert callable(RENDERER_DISPATCH[_COMPONENT])
