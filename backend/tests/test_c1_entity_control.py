"""C1 企业层面控制测试 — 注册契约测试.

Spec: .kiro/specs/c1-entity-level-control/ Task 2.3
Validates: Requirement 1.3（含 1.2 / 1.4 注册契约）

mirror 自 test_a3_8_goodwill.py::test_registered_in_dispatch_and_valid_types 模式：
断言 C1 wp_code_overrides 映射 → c1-entity-level-control，
componentType ∈ VALID_COMPONENT_TYPES，且已注册于 RENDERER_DISPATCH。
"""

import json
from pathlib import Path

C1_COMPONENT_TYPE = "c1-entity-level-control"


def test_overrides_mapping():
    """C1 在 wp_code_overrides 中映射到专属组件 c1-entity-level-control."""
    p = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data.get("C1") == C1_COMPONENT_TYPE


def test_registered_in_dispatch_and_valid_types():
    """componentType 注册于 RENDERER_DISPATCH 与 VALID_COMPONENT_TYPES."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert C1_COMPONENT_TYPE in VALID_COMPONENT_TYPES
    assert C1_COMPONENT_TYPE in RENDERER_DISPATCH


def test_validate_overrides_passes_for_c1():
    """validate_overrides 对含 C1 映射的 overrides 校验通过（value ∈ VALID_COMPONENT_TYPES）."""
    from app.services.wp_code_override_loader import validate_overrides

    # C1 映射单独校验通过，不 raise
    validate_overrides({"C1": C1_COMPONENT_TYPE})

    # 完整线上 overrides 也整体校验通过
    p = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"
    full = json.loads(p.read_text(encoding="utf-8"))
    validate_overrides(full)
