"""K10 其他收益 — 注册契约测试 (Task 1.2).

Spec: .kiro/specs/k10-other-income/ Task 1.2
Validates: Requirements 1.6, 1.7, 1.8

验证 k10-other-income componentType 在后端三个注册表中正确注册：
1. wp_code_overrides（K10/K10-1~K10-6/K10A 共8个映射）
2. VALID_COMPONENT_TYPES
3. DEDICATED_COMPONENT_TYPES (WHOLE)
4. htmlRendererRegistry（前端）
5. RENDERER_DISPATCH（后端 render 策略）
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

from app.services.dedicated_component_types import DEDICATED_COMPONENT_TYPES
from app.services.wp_classification_service import VALID_COMPONENT_TYPES

_JSON_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"
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

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND_ROOT))

from scripts.check.workpaper_component_manifest import (  # noqa: E402
    parse_registry_component_types,
)

COMPONENT_TYPE = "k10-other-income"

K10_WP_CODES = (
    "K10",
    "K10-1",
    "K10-2",
    "K10-3",
    "K10-4",
    "K10-5",
    "K10-6",
    "K10A",
)


def _load_overrides() -> dict[str, str]:
    with open(_JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def _parse_fe_component_types() -> set[str]:
    """前端注册表登记的全部 componentType。

    🔴 2026-09-28 改：委托给唯一解析入口
    `scripts.check.workpaper_component_manifest.parse_registry_component_types`，
    不再手写「`const REGISTRY_LIST` 到 `export const HTML_RENDERER_REGISTRY` 的切片
    + 正则」。注册表按渲染器家族拆到 `registry/entries/*.ts` 后那段只剩 6 个 spread
    ⇒ 手写版解析出 **0 条**，本文件的注册契约因此恒红。
    同一份手抄副本全仓共 4 处（本文件 + k12/k13 + dedicated_component_registry_contract）。
    """
    return set(parse_registry_component_types())


# ─── VALID_COMPONENT_TYPES ────────────────────────────────────────────────────


def test_k10_component_type_registered():
    """VALID_COMPONENT_TYPES 包含 k10-other-income."""
    assert COMPONENT_TYPE in VALID_COMPONENT_TYPES


# ─── DEDICATED_COMPONENT_TYPES (WHOLE) ────────────────────────────────────────


def test_k10_in_dedicated_component_types():
    """DEDICATED_COMPONENT_TYPES (WHOLE) 包含 k10-other-income."""
    assert COMPONENT_TYPE in DEDICATED_COMPONENT_TYPES


# ─── wp_code_overrides.json ───────────────────────────────────────────────────


@pytest.mark.parametrize("wp_code", K10_WP_CODES)
def test_k10_wp_code_override_mapping(wp_code: str):
    """wp_code_overrides.json: {wp_code} → k10-other-income."""
    overrides = _load_overrides()
    assert overrides.get(wp_code) == COMPONENT_TYPE, f"{wp_code} 应映射为 {COMPONENT_TYPE}"


def test_k10_wp_code_override_count():
    """wp_code_overrides.json 中映射到 k10-other-income 的总数为8."""
    overrides = _load_overrides()
    actual_count = sum(1 for v in overrides.values() if v == COMPONENT_TYPE)
    assert actual_count == len(K10_WP_CODES), (
        f"期望 {len(K10_WP_CODES)} 条映射，实际 {actual_count}"
    )


# ─── htmlRendererRegistry（前端）────────────────────────────────────────────────


def test_k10_in_fe_html_renderer_registry():
    """前端 htmlRendererRegistry.ts 包含 k10-other-income。"""
    fe_types = _parse_fe_component_types()
    assert COMPONENT_TYPE in fe_types, (
        f"前端 htmlRendererRegistry 未注册 '{COMPONENT_TYPE}'"
    )


# ─── RENDERER_DISPATCH（后端 render 策略）──────────────────────────────────────


def test_k10_renderer_dispatch():
    """RENDERER_DISPATCH 包含 k10-other-income 且为 callable。"""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert COMPONENT_TYPE in RENDERER_DISPATCH, (
        f"RENDERER_DISPATCH 未注册 '{COMPONENT_TYPE}'"
    )
    assert callable(RENDERER_DISPATCH[COMPONENT_TYPE])


# ─── validate_overrides 整体通过 ──────────────────────────────────────────────


def test_validate_overrides_passes_for_k10():
    """validate_overrides 对 K10 映射及完整线上 overrides 均校验通过."""
    from app.services.wp_code_override_loader import validate_overrides

    # K10 映射单独校验通过
    single = {wp: COMPONENT_TYPE for wp in K10_WP_CODES}
    validate_overrides(single)

    # 完整线上 overrides 整体校验通过
    validate_overrides(_load_overrides())
