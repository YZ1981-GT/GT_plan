"""Unit tests for wp_classification_service.

Tests derive_component_type mapping and ClassificationResult handling.
Requirements: 1.2（9 类全覆盖）+ 3.9（决策树禁止 Univer 兜底）
"""

from __future__ import annotations

import uuid

import pytest

from app.services.wp_classification_service import (
    ClassificationNotFoundError,
    ClassificationResult,
    VALID_COMPONENT_TYPES,
    derive_component_type,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


def _make_classification(
    class_code: str | None,
    wp_code: str = "D2",
    sheet_name: str = "测试sheet",
) -> ClassificationResult:
    """Helper to create a ClassificationResult for testing."""
    return ClassificationResult(
        wp_code=wp_code,
        sheet_name=sheet_name,
        class_code=class_code,
        class_=class_code,
        scope="standalone",
        is_real_workpaper=True,
        delegated_module=None,
        render_schema_path=None,
        template_version_id=uuid.uuid4(),
        has_override=False,
    )


# ─── derive_component_type: 9 类全覆盖 ──────────────────────────────────────


class TestDeriveComponentType:
    """Test derive_component_type covers all 9 classes → componentType whitelist."""

    def test_a_program_console(self):
        result = derive_component_type(_make_classification("A-程序表"))
        assert result == "a-program-console"

    def test_a_any_subclass(self):
        result = derive_component_type(_make_classification("A-替代程序"))
        assert result == "a-program-console"

    def test_b_index(self):
        result = derive_component_type(_make_classification("B-目录"))
        assert result == "b-index"

    def test_c_note_table(self):
        result = derive_component_type(_make_classification("C-附注"))
        assert result == "c-note-table"

    def test_d_default_form_table(self):
        """D- without specific sub-routing → d-form-table."""
        result = derive_component_type(_make_classification("D-检查表"))
        assert result == "d-form-table"

    def test_d_form_paragraph(self):
        result = derive_component_type(_make_classification("D-政策检查"))
        assert result == "d-form-paragraph"

    def test_d_form_qa(self):
        result = derive_component_type(_make_classification("D-业务模式"))
        assert result == "d-form-qa"

    def test_d_form_confirmation_函证(self):
        result = derive_component_type(_make_classification("D-函证"))
        assert result == "d-form-confirmation"

    def test_d_form_confirmation_盘点(self):
        result = derive_component_type(_make_classification("D-盘点"))
        assert result == "d-form-confirmation"

    def test_d_form_confirmation_访谈(self):
        result = derive_component_type(_make_classification("D-访谈"))
        assert result == "d-form-confirmation"

    def test_d_form_confirmation_询证(self):
        result = derive_component_type(_make_classification("D-询证"))
        assert result == "d-form-confirmation"

    def test_d_form_review(self):
        result = derive_component_type(_make_classification("D-复核记录"))
        assert result == "d-form-review"

    def test_d_form_review_short(self):
        result = derive_component_type(_make_classification("D-复核"))
        assert result == "d-form-review"

    def test_e_control_test(self):
        result = derive_component_type(_make_classification("E-控制测试"))
        assert result == "e-control-test"

    def test_e_any_subclass(self):
        result = derive_component_type(_make_classification("E-评价控制偏差"))
        assert result == "e-control-test"

    def test_f_univer(self):
        result = derive_component_type(_make_classification("F-数据表"))
        assert result == "univer"

    def test_f_审定表_audit_sheet(self):
        """F-审定表 → audit-sheet（精确匹配优先于 F- 前缀 fallback）。"""
        result = derive_component_type(_make_classification("F-审定表"))
        assert result == "audit-sheet"

    def test_f_明细表_audit_sheet(self):
        """F-明细表 → audit-sheet（_F_SUB_ROUTING 精确匹配）；其余 F- 仍 fallback univer。"""
        assert derive_component_type(_make_classification("F-明细表")) == "audit-sheet"
        assert derive_component_type(_make_classification("F-分析表")) == "univer"
        assert derive_component_type(_make_classification("F-汇总表")) == "univer"

    def test_bad_debt_sheet_name_override(self):
        """坏账准备明细表 sheet（class_code=F-明细表，共享）→ bad-debt-sheet（sheet 名级专用路由优先）。"""
        result = derive_component_type(
            _make_classification("F-明细表", wp_code="D2", sheet_name="坏账准备明细表D2-3")
        )
        assert result == "bad-debt-sheet"

    def test_bad_debt_sheet_name_override_other_cycle(self):
        """其他循环坏账准备明细表（如 G2-3）同样路由到 bad-debt-sheet。"""
        result = derive_component_type(
            _make_classification("F-明细表", wp_code="G2", sheet_name="坏账准备明细表G2-3")
        )
        assert result == "bad-debt-sheet"

    def test_non_bad_debt_detail_sheet_not_hijacked(self):
        """非坏账准备的普通明细表 sheet 不被 sheet 名级覆盖劫持，仍走 class_code 派生（F-明细表 → audit-sheet）。"""
        result = derive_component_type(
            _make_classification("F-明细表", wp_code="D2", sheet_name="应收账款明细表D2-2")
        )
        assert result == "audit-sheet"

    def test_g_univer(self):
        result = derive_component_type(_make_classification("G-测算"))
        assert result == "univer"

    def test_h_static_doc(self):
        result = derive_component_type(_make_classification("H-辅助说明"))
        assert result == "h-static-doc"

    def test_i_skip(self):
        result = derive_component_type(_make_classification("I-占位"))
        assert result == "skip"


# ─── derive_component_type: 禁止 Univer 兜底 ────────────────────────────────


class TestNoUniverFallback:
    """Requirement 3.9: No Univer fallback for unclassified sheets."""

    def test_none_class_code_raises(self):
        """class_code=None → ClassificationNotFoundError."""
        with pytest.raises(ClassificationNotFoundError):
            derive_component_type(_make_classification(None))

    def test_empty_class_code_raises(self):
        """class_code='' → ClassificationNotFoundError."""
        with pytest.raises(ClassificationNotFoundError):
            derive_component_type(_make_classification(""))

    def test_unknown_prefix_raises(self):
        """Unknown class_code prefix → ClassificationNotFoundError."""
        with pytest.raises(ClassificationNotFoundError):
            derive_component_type(_make_classification("X-未知"))

    def test_pending_classification_raises(self):
        """_pending_classification → ClassificationNotFoundError."""
        with pytest.raises(ClassificationNotFoundError):
            derive_component_type(_make_classification("_pending_classification"))


# ─── derive_component_type: 返回值在白名单内 ────────────────────────────────


class TestComponentTypeWhitelist:
    """All returned componentTypes must be in VALID_COMPONENT_TYPES."""

    @pytest.mark.parametrize(
        "class_code",
        [
            "A-程序表",
            "B-目录",
            "C-附注",
            "D-检查表",
            "D-政策检查",
            "D-业务模式",
            "D-函证",
            "D-复核记录",
            "E-控制测试",
            "F-数据表",
            "F-审定表",
            "G-测算",
            "H-辅助说明",
            "I-占位",
        ],
    )
    def test_all_valid_classes_return_whitelist_value(self, class_code: str):
        result = derive_component_type(_make_classification(class_code))
        assert result in VALID_COMPONENT_TYPES, (
            f"class_code='{class_code}' returned '{result}' "
            f"which is not in VALID_COMPONENT_TYPES"
        )


# ─── ClassificationResult dataclass ─────────────────────────────────────────


class TestClassificationResult:
    """Test ClassificationResult dataclass behavior."""

    def test_default_has_override_false(self):
        cr = _make_classification("A-程序表")
        assert cr.has_override is False

    def test_override_flag(self):
        cr = ClassificationResult(
            wp_code="D2",
            sheet_name="test",
            class_code="D-检查表",
            class_="D-检查表",
            scope="standalone",
            is_real_workpaper=True,
            delegated_module=None,
            render_schema_path=None,
            template_version_id=None,
            has_override=True,
        )
        assert cr.has_override is True
