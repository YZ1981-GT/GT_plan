"""Tests for A14-2 / A14-4 d-form-table render schema integration

Validates: A14 内部控制缺陷 spec tasks 35–37
Verifies:
1. _WP_CODE_OVERRIDE maps A14-2/A14-4 → 'd-form-table'
2. WpRenderSchemaService loads A14-2.yaml and A14-4.yaml correctly
3. Schema YAML structure matches GtDFormTable component expectations:
   - sections, dynamic_table, dictionaries, conclusion

Uses unit test approach (no server startup needed).
"""
from __future__ import annotations

import pytest


class TestWpCodeOverride:
    """Verify A14-2 and A14-4 are registered in _WP_CODE_OVERRIDE."""

    def test_a14_2_maps_to_d_form_table(self):
        from app.services.wp_classification_service import _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE.get("A14-2") == "d-form-table"

    def test_a14_4_maps_to_d_form_table(self):
        from app.services.wp_classification_service import _WP_CODE_OVERRIDE
        assert _WP_CODE_OVERRIDE.get("A14-4") == "d-form-table"


class TestA14_2Schema:
    """WpRenderSchemaService correctly loads A14-2.yaml render schema."""

    @pytest.fixture
    def schema(self):
        from app.services.wp_render_schema_service import WpRenderSchemaService
        service = WpRenderSchemaService()
        return service.load_schema(wp_code="A14-2")

    def test_schema_loads_successfully(self, schema):
        assert schema is not None
        assert isinstance(schema, dict)

    def test_wp_code_and_version(self, schema):
        assert schema.get("wp_code") == "A14-2"
        assert schema.get("template_version") == "v2025-R5"

    def test_sheets_structure(self, schema):
        sheets = schema.get("sheets")
        assert isinstance(sheets, dict)
        assert "main" in sheets

    def test_main_sheet_form_type(self, schema):
        main = schema["sheets"]["main"]
        assert main.get("form_type") == "table"
        assert main.get("title") == "企业层面控制缺陷评价"

    def test_sections_step1_to_step4(self, schema):
        """A14-2 企业层面 has 4 evaluation steps."""
        sections = schema["sheets"]["main"].get("sections", [])
        assert len(sections) == 4
        step_ids = [s["id"] for s in sections]
        assert step_ids == ["step1", "step2", "step3", "step4"]
        # Verify labels are in Chinese
        assert "缺陷描述" in sections[0]["label"]
        assert "缺陷认定" in sections[2]["label"]

    def test_dynamic_table_config(self, schema):
        dt = schema["sheets"]["main"].get("dynamic_table")
        assert dt is not None
        assert dt.get("add_row_button") is True
        assert dt.get("max_rows") == 30
        columns = dt.get("columns", {})
        assert "seq" in columns
        assert "deficiency_desc" in columns
        assert "deficiency_type" in columns
        assert "deficiency_level" in columns
        assert "remediation" in columns

    def test_dictionaries(self, schema):
        dicts = schema["sheets"]["main"].get("dictionaries", {})
        assert "deficiency_type_dict" in dicts
        assert "deficiency_level_dict" in dicts
        # deficiency_type: 设计/运行
        assert len(dicts["deficiency_type_dict"]) == 2
        # deficiency_level: 重大/重要/一般
        assert len(dicts["deficiency_level_dict"]) == 3
        labels = [d["label"] for d in dicts["deficiency_level_dict"]]
        assert "重大缺陷" in labels
        assert "重要缺陷" in labels
        assert "一般缺陷" in labels

    def test_conclusion_composite_mode(self, schema):
        conclusion = schema["sheets"]["main"].get("conclusion")
        assert conclusion is not None
        assert conclusion.get("mode") == "composite"
        assert conclusion.get("audit_explanation_field", {}).get("name") == "audit_explanation"
        assert conclusion.get("overall_conclusion_field", {}).get("name") == "overall_conclusion"


