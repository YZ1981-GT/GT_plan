"""K1 其他应收款 — 注册契约测试 (Task 1.2).

Validates: Requirements 1.6, 1.7, 1.8
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.wp_classification_service import VALID_COMPONENT_TYPES

_JSON_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"

COMPONENT_TYPE = "k1-other-receivables"

K1_WP_CODES = (
    "K1",
    "K1-1",
    "K1-2",
    "K1-3",
    "K1-4",
    "K1-5",
    "K1-6",
    "K1-7",
    "K1-8",
    "K1-9",
    "K1-10",
    "K1-11",
    "K1-12",
    "K1A",
)


def _load_overrides() -> dict[str, str]:
    with open(_JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_k1_component_type_registered():
    """VALID_COMPONENT_TYPES 包含 k1-other-receivables."""
    assert COMPONENT_TYPE in VALID_COMPONENT_TYPES


def test_k1_fourteen_wp_code_overrides():
    """wp_code_overrides.json 映射 K1/K1-1~K1-12/K1A → k1-other-receivables (14条)."""
    overrides = _load_overrides()
    for code in K1_WP_CODES:
        assert overrides.get(code) == COMPONENT_TYPE, f"{code} 应映射为 {COMPONENT_TYPE}"


def test_k1_wp_code_override_count():
    """wp_code_overrides.json 中映射到 k1-other-receivables 的总数为14."""
    overrides = _load_overrides()
    actual_count = sum(1 for v in overrides.values() if v == COMPONENT_TYPE)
    assert actual_count == len(K1_WP_CODES), (
        f"期望 {len(K1_WP_CODES)} 条映射，实际 {actual_count}"
    )


@pytest.mark.xfail(reason="RENDERER_DISPATCH 将在 Task 5.1 注册")
def test_k1_renderer_dispatch_registered():
    """RENDERER_DISPATCH 包含 k1-other-receivables (Task 5.1 后通过)."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert COMPONENT_TYPE in RENDERER_DISPATCH
