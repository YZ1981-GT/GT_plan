"""M5 盈余公积 — 注册契约测试 (Task 1.2).

验证 'm5-surplus-reserve' componentType 在三个注册表中正确注册：
1. VALID_COMPONENT_TYPES（wp_classification_service.py）
2. wp_code_overrides（M5/M5-1~M5-5 共6个映射）
3. RENDERER_DISPATCH（后端渲染策略 + callable）

Spec: .kiro/specs/m5-surplus-reserve/
Task: 1.2

**Validates: Requirements 1.6, 1.7, 1.8**
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.wp_classification_service import VALID_COMPONENT_TYPES

_JSON_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"

_COMPONENT_TYPE = "m5-surplus-reserve"

_M5_WP_CODES = (
    "M5",
    "M5-1",
    "M5-2",
    "M5-3",
    "M5-4",
    "M5-5",
)


def _load_overrides() -> dict[str, str]:
    with open(_JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_m5_component_type_registered():
    """m5-surplus-reserve ∈ VALID_COMPONENT_TYPES."""
    assert _COMPONENT_TYPE in VALID_COMPONENT_TYPES


def test_m5_wp_code_overrides():
    """M5/M5-1~M5-5 共6个 wp_code 映射为 m5-surplus-reserve."""
    overrides = _load_overrides()
    for code in _M5_WP_CODES:
        assert overrides.get(code) == _COMPONENT_TYPE, f"{code} 应映射为 {_COMPONENT_TYPE}"


def test_m5_wp_code_overrides_completeness():
    """覆盖完整性：恰好6个映射无遗漏无多余."""
    overrides = _load_overrides()
    m5_mappings = [k for k, v in overrides.items() if v == _COMPONENT_TYPE]
    assert len(m5_mappings) == len(_M5_WP_CODES)


def test_m5_renderer_dispatch_registered():
    """m5-surplus-reserve 已注册于 RENDERER_DISPATCH 且 callable."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert _COMPONENT_TYPE in RENDERER_DISPATCH
    assert callable(RENDERER_DISPATCH[_COMPONENT_TYPE])
