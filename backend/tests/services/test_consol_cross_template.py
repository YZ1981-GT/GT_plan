"""Sprint B.2.4 — 跨模板共存联动单测 + PBT.

Tests:
1. translate_child_section 共有章节直接通过
2. translate_child_section format_diff 走 adapt_table_data
3. translate_child_section 子公司独有 → archived 标记
4. translate_child_section 合并版独有 → not_applicable
5. translate_child_section 同模板无需翻译
6. aggregate_cross_template 混合模板子公司汇总
7. build_cross_template_provenance 标识模板类型
8. build_cross_template_provenance 空列表
9. build_cross_template_provenance 单一模板
10. PBT: 跨模板汇总后 provenance.has_cross_template 正确
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.services.consol_cross_template_service import (
    aggregate_cross_template,
    build_cross_template_provenance,
    translate_child_section,
)


# ---------------------------------------------------------------------------
# Fixtures: mock diff_data
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_diff_data():
    """模拟 load_diff_data 返回的差异数据."""
    return {
        "version": "1.0.0",
        "is_mock": True,
        "common_sections": [
            {
                "section_title": "货币资金",
                "soe_section_id": "soe_cash",
                "listed_section_id": "listed_cash",
            },
            {
                "section_title": "应收账款",
                "soe_section_id": "soe_ar",
                "listed_section_id": "listed_ar",
            },
        ],
        "soe_only_sections": [
            {"section_id": "soe_special_fund", "title": "专项储备"},
        ],
        "listed_only_sections": [
            {"section_id": "listed_eps", "title": "每股收益"},
        ],
        "format_diff_sections": [
            {
                "section_title": "固定资产",
                "soe_section_id": "soe_fa",
                "listed_section_id": "listed_fa",
                "soe_format": {"content_type": "table", "table_count": 2},
                "listed_format": {"content_type": "table", "table_count": 1},
                "field_mapping": {
                    "column_remap": {"col_movement": "col_category_sum"},
                },
            },
        ],
    }


# ---------------------------------------------------------------------------
# B.2.1 translate_child_section tests
# ---------------------------------------------------------------------------


class TestTranslateChildSection:
    """translate_child_section 单测."""

    def test_common_section_passes_through(self, mock_diff_data):
        """共有章节直接通过，标记 _translated."""
        child_section = {
            "section_id": "soe_cash",
            "table_data": {"rows": [{"label": "银行存款", "values": {"col_amount_end": 100}}]},
        }
        result = translate_child_section(
            child_section, from_type="soe", to_type="listed", diff_data=mock_diff_data,
        )
        assert result["_translated"] is True
        assert result["_translation_type"] == "common"
        assert result["_target_section_id"] == "listed_cash"
        assert result["table_data"]["rows"][0]["label"] == "银行存款"

    def test_format_diff_uses_adapt_table_data(self, mock_diff_data):
        """格式差异章节走 adapt_table_data 列重映射."""
        child_section = {
            "section_id": "soe_fa",
            "table_data": {
                "rows": [{"label": "房屋", "values": {"col_movement": 500}}],
                "_columns_meta": [
                    {"id": "col_label", "label": "项目"},
                    {"id": "col_movement", "label": "变动额"},
                ],
            },
        }
        result = translate_child_section(
            child_section, from_type="soe", to_type="listed", diff_data=mock_diff_data,
        )
        assert result["_translated"] is True
        assert result["_translation_type"] == "format_diff"
        # column_remap: col_movement → col_category_sum
        meta = result["table_data"]["_columns_meta"]
        col_ids = [c["id"] for c in meta]
        assert "col_category_sum" in col_ids
        assert "col_movement" not in col_ids

    def test_source_only_archived(self, mock_diff_data):
        """子公司独有章节 → _archived_from_child 标记."""
        child_section = {
            "section_id": "soe_special_fund",
            "table_data": {"rows": [{"label": "专项储备", "values": {"col_amount": 200}}]},
        }
        result = translate_child_section(
            child_section, from_type="soe", to_type="listed", diff_data=mock_diff_data,
        )
        assert result["_archived_from_child"] is True
        assert result["_translation_type"] == "source_only"
        # 数据不丢
        assert result["table_data"]["rows"][0]["values"]["col_amount"] == 200

    def test_target_only_not_applicable(self, mock_diff_data):
        """合并版独有章节 → not_applicable."""
        child_section = {
            "section_id": "listed_eps",
            "table_data": {},
        }
        # 从 listed 视角看，listed_eps 是 listed_only → 对 soe 子公司来说是 target_only
        result = translate_child_section(
            child_section, from_type="soe", to_type="listed", diff_data=mock_diff_data,
        )
        # listed_eps 在 listed_only_sections 中，source=soe → target_only
        assert result.get("_not_applicable") is True or result.get("_archived_from_child") is True

    def test_same_template_no_translation(self, mock_diff_data):
        """同模板无需翻译，直接返回深拷贝."""
        child_section = {
            "section_id": "soe_cash",
            "table_data": {"rows": [{"label": "现金", "values": {"col_amount": 50}}]},
        }
        result = translate_child_section(
            child_section, from_type="soe", to_type="soe", diff_data=mock_diff_data,
        )
        # 同模板直接返回
        assert result["section_id"] == "soe_cash"
        assert result["table_data"]["rows"][0]["values"]["col_amount"] == 50
        # 不应有翻译标记
        assert "_translated" not in result

    def test_invalid_input_returns_not_applicable(self, mock_diff_data):
        """无效输入返回 not_applicable."""
        result = translate_child_section(
            None, from_type="soe", to_type="listed", diff_data=mock_diff_data,
        )
        assert result["_not_applicable"] is True


# ---------------------------------------------------------------------------
# B.2.2 aggregate_cross_template tests
# ---------------------------------------------------------------------------


class TestAggregateCrossTemplate:
    """aggregate_cross_template 单测."""

    def test_mixed_template_aggregation(self, mock_diff_data, monkeypatch):
        """混合模板子公司汇总."""
        # Mock load_diff_data to return our fixture
        monkeypatch.setattr(
            "app.services.consol_cross_template_service.load_diff_data",
            lambda: mock_diff_data,
        )

        children = [
            {
                "project_id": uuid4(),
                "company_name": "子公司A",
                "template_type": "soe",
                "section_data": {
                    "section_id": "soe_cash",
                    "table_data": {
                        "rows": [
                            {"label": "银行存款", "values": {"col_amount_end": 100}},
                            {"label": "合计", "values": {"col_amount_end": 100}, "is_total": True},
                        ],
                    },
                },
            },
            {
                "project_id": uuid4(),
                "company_name": "子公司B",
                "template_type": "listed",
                "section_data": {
                    "section_id": "listed_cash",
                    "table_data": {
                        "rows": [
                            {"label": "银行存款", "values": {"col_amount_end": 50}},
                            {"label": "合计", "values": {"col_amount_end": 50}, "is_total": True},
                        ],
                    },
                },
            },
        ]

        result = asyncio.run(
            aggregate_cross_template(
                consol_project_id=uuid4(),
                section_id="soe_cash",
                year=2025,
                children=children,
                consol_type="soe",
            )
        )

        assert result["section_id"] == "soe_cash"
        assert result["child_count"] == 2
        assert result["translated_count"] == 2
        assert result["provenance"]["has_cross_template"] is True
        assert set(result["provenance"]["template_types_involved"]) == {"soe", "listed"}
        # 汇总行应包含两个子公司的数据
        assert len(result["aggregated_rows"]) == 4  # 2 rows × 2 children

    def test_archived_sections_collected(self, mock_diff_data, monkeypatch):
        """子公司独有章节被归档收集."""
        monkeypatch.setattr(
            "app.services.consol_cross_template_service.load_diff_data",
            lambda: mock_diff_data,
        )

        children = [
            {
                "project_id": uuid4(),
                "company_name": "子公司A",
                "template_type": "soe",
                "section_data": {
                    "section_id": "soe_special_fund",
                    "table_data": {"rows": [{"label": "专项储备", "values": {"col_amount": 200}}]},
                },
            },
        ]

        result = asyncio.run(
            aggregate_cross_template(
                consol_project_id=uuid4(),
                section_id="soe_special_fund",
                year=2025,
                children=children,
                consol_type="listed",
            )
        )

        assert len(result["archived_sections"]) == 1
        assert result["archived_sections"][0]["company_name"] == "子公司A"
        assert result["translated_count"] == 0


# ---------------------------------------------------------------------------
# B.2.3 build_cross_template_provenance tests
# ---------------------------------------------------------------------------


class TestBuildCrossTemplateProvenance:
    """build_cross_template_provenance 单测."""

    def test_mixed_templates_detected(self):
        """混合模板正确标识."""
        contributions = [
            {"project_id": "p1", "company_name": "子A", "template_type": "soe", "amount": 100},
            {"project_id": "p2", "company_name": "子B", "template_type": "listed", "amount": 50},
        ]
        result = build_cross_template_provenance(contributions)
        assert result["has_cross_template"] is True
        assert sorted(result["template_types_involved"]) == ["listed", "soe"]
        assert len(result["contributions"]) == 2

    def test_empty_contributions(self):
        """空列表返回 has_cross_template=False."""
        result = build_cross_template_provenance([])
        assert result["has_cross_template"] is False
        assert result["template_types_involved"] == []
        assert result["contributions"] == []

    def test_single_template_type(self):
        """单一模板类型 has_cross_template=False."""
        contributions = [
            {"project_id": "p1", "company_name": "子A", "template_type": "soe", "amount": 100},
            {"project_id": "p2", "company_name": "子B", "template_type": "soe", "amount": 200},
        ]
        result = build_cross_template_provenance(contributions)
        assert result["has_cross_template"] is False
        assert result["template_types_involved"] == ["soe"]

    def test_provenance_preserves_amounts(self):
        """provenance 保留各子公司金额."""
        contributions = [
            {"project_id": "p1", "company_name": "子A", "template_type": "soe", "amount": Decimal("100.50")},
        ]
        result = build_cross_template_provenance(contributions)
        assert result["contributions"][0]["amount"] == Decimal("100.50")


# ---------------------------------------------------------------------------
# B.2.4 PBT: 跨模板汇总后 provenance.has_cross_template 正确
# ---------------------------------------------------------------------------


# Hypothesis strategies
template_type_st = st.sampled_from(["soe", "listed"])

contribution_st = st.fixed_dictionaries({
    "project_id": st.text(min_size=1, max_size=10, alphabet="abcdef0123456789"),
    "company_name": st.text(min_size=1, max_size=20),
    "template_type": template_type_st,
    "amount": st.one_of(
        st.none(),
        st.decimals(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False),
    ),
})


class TestCrossTemplatePBT:
    """PBT: 跨模板 provenance 属性测试.

    **Validates: Requirements D14, B.2.3**
    """

    @given(contributions=st.lists(contribution_st, min_size=0, max_size=20))
    @settings(max_examples=200, deadline=None)
    def test_has_cross_template_iff_multiple_types(self, contributions):
        """Property: has_cross_template == True iff len(unique template_types) > 1.

        **Validates: Requirements B.2.3**
        """
        result = build_cross_template_provenance(contributions)

        # 计算实际唯一模板类型数
        actual_types = set(c.get("template_type", "unknown") for c in contributions)

        # 属性：has_cross_template 当且仅当有多种模板类型
        if len(actual_types) > 1:
            assert result["has_cross_template"] is True, (
                f"Expected has_cross_template=True for types {actual_types}"
            )
        else:
            assert result["has_cross_template"] is False, (
                f"Expected has_cross_template=False for types {actual_types}"
            )

        # 属性：template_types_involved 是排序后的唯一类型列表
        assert result["template_types_involved"] == sorted(actual_types)

        # 属性：contributions 数量 == 输入数量
        assert len(result["contributions"]) == len(contributions)
