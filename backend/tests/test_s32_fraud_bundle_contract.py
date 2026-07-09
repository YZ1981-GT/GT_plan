"""S32 舞弊核查聚合组件 — 注册契约测试 (validate_overrides).

Spec: .kiro/specs/s32-fraud-response-bundle/ Task 2.3
Validates: Requirements 1.4

断言 S32 wp_code_overrides 映射 → s32-fraud-bundle，S32-1~S32-13 → skip，
componentType ∈ VALID_COMPONENT_TYPES，
且完整线上 overrides 经 validate_overrides 校验通过。
"""

import json
from pathlib import Path

S32_COMPONENT_TYPE = "s32-fraud-bundle"
S32_CHILD_CODES = [f"S32-{i}" for i in range(1, 14)]  # S32-1 ~ S32-13


def _load_overrides() -> dict:
    p = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"
    return json.loads(p.read_text(encoding="utf-8"))


# ─── wp_code_overrides 映射 ──────────────────────────────────────────────────


def test_s32_overrides_mapping():
    """S32 在 wp_code_overrides 中映射到 s32-fraud-bundle."""
    data = _load_overrides()
    assert data.get("S32") == S32_COMPONENT_TYPE


def test_s32_children_skip_mapping():
    """S32-1~S32-13 在 wp_code_overrides 中映射到 skip."""
    data = _load_overrides()
    for code in S32_CHILD_CODES:
        assert data.get(code) == "skip", f"{code} 应映射为 skip，实际为 {data.get(code)!r}"


# ─── VALID_COMPONENT_TYPES ───────────────────────────────────────────────────


def test_s32_fraud_bundle_in_valid_component_types():
    """s32-fraud-bundle 已注册于 VALID_COMPONENT_TYPES."""
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert S32_COMPONENT_TYPE in VALID_COMPONENT_TYPES


# ─── validate_overrides ──────────────────────────────────────────────────────


def test_validate_overrides_passes_for_s32():
    """validate_overrides 对 S32 映射及完整线上 overrides 均校验通过."""
    from app.services.wp_code_override_loader import validate_overrides

    # S32 bundle + 13 子底稿 skip 映射单独校验通过
    subset = {"S32": S32_COMPONENT_TYPE}
    subset.update({code: "skip" for code in S32_CHILD_CODES})
    validate_overrides(subset)

    # 完整线上 overrides 整体校验通过（含 S32 新映射）
    validate_overrides(_load_overrides())
