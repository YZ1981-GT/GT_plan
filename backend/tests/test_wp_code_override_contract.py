"""Override 契约测试 — 验证 _WP_CODE_OVERRIDE 所有 value ∈ VALID_COMPONENT_TYPES

Requirements: 4.1, 4.2, 4.3
"""

from app.services.wp_classification_service import (
    VALID_COMPONENT_TYPES,
    _WP_CODE_OVERRIDE,
)


def test_all_override_values_are_valid_component_types():
    """Property 4: 所有 override value ∈ VALID_COMPONENT_TYPES

    断言 _WP_CODE_OVERRIDE 字典中每个映射值都属于合法 componentType 集合。
    失败时报告具体非法 wp_code 和对应 value。

    Validates: Requirements 4.1, 4.2, 4.3
    """
    invalid = {k: v for k, v in _WP_CODE_OVERRIDE.items() if v not in VALID_COMPONENT_TYPES}
    assert not invalid, (
        f"以下 wp_code 映射到非法 componentType（不在 VALID_COMPONENT_TYPES 中）:\n"
        + "\n".join(f"  {code!r} -> {ctype!r}" for code, ctype in sorted(invalid.items()))
    )


def test_override_dict_is_non_empty():
    """契约前置条件：_WP_CODE_OVERRIDE 不为空（防止误删导致假绿）

    Validates: Requirements 4.2
    """
    assert len(_WP_CODE_OVERRIDE) > 0, "_WP_CODE_OVERRIDE 不应为空字典"
