"""S 类计算型底稿（S3/S15/S20/S21）— 注册契约测试.

Spec: .kiro/specs/s-estimate-calculation-workpapers/ Task 2.3
Validates: Requirements 1.1, 1.2

mirror 自 test_c25_c26_registration_contract.py 模式：
断言 S3/S15/S20/S21 wp_code_overrides 映射 → 对应专属 componentType，
componentType ∈ VALID_COMPONENT_TYPES，已注册于 RENDERER_DISPATCH，
且完整线上 overrides 经 validate_overrides 校验通过。
"""

import json
from pathlib import Path

S3_COMPONENT_TYPE = "s3-policy-change"
S15_COMPONENT_TYPE = "s15-eps-roe"
S20_COMPONENT_TYPE = "s20-revenue-deduction"
S21_COMPONENT_TYPE = "s21-data-asset"

ALL_S_TYPES = [S3_COMPONENT_TYPE, S15_COMPONENT_TYPE, S20_COMPONENT_TYPE, S21_COMPONENT_TYPE]


def _load_overrides() -> dict:
    p = Path(__file__).resolve().parent.parent / "app" / "data" / "wp_code_overrides.json"
    return json.loads(p.read_text(encoding="utf-8"))


# ─── wp_code_overrides 映射 ──────────────────────────────────────────────────


def test_s3_overrides_mapping():
    """S3 在 wp_code_overrides 中映射到 s3-policy-change."""
    data = _load_overrides()
    assert data.get("S3") == S3_COMPONENT_TYPE


def test_s15_overrides_mapping():
    """S15 在 wp_code_overrides 中映射到 s15-eps-roe."""
    data = _load_overrides()
    assert data.get("S15") == S15_COMPONENT_TYPE


def test_s20_overrides_mapping():
    """S20 在 wp_code_overrides 中映射到 s20-revenue-deduction."""
    data = _load_overrides()
    assert data.get("S20") == S20_COMPONENT_TYPE


def test_s21_overrides_mapping():
    """S21 在 wp_code_overrides 中映射到 s21-data-asset."""
    data = _load_overrides()
    assert data.get("S21") == S21_COMPONENT_TYPE


# ─── VALID_COMPONENT_TYPES ───────────────────────────────────────────────────


def test_s3_in_valid_component_types():
    """s3-policy-change 已注册于 VALID_COMPONENT_TYPES."""
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert S3_COMPONENT_TYPE in VALID_COMPONENT_TYPES


def test_s15_in_valid_component_types():
    """s15-eps-roe 已注册于 VALID_COMPONENT_TYPES."""
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert S15_COMPONENT_TYPE in VALID_COMPONENT_TYPES


def test_s20_in_valid_component_types():
    """s20-revenue-deduction 已注册于 VALID_COMPONENT_TYPES."""
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert S20_COMPONENT_TYPE in VALID_COMPONENT_TYPES


def test_s21_in_valid_component_types():
    """s21-data-asset 已注册于 VALID_COMPONENT_TYPES."""
    from app.services.wp_classification_service import VALID_COMPONENT_TYPES

    assert S21_COMPONENT_TYPE in VALID_COMPONENT_TYPES


# ─── RENDERER_DISPATCH ───────────────────────────────────────────────────────


def test_s3_registered_in_dispatch():
    """s3-policy-change 已注册于 RENDERER_DISPATCH."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert S3_COMPONENT_TYPE in RENDERER_DISPATCH


def test_s15_registered_in_dispatch():
    """s15-eps-roe 已注册于 RENDERER_DISPATCH."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert S15_COMPONENT_TYPE in RENDERER_DISPATCH


def test_s20_registered_in_dispatch():
    """s20-revenue-deduction 已注册于 RENDERER_DISPATCH."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert S20_COMPONENT_TYPE in RENDERER_DISPATCH


def test_s21_registered_in_dispatch():
    """s21-data-asset 已注册于 RENDERER_DISPATCH."""
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert S21_COMPONENT_TYPE in RENDERER_DISPATCH


# ─── validate_overrides ──────────────────────────────────────────────────────


def test_validate_overrides_passes_for_s_estimate():
    """validate_overrides 对 S3/S15/S20/S21 映射及完整线上 overrides 均校验通过."""
    from app.services.wp_code_override_loader import validate_overrides

    # 4 个 S 类映射单独校验通过
    validate_overrides(
        {
            "S3": S3_COMPONENT_TYPE,
            "S15": S15_COMPONENT_TYPE,
            "S20": S20_COMPONENT_TYPE,
            "S21": S21_COMPONENT_TYPE,
        }
    )

    # 完整线上 overrides 整体校验通过（含 S3/S15/S20/S21 新映射）
    validate_overrides(_load_overrides())
