"""I6 研发费用 — 注册契约测试.

Spec: .kiro/specs/i6-research-development-expense/ Task 1.2
Validates: Requirements 1.6, 1.7, 1.8

验证 i6-research-development-expense componentType 在后端三个注册表中正确注册：
1. wp_code_overrides（I6/I6-1~I6-8/I6A 共10个映射）
2. VALID_COMPONENT_TYPES
3. RENDERER_DISPATCH（task 5.1 实现后注册）
"""

import json
from pathlib import Path

import pytest

COMPONENT_TYPE = "i6-research-development-expense"

# I6/I6-1~I6-8/I6A 共10个wp_code
EXPECTED_WP_CODES = [
    "I6",
    "I6-1",
    "I6-2",
    "I6-3",
    "I6-4",
    "I6-5",
    "I6-6",
    "I6-7",
    "I6-8",
    "I6A",
]


def _load_overrides() -> dict:
    p = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"
    return json.loads(p.read_text(encoding="utf-8"))


# ─── wp_code_overrides 映射 ──────────────────────────────────────────────────


@pytest.mark.parametrize("wp_code", EXPECTED_WP_CODES)
def test_wp_code_override_mapping(wp_code: str):
    """wp_code_overrides: {wp_code} → i6-research-development-expense."""
    data = _load_overrides()
    assert data.get(wp_code) == COMPONENT_TYPE


def test_wp_code_overrides_completeness():
    """wp_code_overrides 中 i6-research-development-expense 映射覆盖完整（共10个）."""
    data = _load_overrides()
    i6_mappings = [k for k, v in data.items() if v == COMPONENT_TYPE]
    assert sorted(i6_mappings) == sorted(EXPECTED_WP_CODES)


def test_wp_code_overrides_count():
    """wp_code_overrides 中 i6-research-development-expense 映射数量正好10个."""
    data = _load_overrides()
    i6_mappings = [k for k, v in data.items() if v == COMPONENT_TYPE]
    assert len(i6_mappings) == 10


# ─── VALID_COMPONENT_TYPES ───────────────────────────────────────────────────


def test_i6_in_valid_component_types():
    """i6-research-development-expense 已注册于 VALID_COMPONENT_TYPES."""
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert COMPONENT_TYPE in VALID_COMPONENT_TYPES


# ─── RENDERER_DISPATCH ───────────────────────────────────────────────────────


def test_i6_registered_in_dispatch():
    """i6-research-development-expense 已注册于 RENDERER_DISPATCH（或 task 5.1 后注册）."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    # NOTE: RENDERER_DISPATCH 注册在 task 5.1 完成后才有
    # 此测试提前声明契约：一旦注册必须为 callable
    if COMPONENT_TYPE in RENDERER_DISPATCH:
        assert callable(RENDERER_DISPATCH[COMPONENT_TYPE])
    else:
        pytest.skip("i6-research-development-expense 尚未注册 RENDERER_DISPATCH（待 task 5.1）")


# ─── validate_overrides ──────────────────────────────────────────────────────


def test_validate_overrides_passes_for_i6():
    """validate_overrides 对 I6 映射及完整线上 overrides 均校验通过."""
    from app.services.wp_code_override_loader import validate_overrides

    # I6 映射单独校验通过
    single = {wp: COMPONENT_TYPE for wp in EXPECTED_WP_CODES}
    validate_overrides(single)

    # 完整线上 overrides 整体校验通过
    validate_overrides(_load_overrides())
