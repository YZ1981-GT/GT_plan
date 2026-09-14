"""K4 其他流动负债 — 注册契约测试 (Task 1.2).

Validates: Requirements 1.6, 1.7, 1.8
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.wp_classification_service import VALID_COMPONENT_TYPES

_JSON_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"

COMPONENT_TYPE = "k4-other-current-liabilities"

K4_WP_CODES = (
    "K4",
    "K4-1",
    "K4-2",
    "K4-3",
    "K4-4",
    "K4A",
)


def _load_overrides() -> dict[str, str]:
    with open(_JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_k4_component_type_registered():
    """VALID_COMPONENT_TYPES 包含 k4-other-current-liabilities."""
    assert COMPONENT_TYPE in VALID_COMPONENT_TYPES


def test_k4_six_wp_code_overrides():
    """wp_code_overrides.json 映射 K4/K4-1~K4-4/K4A → k4-other-current-liabilities (6条)."""
    overrides = _load_overrides()
    for code in K4_WP_CODES:
        assert overrides.get(code) == COMPONENT_TYPE, f"{code} 应映射为 {COMPONENT_TYPE}"


def test_k4_wp_code_override_count():
    """wp_code_overrides.json 中映射到 k4-other-current-liabilities 的总数为6."""
    overrides = _load_overrides()
    actual_count = sum(1 for v in overrides.values() if v == COMPONENT_TYPE)
    assert actual_count == len(K4_WP_CODES), (
        f"期望 {len(K4_WP_CODES)} 条映射，实际 {actual_count}"
    )


@pytest.mark.xfail(reason="RENDERER_DISPATCH 将在 Task 5.1 注册")
def test_k4_renderer_dispatch_registered():
    """RENDERER_DISPATCH 包含 k4-other-current-liabilities (Task 5.1 后通过)."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert COMPONENT_TYPE in RENDERER_DISPATCH
