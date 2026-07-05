"""L2 应付利息 — 注册契约测试.

Spec: .kiro/specs/l2-interest-payable/ Task 1.2
Validates: Requirements 1.6, 1.7, 1.8

验证 l2-interest-payable componentType 在后端三个注册表中正确注册：
1. wp_code_overrides（L2/L2-1~L2-4/L2A 共6个映射）
2. VALID_COMPONENT_TYPES
3. RENDERER_DISPATCH
"""

import json
from pathlib import Path

import pytest

COMPONENT_TYPE = "l2-interest-payable"

# L2/L2-1~L2-4/L2A 共6个wp_code
EXPECTED_WP_CODES = [
    "L2",
    "L2-1",
    "L2-2",
    "L2-3",
    "L2-4",
    "L2A",
]


def _load_overrides() -> dict:
    p = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"
    return json.loads(p.read_text(encoding="utf-8"))


# ─── wp_code_overrides 映射 ──────────────────────────────────────────────────


@pytest.mark.parametrize("wp_code", EXPECTED_WP_CODES)
def test_wp_code_override_mapping(wp_code: str):
    """wp_code_overrides: {wp_code} → l2-interest-payable."""
    data = _load_overrides()
    assert data.get(wp_code) == COMPONENT_TYPE


def test_wp_code_overrides_completeness():
    """wp_code_overrides 中 l2-interest-payable 映射覆盖完整（共6个）."""
    data = _load_overrides()
    l2_mappings = [k for k, v in data.items() if v == COMPONENT_TYPE]
    assert sorted(l2_mappings) == sorted(EXPECTED_WP_CODES)


# ─── VALID_COMPONENT_TYPES ───────────────────────────────────────────────────


def test_l2_in_valid_component_types():
    """l2-interest-payable 已注册于 VALID_COMPONENT_TYPES."""
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert COMPONENT_TYPE in VALID_COMPONENT_TYPES


# ─── RENDERER_DISPATCH ───────────────────────────────────────────────────────


def test_l2_registered_in_dispatch():
    """l2-interest-payable 已注册于 RENDERER_DISPATCH."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert COMPONENT_TYPE in RENDERER_DISPATCH


# ─── validate_overrides ──────────────────────────────────────────────────────


def test_validate_overrides_passes_for_l2():
    """validate_overrides 对 L2 映射及完整线上 overrides 均校验通过."""
    from app.services.wp_code_override_loader import validate_overrides

    # L2 映射单独校验通过
    single = {wp: COMPONENT_TYPE for wp in EXPECTED_WP_CODES}
    validate_overrides(single)

    # 完整线上 overrides 整体校验通过
    validate_overrides(_load_overrides())
