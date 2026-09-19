"""N1 递延所得税资产 — 注册契约测试.

Spec: .kiro/specs/n1-deferred-tax-assets/ Task 1.2
Validates: Requirements 1.6, 1.7, 1.8

验证 n1-deferred-tax-assets componentType 在后端三个注册表中正确注册：
1. wp_code_overrides（N1/N1-1~N1-5/N1A 共7个映射）
2. VALID_COMPONENT_TYPES
3. RENDERER_DISPATCH
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.wp_classification_service import VALID_COMPONENT_TYPES

_COMPONENT = "n1-deferred-tax-assets"
_OVERRIDES_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"

# N1/N1-1~N1-5/N1A 共7个wp_code
_N1_WP_CODES = (
    "N1",
    "N1-1",
    "N1-2",
    "N1-3",
    "N1-4",
    "N1-5",
    "N1A",
)


def _load_overrides() -> dict[str, str]:
    with open(_OVERRIDES_PATH, encoding="utf-8") as f:
        return json.load(f)


# ─── VALID_COMPONENT_TYPES ───────────────────────────────────────────────────


def test_n1_in_valid_component_types():
    """n1-deferred-tax-assets 已注册于 VALID_COMPONENT_TYPES."""
    assert _COMPONENT in VALID_COMPONENT_TYPES


# ─── wp_code_overrides 映射 ──────────────────────────────────────────────────


@pytest.mark.parametrize("wp_code", _N1_WP_CODES)
def test_wp_code_override_mapping(wp_code: str):
    """wp_code_overrides: {wp_code} → n1-deferred-tax-assets."""
    data = _load_overrides()
    assert data.get(wp_code) == _COMPONENT, f"{wp_code} 应映射为 {_COMPONENT}"


def test_wp_code_overrides_completeness():
    """wp_code_overrides 中 n1-deferred-tax-assets 映射覆盖完整（共7个）."""
    data = _load_overrides()
    n1_mappings = [k for k, v in data.items() if v == _COMPONENT]
    assert sorted(n1_mappings) == sorted(_N1_WP_CODES)


# ─── RENDERER_DISPATCH ───────────────────────────────────────────────────────


def test_n1_registered_in_dispatch():
    """n1-deferred-tax-assets 已注册于 RENDERER_DISPATCH."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert _COMPONENT in RENDERER_DISPATCH
    assert callable(RENDERER_DISPATCH[_COMPONENT])
