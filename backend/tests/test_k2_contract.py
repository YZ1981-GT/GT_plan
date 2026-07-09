"""K2 其他流动资产 — 注册契约测试 (Task 1.2).

Spec: .kiro/specs/k2-other-current-assets/ Task 1.2
Validates: Requirements 1.6, 1.7, 1.8

验证 k2-other-current-assets componentType 在后端三个注册表中正确注册：
1. wp_code_overrides（K2/K2-1~K2-6/K2A 共8个映射）
2. VALID_COMPONENT_TYPES
3. RENDERER_DISPATCH（task 5.1 实现后注册）
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.wp_classification_service import VALID_COMPONENT_TYPES

_JSON_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"

COMPONENT_TYPE = "k2-other-current-assets"

K2_WP_CODES = (
    "K2",
    "K2-1",
    "K2-2",
    "K2-3",
    "K2-4",
    "K2-5",
    "K2-6",
    "K2A",
)


def _load_overrides() -> dict[str, str]:
    with open(_JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_k2_component_type_registered():
    """VALID_COMPONENT_TYPES 包含 k2-other-current-assets."""
    assert COMPONENT_TYPE in VALID_COMPONENT_TYPES


@pytest.mark.parametrize("wp_code", K2_WP_CODES)
def test_k2_wp_code_override_mapping(wp_code: str):
    """wp_code_overrides.json: {wp_code} → k2-other-current-assets."""
    overrides = _load_overrides()
    assert overrides.get(wp_code) == COMPONENT_TYPE, f"{wp_code} 应映射为 {COMPONENT_TYPE}"


def test_k2_wp_code_override_count():
    """wp_code_overrides.json 中映射到 k2-other-current-assets 的总数为8."""
    overrides = _load_overrides()
    actual_count = sum(1 for v in overrides.values() if v == COMPONENT_TYPE)
    assert actual_count == len(K2_WP_CODES), (
        f"期望 {len(K2_WP_CODES)} 条映射，实际 {actual_count}"
    )


def test_k2_renderer_dispatch():
    """RENDERER_DISPATCH 包含 k2-other-current-assets（或 task 5.1 后注册）."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    # NOTE: RENDERER_DISPATCH 注册在 task 5.1 完成后才有
    # 此测试提前声明契约：一旦注册必须为 callable
    if COMPONENT_TYPE in RENDERER_DISPATCH:
        assert callable(RENDERER_DISPATCH[COMPONENT_TYPE])
    else:
        pytest.skip("k2-other-current-assets 尚未注册 RENDERER_DISPATCH（待 task 5.1）")


def test_validate_overrides_passes_for_k2():
    """validate_overrides 对 K2 映射及完整线上 overrides 均校验通过."""
    from app.services.wp_code_override_loader import validate_overrides

    # K2 映射单独校验通过
    single = {wp: COMPONENT_TYPE for wp in K2_WP_CODES}
    validate_overrides(single)

    # 完整线上 overrides 整体校验通过
    validate_overrides(_load_overrides())
