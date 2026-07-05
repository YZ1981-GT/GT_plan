"""C23/C24 会计分录测试 — 注册契约测试.

Spec: .kiro/specs/c23-c24-journal-entry-testing/ Task 2.3
Validates: Requirements 1.2, 1.3, 1.4

mirror 自 test_c22_itgc_bundle.py / test_c1_entity_control.py 模式：
断言 C23/C24 wp_code_overrides 映射 → 对应 componentType，
componentType ∈ VALID_COMPONENT_TYPES，已注册于 RENDERER_DISPATCH，
加入 _WHOLE_WP_MULTISHEET_DEDICATED（整册统一路由），
且完整线上 overrides 经 validate_overrides 校验通过。
"""

import json
from pathlib import Path

C23_COMPONENT_TYPE = "c23-journal-entry-control"
C24_COMPONENT_TYPE = "c24-journal-entry-detail"


def _load_overrides() -> dict:
    p = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"
    return json.loads(p.read_text(encoding="utf-8"))


# ─── C23 overrides 映射 ──────────────────────────────────────────────────────


def test_c23_overrides_mapping():
    """C23 在 wp_code_overrides 中映射到专属组件 c23-journal-entry-control."""
    data = _load_overrides()
    assert data.get("C23") == C23_COMPONENT_TYPE


def test_c24_overrides_mapping():
    """C24 在 wp_code_overrides 中映射到专属组件 c24-journal-entry-detail."""
    data = _load_overrides()
    assert data.get("C24") == C24_COMPONENT_TYPE


# ─── VALID_COMPONENT_TYPES ───────────────────────────────────────────────────


def test_c23_in_valid_component_types():
    """c23-journal-entry-control 已注册于 VALID_COMPONENT_TYPES."""
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert C23_COMPONENT_TYPE in VALID_COMPONENT_TYPES


def test_c24_in_valid_component_types():
    """c24-journal-entry-detail 已注册于 VALID_COMPONENT_TYPES."""
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert C24_COMPONENT_TYPE in VALID_COMPONENT_TYPES


# ─── RENDERER_DISPATCH ───────────────────────────────────────────────────────


def test_c23_registered_in_dispatch():
    """c23-journal-entry-control 已注册于 RENDERER_DISPATCH（整册专属渲染策略）."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert C23_COMPONENT_TYPE in RENDERER_DISPATCH


def test_c24_registered_in_dispatch():
    """c24-journal-entry-detail 已注册于 RENDERER_DISPATCH（整册专属渲染策略）."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert C24_COMPONENT_TYPE in RENDERER_DISPATCH


# ─── _WHOLE_WP_MULTISHEET_DEDICATED ─────────────────────────────────────────


def test_c23_in_whole_wp_multisheet_dedicated():
    """c23-journal-entry-control 已加入 _WHOLE_WP_MULTISHEET_DEDICATED（整册统一路由）."""
    from app.routers.wp_render_config import _WHOLE_WP_MULTISHEET_DEDICATED

    assert C23_COMPONENT_TYPE in _WHOLE_WP_MULTISHEET_DEDICATED


def test_c24_in_whole_wp_multisheet_dedicated():
    """c24-journal-entry-detail 已加入 _WHOLE_WP_MULTISHEET_DEDICATED（整册统一路由）."""
    from app.routers.wp_render_config import _WHOLE_WP_MULTISHEET_DEDICATED

    assert C24_COMPONENT_TYPE in _WHOLE_WP_MULTISHEET_DEDICATED


# ─── validate_overrides ──────────────────────────────────────────────────────


def test_validate_overrides_passes_for_c23_c24():
    """validate_overrides 对 C23/C24 映射及完整线上 overrides 均校验通过."""
    from app.services.wp_code_override_loader import validate_overrides

    # C23/C24 映射单独校验通过，不 raise
    validate_overrides(
        {
            "C23": C23_COMPONENT_TYPE,
            "C24": C24_COMPONENT_TYPE,
        }
    )

    # 完整线上 overrides 整体校验通过（含 C23/C24 新映射）
    validate_overrides(_load_overrides())
