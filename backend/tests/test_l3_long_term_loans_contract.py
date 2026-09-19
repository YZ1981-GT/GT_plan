"""L3 长期借款 — 注册契约测试.

Spec: .kiro/specs/l3-long-term-loans/ Task 1.2
Validates: Requirements 1.6, 1.7, 1.8

验证 l3-long-term-loans componentType 在后端四个注册表中正确注册：
1. wp_code_overrides（L3/L3-1~L3-9/L3A 共11个映射）
2. VALID_COMPONENT_TYPES
3. RENDERER_DISPATCH
4. validate_overrides 校验通过
"""

import json
from pathlib import Path

import pytest

COMPONENT_TYPE = "l3-long-term-loans"

# L3/L3-1~L3-9/L3A 共11个wp_code
EXPECTED_WP_CODES = [
    "L3",
    "L3-1",
    "L3-2",
    "L3-3",
    "L3-4",
    "L3-5",
    "L3-6",
    "L3-7",
    "L3-8",
    "L3-9",
    "L3A",
]


def _load_overrides() -> dict:
    p = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"
    return json.loads(p.read_text(encoding="utf-8"))


# ─── wp_code_overrides 映射 ──────────────────────────────────────────────────


@pytest.mark.parametrize("wp_code", EXPECTED_WP_CODES)
def test_wp_code_override_mapping(wp_code: str):
    """wp_code_overrides: {wp_code} → l3-long-term-loans."""
    data = _load_overrides()
    assert data.get(wp_code) == COMPONENT_TYPE


def test_wp_code_overrides_completeness():
    """wp_code_overrides 中 l3-long-term-loans 映射覆盖完整（共11个）."""
    data = _load_overrides()
    l3_mappings = [k for k, v in data.items() if v == COMPONENT_TYPE]
    assert sorted(l3_mappings) == sorted(EXPECTED_WP_CODES)


# ─── VALID_COMPONENT_TYPES ───────────────────────────────────────────────────


def test_l3_in_valid_component_types():
    """l3-long-term-loans 已注册于 VALID_COMPONENT_TYPES."""
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert COMPONENT_TYPE in VALID_COMPONENT_TYPES


# ─── RENDERER_DISPATCH ───────────────────────────────────────────────────────


def test_l3_registered_in_dispatch():
    """l3-long-term-loans 已注册于 RENDERER_DISPATCH."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert COMPONENT_TYPE in RENDERER_DISPATCH
    assert callable(RENDERER_DISPATCH[COMPONENT_TYPE])


# ─── validate_overrides ──────────────────────────────────────────────────────


def test_validate_overrides_passes_for_l3():
    """validate_overrides 对 L3 映射及完整线上 overrides 均校验通过."""
    from app.services.wp_code_override_loader import validate_overrides

    # L3 映射单独校验通过
    single = {wp: COMPONENT_TYPE for wp in EXPECTED_WP_CODES}
    validate_overrides(single)

    # 完整线上 overrides 整体校验通过
    validate_overrides(_load_overrides())
