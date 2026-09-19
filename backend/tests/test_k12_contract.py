"""K12 营业外收入 — 注册契约测试 (Task 1.2).

Spec: .kiro/specs/k12-non-operating-income/ Task 1.2
Validates: Requirements 1.6, 1.7, 1.8

验证 k12-non-operating-income componentType 在后端三个注册表中正确注册：
1. wp_code_overrides（K12/K12-1~K12-4/K12A 共6个映射）
2. VALID_COMPONENT_TYPES
3. DEDICATED_COMPONENT_TYPES (WHOLE)
4. htmlRendererRegistry（前端）
"""

from __future__ import annotations

import json
import re
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

COMPONENT_TYPE = "k12-non-operating-income"

K12_WP_CODES = (
    "K12",
    "K12-1",
    "K12-2",
    "K12-3",
    "K12-4",
    "K12A",
)


def _load_overrides() -> dict[str, str]:
    with open(_JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def _parse_fe_component_types() -> set[str]:
    """解析前端 htmlRendererRegistry.ts 中 REGISTRY_LIST 段的 componentType。"""
    text = _FE_REGISTRY.read_text(encoding="utf-8")
    start = text.find("const REGISTRY_LIST")
    end = text.find("export const HTML_RENDERER_REGISTRY")
    assert start >= 0 and end > start, "无法定位 REGISTRY_LIST"
    ct_re = re.compile(r"componentType:\s*'([a-z0-9-]+)'")
    return set(ct_re.findall(text[start:end]))


# ─── VALID_COMPONENT_TYPES ────────────────────────────────────────────────────


def test_k12_component_type_registered():
    """VALID_COMPONENT_TYPES 包含 k12-non-operating-income."""
    assert COMPONENT_TYPE in VALID_COMPONENT_TYPES


# ─── DEDICATED_COMPONENT_TYPES (WHOLE) ────────────────────────────────────────


def test_k12_in_dedicated_component_types():
    """DEDICATED_COMPONENT_TYPES (WHOLE) 包含 k12-non-operating-income."""
    assert COMPONENT_TYPE in DEDICATED_COMPONENT_TYPES


# ─── wp_code_overrides.json ───────────────────────────────────────────────────


@pytest.mark.parametrize("wp_code", K12_WP_CODES)
def test_k12_wp_code_override_mapping(wp_code: str):
    """wp_code_overrides.json: {wp_code} → k12-non-operating-income."""
    overrides = _load_overrides()
    assert overrides.get(wp_code) == COMPONENT_TYPE, f"{wp_code} 应映射为 {COMPONENT_TYPE}"


def test_k12_wp_code_override_count():
    """wp_code_overrides.json 中映射到 k12-non-operating-income 的总数为6."""
    overrides = _load_overrides()
    actual_count = sum(1 for v in overrides.values() if v == COMPONENT_TYPE)
    assert actual_count == len(K12_WP_CODES), (
        f"期望 {len(K12_WP_CODES)} 条映射，实际 {actual_count}"
    )


# ─── htmlRendererRegistry（前端）────────────────────────────────────────────────


def test_k12_in_fe_html_renderer_registry():
    """前端 htmlRendererRegistry.ts 包含 k12-non-operating-income。"""
    fe_types = _parse_fe_component_types()
    assert COMPONENT_TYPE in fe_types, (
        f"前端 htmlRendererRegistry 未注册 '{COMPONENT_TYPE}'"
    )


# ─── RENDERER_DISPATCH（后端 render 策略）──────────────────────────────────────


def test_k12_renderer_dispatch():
    """RENDERER_DISPATCH 包含 k12-non-operating-income（或 task 5.1 后注册）."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    # NOTE: RENDERER_DISPATCH 注册在 task 5.1 完成后才有
    # 此测试提前声明契约：一旦注册必须为 callable
    if COMPONENT_TYPE in RENDERER_DISPATCH:
        assert callable(RENDERER_DISPATCH[COMPONENT_TYPE])
    else:
        pytest.skip("k12-non-operating-income 尚未注册 RENDERER_DISPATCH（待 task 5.1）")


# ─── validate_overrides 整体通过 ──────────────────────────────────────────────


def test_validate_overrides_passes_for_k12():
    """validate_overrides 对 K12 映射及完整线上 overrides 均校验通过."""
    from app.services.wp_code_override_loader import validate_overrides

    # K12 映射单独校验通过
    single = {wp: COMPONENT_TYPE for wp in K12_WP_CODES}
    validate_overrides(single)

    # 完整线上 overrides 整体校验通过
    validate_overrides(_load_overrides())
