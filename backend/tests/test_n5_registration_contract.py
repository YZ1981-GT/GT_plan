"""N5 所得税费用 — 注册契约测试 (Task 1.2).

验证 'n5-income-tax-expense' componentType 在三个注册表中正确注册：
1. VALID_COMPONENT_TYPES（wp_classification_service.py）
2. wp_code_overrides（N5/N5-1~N5-8/N5-6-1/N5-6-2/N5A 共12个映射）
3. RENDERER_DISPATCH（后端渲染策略 + callable）

Spec: .kiro/specs/n5-income-tax-expense/
Task: 1.2

**Validates: Requirements 1.6, 1.7, 1.8**
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.wp_classification_service import VALID_COMPONENT_TYPES

_JSON_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"

_COMPONENT_TYPE = "n5-income-tax-expense"

_N5_WP_CODES = (
    "N5",
    "N5-1",
    "N5-2",
    "N5-3",
    "N5-4",
    "N5-5",
    "N5-6",
    "N5-6-1",
    "N5-6-2",
    "N5-7",
    "N5-8",
    "N5A",
)


def _load_overrides() -> dict[str, str]:
    with open(_JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_n5_component_type_registered():
    """n5-income-tax-expense ∈ VALID_COMPONENT_TYPES."""
    assert _COMPONENT_TYPE in VALID_COMPONENT_TYPES


def test_n5_wp_code_overrides():
    """N5/N5-1~N5-8/N5-6-1/N5-6-2/N5A 共12个 wp_code 映射为 n5-income-tax-expense."""
    overrides = _load_overrides()
    for code in _N5_WP_CODES:
        assert overrides.get(code) == _COMPONENT_TYPE, f"{code} 应映射为 {_COMPONENT_TYPE}"


def test_n5_wp_code_overrides_completeness():
    """覆盖完整性：恰好12个映射无遗漏无多余."""
    overrides = _load_overrides()
    n5_mappings = [k for k, v in overrides.items() if v == _COMPONENT_TYPE]
    assert len(n5_mappings) == len(_N5_WP_CODES)


def test_n5_renderer_dispatch_registered():
    """n5-income-tax-expense 已注册于 RENDERER_DISPATCH 且 callable."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert _COMPONENT_TYPE in RENDERER_DISPATCH
    assert callable(RENDERER_DISPATCH[_COMPONENT_TYPE])
