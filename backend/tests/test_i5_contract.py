"""I5 其他非流动资产 — 注册契约测试.

Spec: .kiro/specs/i5-other-noncurrent-assets/ Task 1.2
Validates: Requirements 1.6, 1.7, 1.8

验证 i5-other-noncurrent-assets componentType 在后端三个注册表中正确注册：
1. wp_code_overrides（I5/I5-1~I5-4/I5A 共6个映射）
2. VALID_COMPONENT_TYPES
3. RENDERER_DISPATCH（task 5.1 实现后注册）
"""

import json
from pathlib import Path

import pytest

COMPONENT_TYPE = "i5-other-noncurrent-assets"

# I5/I5-1~I5-4/I5A 共6个wp_code
EXPECTED_WP_CODES = [
    "I5",
    "I5-1",
    "I5-2",
    "I5-3",
    "I5-4",
    "I5A",
]


def _load_overrides() -> dict:
    p = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"
    return json.loads(p.read_text(encoding="utf-8"))


# ─── wp_code_overrides 映射 ──────────────────────────────────────────────────


@pytest.mark.parametrize("wp_code", EXPECTED_WP_CODES)
def test_wp_code_override_mapping(wp_code: str):
    """wp_code_overrides: {wp_code} → i5-other-noncurrent-assets."""
    data = _load_overrides()
    assert data.get(wp_code) == COMPONENT_TYPE


def test_wp_code_overrides_completeness():
    """wp_code_overrides 中 i5-other-noncurrent-assets 映射覆盖完整（共6个）."""
    data = _load_overrides()
    i5_mappings = [k for k, v in data.items() if v == COMPONENT_TYPE]
    assert sorted(i5_mappings) == sorted(EXPECTED_WP_CODES)


# ─── VALID_COMPONENT_TYPES ───────────────────────────────────────────────────


def test_i5_in_valid_component_types():
    """i5-other-noncurrent-assets 已注册于 VALID_COMPONENT_TYPES."""
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert COMPONENT_TYPE in VALID_COMPONENT_TYPES


# ─── RENDERER_DISPATCH ───────────────────────────────────────────────────────


def test_i5_registered_in_dispatch():
    """i5-other-noncurrent-assets 已注册于 RENDERER_DISPATCH（或 task 5.1 后注册）."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    # NOTE: RENDERER_DISPATCH 注册在 task 5.1 完成后才有
    # 此测试提前声明契约：一旦注册必须为 callable
    if COMPONENT_TYPE in RENDERER_DISPATCH:
        assert callable(RENDERER_DISPATCH[COMPONENT_TYPE])
    else:
        pytest.skip("i5-other-noncurrent-assets 尚未注册 RENDERER_DISPATCH（待 task 5.1）")


# ─── validate_overrides ──────────────────────────────────────────────────────


def test_validate_overrides_passes_for_i5():
    """validate_overrides 对 I5 映射及完整线上 overrides 均校验通过."""
    from app.services.wp_code_override_loader import validate_overrides

    # I5 映射单独校验通过
    single = {wp: COMPONENT_TYPE for wp in EXPECTED_WP_CODES}
    validate_overrides(single)

    # 完整线上 overrides 整体校验通过
    validate_overrides(_load_overrides())
