"""S35 再融资审核聚合组件 — 注册契约测试 (validate_overrides).

Spec: .kiro/specs/s35-refinancing-bundle/ Task 2.3
Validates: Requirements 1.4

断言 S35 wp_code_overrides 映射 → s35-refinance-bundle，S35-1~S35-5 及子表编码 → skip，
componentType ∈ VALID_COMPONENT_TYPES，
且完整线上 overrides 经 validate_overrides 校验通过。
"""

import json
from pathlib import Path

S35_COMPONENT_TYPE = "s35-refinance-bundle"

# S35-1~S35-5 主底稿编码
S35_MAIN_CODES = [f"S35-{i}" for i in range(1, 6)]

# 子检查表编码（明细核查子表）
S35_SUB_CODES = [
    "S35-1-1",
    "S35-2-1",
    "S35-3-1",
]

# 所有应为 skip 的编码
S35_ALL_SKIP_CODES = S35_MAIN_CODES + S35_SUB_CODES


def _load_overrides() -> dict:
    p = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"
    return json.loads(p.read_text(encoding="utf-8"))


# ─── wp_code_overrides 映射 ──────────────────────────────────────────────────


def test_s35_overrides_mapping():
    """S35 在 wp_code_overrides 中映射到 s35-refinance-bundle."""
    data = _load_overrides()
    assert data.get("S35") == S35_COMPONENT_TYPE


def test_s35_children_skip_mapping():
    """S35-1~S35-5 及子表编码在 wp_code_overrides 中映射到 skip."""
    data = _load_overrides()
    for code in S35_ALL_SKIP_CODES:
        assert data.get(code) == "skip", f"{code} 应映射为 skip，实际为 {data.get(code)!r}"


# ─── VALID_COMPONENT_TYPES ───────────────────────────────────────────────────


def test_s35_refinance_bundle_in_valid_component_types():
    """s35-refinance-bundle 已注册于 VALID_COMPONENT_TYPES."""
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert S35_COMPONENT_TYPE in VALID_COMPONENT_TYPES


# ─── validate_overrides ──────────────────────────────────────────────────────


def test_validate_overrides_passes_for_s35():
    """validate_overrides 对 S35 映射及完整线上 overrides 均校验通过."""
    from app.services.wp_code_override_loader import validate_overrides

    # S35 bundle + 所有子底稿 skip 映射单独校验通过
    subset = {"S35": S35_COMPONENT_TYPE}
    subset.update({code: "skip" for code in S35_ALL_SKIP_CODES})
    validate_overrides(subset)

    # 完整线上 overrides 整体校验通过（含 S35 新映射）
    validate_overrides(_load_overrides())
