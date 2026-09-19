"""L1 短期借款 — 注册契约测试.

Spec: .kiro/specs/l1-short-term-loans/ Task 1.2
Validates: Requirements 1.6, 1.7, 1.8

验证 l1-short-term-loans componentType 在后端三个注册表中正确注册：
1. wp_code_overrides（L1/L1-1~L1-9/L1A 共11个映射）
2. VALID_COMPONENT_TYPES
3. RENDERER_DISPATCH — TODO: Phase 5 完成后取消 skip
"""

import json
from pathlib import Path

import pytest

COMPONENT_TYPE = "l1-short-term-loans"

# L1/L1-1~L1-9/L1A 共11个wp_code
EXPECTED_WP_CODES = [
    "L1",
    "L1-1",
    "L1-2",
    "L1-3",
    "L1-4",
    "L1-5",
    "L1-6",
    "L1-7",
    "L1-8",
    "L1-9",
    "L1A",
]


def _load_overrides() -> dict:
    p = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"
    return json.loads(p.read_text(encoding="utf-8"))


# ─── wp_code_overrides 映射 ──────────────────────────────────────────────────


@pytest.mark.parametrize("wp_code", EXPECTED_WP_CODES)
def test_wp_code_override_mapping(wp_code: str):
    """wp_code_overrides: {wp_code} → l1-short-term-loans."""
    data = _load_overrides()
    assert data.get(wp_code) == COMPONENT_TYPE


def test_wp_code_overrides_completeness():
    """wp_code_overrides 中 l1-short-term-loans 映射覆盖完整（共11个）."""
    data = _load_overrides()
    l1_mappings = [k for k, v in data.items() if v == COMPONENT_TYPE]
    assert sorted(l1_mappings) == sorted(EXPECTED_WP_CODES)


# ─── VALID_COMPONENT_TYPES ───────────────────────────────────────────────────


def test_l1_in_valid_component_types():
    """l1-short-term-loans 已注册于 VALID_COMPONENT_TYPES."""
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert COMPONENT_TYPE in VALID_COMPONENT_TYPES


# ─── RENDERER_DISPATCH ───────────────────────────────────────────────────────


def test_l1_registered_in_dispatch():
    """l1-short-term-loans 已注册于 RENDERER_DISPATCH."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert COMPONENT_TYPE in RENDERER_DISPATCH


# ─── validate_overrides ──────────────────────────────────────────────────────


def test_validate_overrides_passes_for_l1():
    """validate_overrides 对 L1 映射及完整线上 overrides 均校验通过."""
    from app.services.wp_code_override_loader import validate_overrides

    # L1 映射单独校验通过
    single = {wp: COMPONENT_TYPE for wp in EXPECTED_WP_CODES}
    validate_overrides(single)

    # 完整线上 overrides 整体校验通过
    validate_overrides(_load_overrides())
