"""K5 预计负债 — 注册契约测试 (Task 1.2).

Spec: .kiro/specs/k5-provisions/ Task 1.2
Validates: Requirements 1.6, 1.7, 1.8

断言 K5 wp_code_overrides 映射 → 'k5-provisions'（9条），
componentType ∈ VALID_COMPONENT_TYPES，
且完整线上 overrides 经 validate_overrides 校验通过。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.wp_classification_service import VALID_COMPONENT_TYPES

_JSON_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"

COMPONENT_TYPE = "k5-provisions"

K5_WP_CODES = (
    "K5",
    "K5-1",
    "K5-2",
    "K5-3",
    "K5-4",
    "K5-5",
    "K5-6",
    "K5-7",
    "K5A",
)


def _load_overrides() -> dict[str, str]:
    with open(_JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_k5_component_type_registered():
    """VALID_COMPONENT_TYPES 包含 k5-provisions."""
    assert COMPONENT_TYPE in VALID_COMPONENT_TYPES


def test_k5_nine_wp_code_overrides():
    """wp_code_overrides.json 映射 K5/K5-1~K5-7/K5A → k5-provisions (9条)."""
    overrides = _load_overrides()
    for code in K5_WP_CODES:
        assert overrides.get(code) == COMPONENT_TYPE, f"{code} 应映射为 {COMPONENT_TYPE}"


def test_k5_wp_code_override_count():
    """wp_code_overrides.json 中映射到 k5-provisions 的总数为9."""
    overrides = _load_overrides()
    actual_count = sum(1 for v in overrides.values() if v == COMPONENT_TYPE)
    assert actual_count == len(K5_WP_CODES), (
        f"期望 {len(K5_WP_CODES)} 条映射，实际 {actual_count}"
    )


def test_k5_validate_overrides_passes():
    """validate_overrides 对 K5 映射及完整线上 overrides 均校验通过."""
    from app.services.wp_code_override_loader import validate_overrides

    # K5 映射单独校验通过
    validate_overrides({code: COMPONENT_TYPE for code in K5_WP_CODES})

    # 完整线上 overrides 整体校验通过
    validate_overrides(_load_overrides())


def test_k5_renderer_dispatch_registered():
    """RENDERER_DISPATCH 包含 k5-provisions."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert COMPONENT_TYPE in RENDERER_DISPATCH
