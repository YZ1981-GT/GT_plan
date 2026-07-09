"""L7 其他非流动负债 — 注册契约测试 (Task 1.2).

验证 'l7-other-noncurrent-liabilities' componentType 在三个注册表中正确注册：
1. VALID_COMPONENT_TYPES（wp_classification_service.py）
2. wp_code_overrides（L7/L7-1~L7-4/L7A 共6个映射）
3. RENDERER_DISPATCH（后端渲染策略 + callable）

Spec: .kiro/specs/l7-other-noncurrent-liabilities/
Task: 1.2

**Validates: Requirements 1.6, 1.7, 1.8**
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.wp_classification_service import VALID_COMPONENT_TYPES

_JSON_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"

_COMPONENT_TYPE = "l7-other-noncurrent-liabilities"

_L7_WP_CODES = (
    "L7",
    "L7-1",
    "L7-2",
    "L7-3",
    "L7-4",
    "L7A",
)


def _load_overrides() -> dict[str, str]:
    with open(_JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_l7_component_type_registered():
    """l7-other-noncurrent-liabilities ∈ VALID_COMPONENT_TYPES."""
    assert _COMPONENT_TYPE in VALID_COMPONENT_TYPES


def test_l7_wp_code_overrides():
    """L7/L7-1~L7-4/L7A 共6个 wp_code 映射为 l7-other-noncurrent-liabilities."""
    overrides = _load_overrides()
    for code in _L7_WP_CODES:
        assert overrides.get(code) == _COMPONENT_TYPE, f"{code} 应映射为 {_COMPONENT_TYPE}"


def test_l7_wp_code_overrides_completeness():
    """覆盖完整性：恰好6个映射无遗漏无多余."""
    overrides = _load_overrides()
    l7_mappings = [k for k, v in overrides.items() if v == _COMPONENT_TYPE]
    assert len(l7_mappings) == len(_L7_WP_CODES)


def test_l7_renderer_dispatch_registered():
    """l7-other-noncurrent-liabilities 已注册于 RENDERER_DISPATCH 且 callable."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert _COMPONENT_TYPE in RENDERER_DISPATCH
    assert callable(RENDERER_DISPATCH[_COMPONENT_TYPE])
