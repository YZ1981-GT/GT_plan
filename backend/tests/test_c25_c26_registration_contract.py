"""C25/C26 内审利用 + 信息处理控制 — 注册契约测试.

Spec: .kiro/specs/c25-c26-internal-audit-info-control/ Task 2.3
Validates: Requirements 1.2, 1.3

mirror 自 test_c23_c24_journal_entry.py 模式：
断言 C25/C26 wp_code_overrides 映射 → 对应 componentType，
componentType ∈ VALID_COMPONENT_TYPES，已注册于 RENDERER_DISPATCH，
且完整线上 overrides 经 validate_overrides 校验通过。
"""

import json
from pathlib import Path

C25_COMPONENT_TYPE = "c25-internal-audit-reliance"
C26_COMPONENT_TYPE = "c26-info-processing-control"


def _load_overrides() -> dict:
    p = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"
    return json.loads(p.read_text(encoding="utf-8"))


# ─── C25 overrides 映射 ──────────────────────────────────────────────────────


def test_c25_overrides_mapping():
    """C25 在 wp_code_overrides 中映射到专属组件 c25-internal-audit-reliance."""
    data = _load_overrides()
    assert data.get("C25") == C25_COMPONENT_TYPE


def test_c26_overrides_mapping():
    """C26 在 wp_code_overrides 中映射到专属组件 c26-info-processing-control."""
    data = _load_overrides()
    assert data.get("C26") == C26_COMPONENT_TYPE


# ─── VALID_COMPONENT_TYPES ───────────────────────────────────────────────────


def test_c25_in_valid_component_types():
    """c25-internal-audit-reliance 已注册于 VALID_COMPONENT_TYPES."""
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert C25_COMPONENT_TYPE in VALID_COMPONENT_TYPES


def test_c26_in_valid_component_types():
    """c26-info-processing-control 已注册于 VALID_COMPONENT_TYPES."""
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert C26_COMPONENT_TYPE in VALID_COMPONENT_TYPES


# ─── RENDERER_DISPATCH ───────────────────────────────────────────────────────


def test_c25_registered_in_dispatch():
    """c25-internal-audit-reliance 已注册于 RENDERER_DISPATCH."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert C25_COMPONENT_TYPE in RENDERER_DISPATCH


def test_c26_registered_in_dispatch():
    """c26-info-processing-control 已注册于 RENDERER_DISPATCH."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert C26_COMPONENT_TYPE in RENDERER_DISPATCH


# ─── validate_overrides ──────────────────────────────────────────────────────


def test_validate_overrides_passes_for_c25_c26():
    """validate_overrides 对 C25/C26 映射及完整线上 overrides 均校验通过."""
    from app.services.wp_code_override_loader import validate_overrides

    # C25/C26 映射单独校验通过，不 raise
    validate_overrides(
        {
            "C25": C25_COMPONENT_TYPE,
            "C26": C26_COMPONENT_TYPE,
        }
    )

    # 完整线上 overrides 整体校验通过（含 C25/C26 新映射）
    validate_overrides(_load_overrides())
