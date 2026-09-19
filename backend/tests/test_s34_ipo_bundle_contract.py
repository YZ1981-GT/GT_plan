"""S34 首发审核（IPO）聚合组件 — 注册契约测试 (validate_overrides).

Spec: .kiro/specs/s34-ipo-review-bundle/ Task 2.3
Validates: Requirements 1.5

断言 S34 wp_code_overrides 映射 → s34-ipo-bundle，S34-0~S34-41 及子表编码 → skip，
componentType ∈ VALID_COMPONENT_TYPES，
且完整线上 overrides 经 validate_overrides 校验通过。
"""

import json
from pathlib import Path

S34_COMPONENT_TYPE = "s34-ipo-bundle"

# S34-0~S34-41 主底稿编码
S34_MAIN_CODES = [f"S34-{i}" for i in range(0, 42)]

# 子检查表编码（带公式子表）
S34_SUB_CODES = [
    "S34-2-1", "S34-2-2",
    "S34-3-1",
    "S34-4-1",
    "S34-8-1", "S34-8-2",
    "S34-9-1",
    "S34-11-1",
    "S34-16-1", "S34-16-2",
    "S34-18-1",
    "S34-20-1",
    "S34-25-1", "S34-25-2", "S34-25-3",
    "S34-30-1",
    "S34-34-1", "S34-34-2",
]

# 所有应为 skip 的编码
S34_ALL_SKIP_CODES = S34_MAIN_CODES + S34_SUB_CODES


def _load_overrides() -> dict:
    p = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"
    return json.loads(p.read_text(encoding="utf-8"))


# ─── wp_code_overrides 映射 ──────────────────────────────────────────────────


def test_s34_overrides_mapping():
    """S34 在 wp_code_overrides 中映射到 s34-ipo-bundle."""
    data = _load_overrides()
    assert data.get("S34") == S34_COMPONENT_TYPE


def test_s34_children_skip_mapping():
    """S34-0~S34-41 及子表编码在 wp_code_overrides 中映射到 skip."""
    data = _load_overrides()
    for code in S34_ALL_SKIP_CODES:
        assert data.get(code) == "skip", f"{code} 应映射为 skip，实际为 {data.get(code)!r}"


# ─── VALID_COMPONENT_TYPES ───────────────────────────────────────────────────


def test_s34_ipo_bundle_in_valid_component_types():
    """s34-ipo-bundle 已注册于 VALID_COMPONENT_TYPES."""
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert S34_COMPONENT_TYPE in VALID_COMPONENT_TYPES


# ─── validate_overrides ──────────────────────────────────────────────────────


def test_validate_overrides_passes_for_s34():
    """validate_overrides 对 S34 映射及完整线上 overrides 均校验通过."""
    from app.services.wp_code_override_loader import validate_overrides

    # S34 bundle + 所有子底稿 skip 映射单独校验通过
    subset = {"S34": S34_COMPONENT_TYPE}
    subset.update({code: "skip" for code in S34_ALL_SKIP_CODES})
    validate_overrides(subset)

    # 完整线上 overrides 整体校验通过（含 S34 新映射）
    validate_overrides(_load_overrides())
