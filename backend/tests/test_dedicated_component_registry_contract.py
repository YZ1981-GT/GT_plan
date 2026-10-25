"""专属组件注册表契约：WHOLE / VALID / FE / DISPATCH 一致性。

规则：
1. WHOLE == DEDICATED_COMPONENT_TYPES（单一来源派生）
2. WHOLE ⊆ VALID ∩ FE
3. WHOLE − DISPATCH ⊆ WHITELIST ∪ CONFIRMATION
   （无后端 renderer 的整册类型必须在白名单或函证集合，避免被改写为 onlyoffice-sheet）
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND_ROOT))

from scripts.check.workpaper_component_manifest import (  # noqa: E402
    parse_registry_component_types,
)

from app.routers.wp_render_config import (
    _CONFIRMATION_COMPONENTS,
    _ONLYOFFICE_HTML_WHITELIST,
    _WHOLE_WP_MULTISHEET_DEDICATED,
)
from app.routers.wp_render_strategies import RENDERER_DISPATCH
from app.services.dedicated_component_types import DEDICATED_COMPONENT_TYPES
from app.services.wp_classification_service import VALID_COMPONENT_TYPES

def _parse_fe_component_types() -> set[str]:
    """🔴 2026-09-28 改：委托给唯一解析入口，不再手写 REGISTRY_LIST 切片。

    原实现取 `const REGISTRY_LIST` 到 `export const HTML_RENDERER_REGISTRY` 之间的
    切片再正则 componentType。注册表按渲染器家族拆到 `registry/entries/*.ts` 后，
    那段只剩 6 个 spread ⇒ 解析出 **0 条**，于是 `whole - fe_types` 报出 91 个
    「WHOLE 不在 FE registry」—— 看着像注册漂移，实为解析失败。
    仓库里同一份手抄副本共 4 处（本文件 + k10/k12/k13 契约），全部同时恒红。
    """
    return set(parse_registry_component_types())


@pytest.fixture(scope="module")
def fe_types() -> set[str]:
    return _parse_fe_component_types()


def test_whole_equals_dedicated_source():
    assert _WHOLE_WP_MULTISHEET_DEDICATED == set(DEDICATED_COMPONENT_TYPES)


def test_dedicated_count_stable():
    """防误删：当前整册专属为 90 项（含 A/B Bundle + C/H/I/J/K/L/M/N/S + G1/G5 + B22A/B22B-deficiency/B22B-control-matrix/B22C + B23 + B50）。"""
    # 91 = 90 + a5-1-cashflow-audit（A 循环 canary 整册路由）
    # spec: a-cycle-sync-foundation-and-first-canary
    assert len(DEDICATED_COMPONENT_TYPES) == 91


def test_fe_registry_parse_is_not_empty(fe_types: set[str]):
    """结构性零守卫：解析结果必须非空，且含跨家族锚点。

    没有这条，「解析出 0 条」会伪装成「91 个 componentType 全部缺失」——
    2026-09-28 实测就是这个形态（注册表拆分后手写切片解析器失效）。
    锚点跨 core / programs / specialized 三个分域文件，确保 spread 各族都解析到。
    """
    assert len(fe_types) >= 90, len(fe_types)
    for anchor in ("a1-dashboard", "b22a-control-matrix", "k8-selling-expenses"):
        assert anchor in fe_types, f"{anchor} 未解析到 —— 分域 spread 可能漏族"


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