class TestA14_4Schema:
    """WpRenderSchemaService correctly loads A14-4.yaml render schema."""

    @pytest.fixture
    def schema(self):
        from app.services.wp_render_schema_service import WpRenderSchemaService
        service = WpRenderSchemaService()
        return service.load_schema(wp_code="A14-4")

    def test_schema_loads_successfully(self, schema):
        assert schema is not None
        assert isinstance(schema, dict)

    def test_wp_code_and_version(self, schema):
        assert schema.get("wp_code") == "A14-4"
        assert schema.get("template_version") == "v2025-R5"

    def test_sheets_structure(self, schema):
        sheets = schema.get("sheets")
        assert isinstance(sheets, dict)
        assert "main" in sheets

    def test_main_sheet_form_type(self, schema):
        main = schema["sheets"]["main"]
        assert main.get("form_type") == "table"
        assert main.get("title") == "业务流程层面控制缺陷评价"

    def test_sections_step1_to_step7(self, schema):
        """A14-4 业务流程层面 has 7 evaluation steps."""
        sections = schema["sheets"]["main"].get("sections", [])
        assert len(sections) == 7
        step_ids = [s["id"] for s in sections]
        assert step_ids == ["step1", "step2", "step3", "step4", "step5", "step6", "step7"]
        # Verify labels
        assert "缺陷来源" in sections[0]["label"]
        assert "综合评价" in sections[6]["label"]

    def test_dynamic_table_config(self, schema):
        """A14-4 has more columns including business_cycle, likelihood, impact."""
        dt = schema["sheets"]["main"].get("dynamic_table")
        assert dt is not None
        assert dt.get("add_row_button") is True
        assert dt.get("max_rows") == 50
        columns = dt.get("columns", {})
        assert "seq" in columns
        assert "business_cycle" in columns
        assert "control_point" in columns
        assert "deficiency_desc" in columns
        assert "deficiency_type" in columns
        assert "likelihood" in columns
        assert "impact" in columns
        assert "deficiency_level" in columns
        assert "remediation" in columns

    def test_dictionaries_includes_likelihood_and_impact(self, schema):
        """A14-4 has likelihood/impact dicts in addition to type/level."""
        dicts = schema["sheets"]["main"].get("dictionaries", {})
        assert "deficiency_type_dict" in dicts
        assert "deficiency_level_dict" in dicts
        assert "likelihood_dict" in dicts
        assert "impact_dict" in dicts
        # likelihood: 高/中/低
        assert len(dicts["likelihood_dict"]) == 3
        assert len(dicts["impact_dict"]) == 3
        # Check values
        lik_labels = [d["label"] for d in dicts["likelihood_dict"]]
        assert "高" in lik_labels
        assert "中" in lik_labels
        assert "低" in lik_labels

    def test_conclusion_composite_mode(self, schema):
        conclusion = schema["sheets"]["main"].get("conclusion")
        assert conclusion is not None
        assert conclusion.get("mode") == "composite"
        assert conclusion.get("overall_conclusion_field", {}).get("name") == "overall_conclusion"
        assert conclusion.get("overall_conclusion_field", {}).get("label") == "综合评价结论"


class TestSchemaCompatibility:
    """Cross-validation: schemas match GtDFormTable component expectations."""

    @pytest.fixture(params=["A14-2", "A14-4"])
    def schema(self, request):
        from app.services.wp_render_schema_service import WpRenderSchemaService
        service = WpRenderSchemaService()
        return service.load_schema(wp_code=request.param)

    def test_main_sheet_has_form_type_table(self, schema):
        """GtDFormTable expects form_type='table' in the sheet config."""
        assert schema["sheets"]["main"]["form_type"] == "table"

    def test_dynamic_table_columns_have_required_fields(self, schema):
        """Each column must have field, type, label, width."""
        dt = schema["sheets"]["main"]["dynamic_table"]
        for col_key, col_def in dt["columns"].items():
            assert "field" in col_def, f"Column {col_key} missing 'field'"
            assert "type" in col_def, f"Column {col_key} missing 'type'"
            assert "label" in col_def, f"Column {col_key} missing 'label'"
            assert "width" in col_def, f"Column {col_key} missing 'width'"

    def test_dictionary_items_have_value_and_label(self, schema):
        """Each dict item must have 'value' and 'label' for GtDFormTable dropdown rendering."""
        dicts = schema["sheets"]["main"].get("dictionaries", {})
        for dict_name, items in dicts.items():
            for item in items:
                assert "value" in item, f"Dict {dict_name} item missing 'value'"
                assert "label" in item, f"Dict {dict_name} item missing 'label'"

    def test_conclusion_has_mode(self, schema):
        """Conclusion config must have 'mode' for GtDFormTable to render correctly."""
        conclusion = schema["sheets"]["main"]["conclusion"]
        assert "mode" in conclusion
