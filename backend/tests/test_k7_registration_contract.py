"""K7 递延收益 — 注册契约测试 (Task 1.2).

Spec: .kiro/specs/k7-deferred-income/ Task 1.2
Validates: Requirements 1.6, 1.7, 1.8

断言 K7 wp_code_overrides 映射 → 'k7-deferred-income'（7条），
componentType ∈ VALID_COMPONENT_TYPES，
且完整线上 overrides 经 validate_overrides 校验通过。
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.wp_classification_service import VALID_COMPONENT_TYPES

_JSON_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"

COMPONENT_TYPE = "k7-deferred-income"

K7_WP_CODES = (
    "K7",
    "K7-1",
    "K7-2",
    "K7-3",
    "K7-4",
    "K7-5",
    "K7A",
)


def _load_overrides() -> dict[str, str]:
    with open(_JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_k7_component_type_registered():
    """VALID_COMPONENT_TYPES 包含 k7-deferred-income."""
    assert COMPONENT_TYPE in VALID_COMPONENT_TYPES


def test_k7_seven_wp_code_overrides():
    """wp_code_overrides.json 映射 K7/K7-1~K7-5/K7A → k7-deferred-income (7条)."""
    overrides = _load_overrides()
    for code in K7_WP_CODES:
        assert overrides.get(code) == COMPONENT_TYPE, f"{code} 应映射为 {COMPONENT_TYPE}"


def test_k7_wp_code_override_count():
    """wp_code_overrides.json 中映射到 k7-deferred-income 的总数为7."""
    overrides = _load_overrides()
    actual_count = sum(1 for v in overrides.values() if v == COMPONENT_TYPE)
    assert actual_count == len(K7_WP_CODES), (
        f"期望 {len(K7_WP_CODES)} 条映射，实际 {actual_count}"
    )


def test_k7_validate_overrides_passes():
    """validate_overrides 对 K7 映射及完整线上 overrides 均校验通过."""
    from app.services.wp_code_override_loader import validate_overrides

    # K7 映射单独校验通过
    validate_overrides({code: COMPONENT_TYPE for code in K7_WP_CODES})

    # 完整线上 overrides 整体校验通过
    validate_overrides(_load_overrides())
