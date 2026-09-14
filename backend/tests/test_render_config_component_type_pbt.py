"""render-config componentType 属性测试

Feature: a-cycle-docx-online, Property 1: Override 注册正确性

验证注册的 wp_code 通过 render-config 逻辑（derive_component_type）
返回精确匹配的 componentType。

**Validates: Requirements 1.2, 2.7**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.wp_classification_service import (
    ClassificationResult,
    _WP_CODE_OVERRIDE,
    derive_component_type,
)

from tests.test_wp_code_overrides import ALL_EXPECTED, EXPECTED_NON_DOCX, EXPECTED_WORD_TEMPLATE

# ──────────────────────────────────────────────────────────────────────
# 期望映射（从 test_wp_code_overrides 导入的 31 条映射）
# ──────────────────────────────────────────────────────────────────────

_all_31_codes = list(ALL_EXPECTED.keys())


def _make_classification(wp_code: str) -> ClassificationResult:
    """构造最小的 ClassificationResult 用于 derive_component_type 测试。

    derive_component_type 在 ignore_wp_code_override=False 时优先查 _WP_CODE_OVERRIDE，
    命中后直接返回 componentType，不需要 class_code。
    """
    return ClassificationResult(
        wp_code=wp_code,
        sheet_name=f"{wp_code}_sheet",
        class_code=None,
        class_=None,
        scope="test",
        is_real_workpaper=True,
        delegated_module=None,
        render_schema_path=None,
        template_version_id=None,
    )


# ──────────────────────────────────────────────────────────────────────
# Property 1: Override 注册正确性 — render-config 返回精确 componentType
# ──────────────────────────────────────────────────────────────────────


@given(wp_code=st.sampled_from(_all_31_codes))
@settings(max_examples=5, deadline=None)
def test_render_config_returns_exact_component_type(wp_code: str):
    """Property 1: 任意注册的 wp_code，derive_component_type 返回精确匹配的 componentType。

    Feature: a-cycle-docx-online, Property 1: Override 注册正确性

    **Validates: Requirements 1.2, 2.7**
    """
    expected_type = ALL_EXPECTED[wp_code]

    # 验证 _WP_CODE_OVERRIDE 包含此 wp_code
    assert wp_code in _WP_CODE_OVERRIDE, (
        f"{wp_code!r} 未在 _WP_CODE_OVERRIDE（运行时 render-config 路由）中注册"
    )

    # 验证 derive_component_type 返回正确的 componentType
    classification = _make_classification(wp_code)
    actual_type = derive_component_type(classification, ignore_wp_code_override=False)

    assert actual_type == expected_type, (
        f"render-config 对 {wp_code!r} 返回 {actual_type!r}，期望 {expected_type!r}"
    )


@given(wp_code=st.sampled_from(list(EXPECTED_WORD_TEMPLATE.keys())))
@settings(max_examples=5, deadline=None)
def test_word_template_codes_derive_to_word_template(wp_code: str):
    """25 个 word-template wp_code 通过 derive_component_type 均返回 "word-template"。

    **Validates: Requirements 1.2**
    """
    classification = _make_classification(wp_code)
    actual_type = derive_component_type(classification, ignore_wp_code_override=False)
    assert actual_type == "word-template", (
        f"{wp_code!r} 期望 'word-template'，实际 {actual_type!r}"
    )


@given(wp_code=st.sampled_from(list(EXPECTED_NON_DOCX.keys())))
@settings(max_examples=5, deadline=None)
def test_non_docx_codes_derive_to_specific_type(wp_code: str):
    """6 个非 docx wp_code 通过 derive_component_type 返回各自指定的 componentType。

    **Validates: Requirements 2.7**
    """
    expected_type = EXPECTED_NON_DOCX[wp_code]
    classification = _make_classification(wp_code)
    actual_type = derive_component_type(classification, ignore_wp_code_override=False)
    assert actual_type == expected_type, (
        f"{wp_code!r} 期望 {expected_type!r}，实际 {actual_type!r}"
    )
