"""L6 专项应付款 — 注册契约测试 (Task 1.2).

验证 'l6-special-payables' componentType 在三个注册表中正确注册：
1. VALID_COMPONENT_TYPES（wp_classification_service.py）
2. wp_code_overrides（L6/L6-1~L6-4/L6A 共6个映射）
3. RENDERER_DISPATCH（后端渲染策略 + callable）

Spec: .kiro/specs/l6-special-payables/
Task: 1.2

**Validates: Requirements 1.6, 1.7, 1.8**
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.wp_classification_service import VALID_COMPONENT_TYPES

_JSON_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"

_COMPONENT_TYPE = "l6-special-payables"

# L6/L6-1~L6-4/L6A 共6个wp_code
_L6_WP_CODES = (
    "L6",
    "L6-1",
    "L6-2",
    "L6-3",
    "L6-4",
    "L6A",
)


def _load_overrides() -> dict[str, str]:
    with open(_JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_l6_component_type_registered():
    """l6-special-payables ∈ VALID_COMPONENT_TYPES."""
    assert _COMPONENT_TYPE in VALID_COMPONENT_TYPES


@pytest.mark.parametrize("wp_code", _L6_WP_CODES)
def test_l6_wp_code_override_mapping(wp_code: str):
    """wp_code_overrides: {wp_code} → l6-special-payables."""
    data = _load_overrides()
    assert data.get(wp_code) == _COMPONENT_TYPE, f"{wp_code} 应映射为 {_COMPONENT_TYPE}"


def test_l6_wp_code_overrides_completeness():
    """wp_code_overrides 中 l6-special-payables 映射覆盖完整（共6个）."""
    data = _load_overrides()
    l6_mappings = [k for k, v in data.items() if v == _COMPONENT_TYPE]
    assert len(l6_mappings) == len(_L6_WP_CODES), (
        f"期望 {len(_L6_WP_CODES)} 个映射，实际 {len(l6_mappings)} 个: {l6_mappings}"
    )


def test_l6_renderer_dispatch_registered():
    """l6-special-payables 已注册于 RENDERER_DISPATCH 且 callable."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert _COMPONENT_TYPE in RENDERER_DISPATCH
    assert callable(RENDERER_DISPATCH[_COMPONENT_TYPE])
