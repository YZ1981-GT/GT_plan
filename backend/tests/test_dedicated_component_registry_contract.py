"""专属组件注册表契约：WHOLE / VALID / FE / DISPATCH 一致性。

规则：
1. WHOLE == DEDICATED_COMPONENT_TYPES（单一来源派生）
2. WHOLE ⊆ VALID ∩ FE
3. WHOLE − DISPATCH ⊆ WHITELIST ∪ CONFIRMATION
   （无后端 renderer 的整册类型必须在白名单或函证集合，避免被改写为 onlyoffice-sheet）
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.routers.wp_render_config import (
    _CONFIRMATION_COMPONENTS,
    _ONLYOFFICE_HTML_WHITELIST,
    _WHOLE_WP_MULTISHEET_DEDICATED,
)
from app.routers.wp_render_strategies import RENDERER_DISPATCH
from app.services.dedicated_component_types import DEDICATED_COMPONENT_TYPES
from app.services.wp_classification_service import VALID_COMPONENT_TYPES

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FE_REGISTRY = (
    _REPO_ROOT
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "htmlRendererRegistry.ts"
)

_CT_RE = re.compile(r"componentType:\s*'([a-z0-9-]+)'")


def _parse_fe_component_types() -> set[str]:
    text = _FE_REGISTRY.read_text(encoding="utf-8")
    # 仅取 REGISTRY_LIST 段内的 componentType（避免 HtmlComponentType union 干扰）
    start = text.find("const REGISTRY_LIST")
    end = text.find("export const HTML_RENDERER_REGISTRY")
    assert start >= 0 and end > start, "无法定位 REGISTRY_LIST"
    return set(_CT_RE.findall(text[start:end]))


@pytest.fixture(scope="module")
def fe_types() -> set[str]:
    return _parse_fe_component_types()


def test_whole_equals_dedicated_source():
    assert _WHOLE_WP_MULTISHEET_DEDICATED == set(DEDICATED_COMPONENT_TYPES)


def test_dedicated_count_stable():
    """防误删：当前整册专属为 82 项（含 A/B Bundle + C/H/I/J/K/L/M/N/S）。"""
    assert len(DEDICATED_COMPONENT_TYPES) == 82


def test_whole_subset_of_valid_and_fe(fe_types: set[str]):
    whole = set(DEDICATED_COMPONENT_TYPES)
    missing_valid = sorted(whole - VALID_COMPONENT_TYPES)
    missing_fe = sorted(whole - fe_types)
    assert not missing_valid, f"WHOLE 不在 VALID: {missing_valid}"
    assert not missing_fe, f"WHOLE 不在 FE registry: {missing_fe}"


def test_whole_without_dispatch_covered_by_whitelist_or_confirmation():
    whole = set(DEDICATED_COMPONENT_TYPES)
    dispatch = set(RENDERER_DISPATCH)
    uncovered = sorted(
        (whole - dispatch)
        - _ONLYOFFICE_HTML_WHITELIST
        - _CONFIRMATION_COMPONENTS
    )
    assert not uncovered, (
        "WHOLE − DISPATCH 必须 ⊆ WHITELIST ∪ CONFIRMATION，否则会被改写为 onlyoffice-sheet:\n"
        f"{uncovered}"
    )


def test_dedicated_sorted_export_for_fe_expected():
    """可选：生成按字母序的 FE expected 列表（契约侧可 diff）。"""
    expected = sorted(DEDICATED_COMPONENT_TYPES)
    assert expected[0].startswith(("a1", "b", "c-", "c1-", "c2", "h", "i", "j", "k", "l", "m", "n", "s"))
    assert "b19-bundle" in expected
    assert "l1-short-term-loans" in expected
    assert "k8-selling-expenses" in expected
    assert "m6-retained-earnings" in expected
    assert "n4-taxes-and-surcharges" in expected
