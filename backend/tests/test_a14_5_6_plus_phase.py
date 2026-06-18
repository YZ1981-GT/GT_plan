"""Tests for A14-5 / A14-6 plus-phase workpaper registration and schema

Validates: A14 内部控制缺陷 spec tasks 42–43 (plus 阶段)
Verifies:
1. _WP_CODE_OVERRIDE maps A14-5 → 'd-form-table'
2. _WP_CODE_OVERRIDE maps A14-6 → 'e-control-test'
3. WpRenderSchemaService loads A14-5.yaml correctly
4. A14-5 YAML structure matches GtDFormTable component expectations
5. A14-6 generated schema exists and has e-control-test component_type

Uses unit test approach (no server startup needed).
"""
from __future__ import annotations

import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# 1. _WP_CODE_OVERRIDE registration
# ---------------------------------------------------------------------------


class TestWpCodeOverridePlusPhase:
    """Verify A14-5 and A14-6 are registered in _WP_CODE_OVERRIDE."""

    def test_a14_5_maps_to_d_form_table(self):
        from app.services.wp_classification_service import _WP_CODE_OVERRIDE

        assert _WP_CODE_OVERRIDE.get("A14-5") == "d-form-table"

    def test_a14_6_maps_to_e_control_test(self):
        from app.services.wp_classification_service import _WP_CODE_OVERRIDE

        assert _WP_CODE_OVERRIDE.get("A14-6") == "e-control-test"


# ---------------------------------------------------------------------------
# 2. A14-5 render schema (d-form-table)
# ---------------------------------------------------------------------------


class TestA14_5Schema:
    """WpRenderSchemaService correctly loads A14-5.yaml render schema."""

    @pytest.fixture
    def schema(self):
        from app.services.wp_render_schema_service import WpRenderSchemaService

        service = WpRenderSchemaService()
        return service.load_schema(wp_code="A14-5")

    def test_schema_loads_successfully(self, schema):
        assert schema is not None
        assert isinstance(schema, dict)

    def test_wp_code_and_version(self, schema):
        assert schema.get("wp_code") == "A14-5"
        assert schema.get("template_version") == "v2025-R5"

    def test_sheets_structure(self, schema):
        sheets = schema.get("sheets")
        assert isinstance(sheets, dict)
        assert "main" in sheets

    def test_main_sheet_form_type(self, schema):
        main = schema["sheets"]["main"]
        assert main.get("form_type") == "table"
        assert "与其他缺陷" in main.get("title", "")

    def test_dynamic_table_config(self, schema):
        dt = schema["sheets"]["main"].get("dynamic_table")
        assert dt is not None
        assert dt.get("add_row_button") is True
        assert dt.get("max_rows") == 30
        columns = dt.get("columns", {})
        assert "seq" in columns
        assert "source_deficiency" in columns
        assert "source_wp" in columns
        assert "individual_level" in columns
        assert "combined_level" in columns
        assert "remarks" in columns

    def test_dynamic_table_columns_have_required_fields(self, schema):
        """Each column must have field, type, label, width for GtDFormTable."""
        dt = schema["sheets"]["main"]["dynamic_table"]
        for col_key, col_def in dt["columns"].items():
            assert "field" in col_def, f"Column {col_key} missing 'field'"
            assert "type" in col_def, f"Column {col_key} missing 'type'"
            assert "label" in col_def, f"Column {col_key} missing 'label'"
            assert "width" in col_def, f"Column {col_key} missing 'width'"

    def test_dictionaries(self, schema):
        dicts = schema["sheets"]["main"].get("dictionaries", {})
        assert "level_dict" in dicts
        # level_dict: 重大/重要/一般
        assert len(dicts["level_dict"]) == 3
        labels = [d["label"] for d in dicts["level_dict"]]
        assert "重大缺陷" in labels
        assert "重要缺陷" in labels
        assert "一般缺陷" in labels

    def test_dictionary_items_have_value_and_label(self, schema):
        """Each dict item must have 'value' and 'label'."""
        dicts = schema["sheets"]["main"].get("dictionaries", {})
        for dict_name, items in dicts.items():
            for item in items:
                assert "value" in item, f"Dict {dict_name} item missing 'value'"
                assert "label" in item, f"Dict {dict_name} item missing 'label'"

    def test_conclusion_composite_mode(self, schema):
        conclusion = schema["sheets"]["main"].get("conclusion")
        assert conclusion is not None
        assert conclusion.get("mode") == "composite"
        assert conclusion.get("audit_explanation_field", {}).get("name") == "audit_explanation"
        assert conclusion.get("overall_conclusion_field", {}).get("name") == "overall_conclusion"

    def test_fields_section(self, schema):
        """A14-5 has form-level fields for combined evaluation."""
        fields = schema["sheets"]["main"].get("fields")
        assert fields is not None
        assert len(fields) >= 2
        field_names = [f["field"] for f in fields]
        assert "combined_eval_rationale" in field_names
        assert "combined_eval_result" in field_names


# ---------------------------------------------------------------------------
# 3. A14-6 generated schema (e-control-test)
# ---------------------------------------------------------------------------


class TestA14_6GeneratedSchema:
    """Verify A14-6 generated schema exists and is correctly structured."""

    @pytest.fixture
    def schema_path(self):
        return Path(__file__).resolve().parents[1] / (
            "data/ledger_adapters/wp_render_schema/generated/A14-6.yaml"
        )

    @pytest.fixture
    def schema(self, schema_path):
        import yaml

        assert schema_path.is_file(), f"A14-6 generated schema not found at {schema_path}"
        with open(schema_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_schema_file_exists(self, schema_path):
        assert schema_path.is_file()

    def test_wp_code(self, schema):
        assert schema.get("wp_code") == "A14-6"

    def test_template_version(self, schema):
        assert schema.get("template_version") == "v2025-R5"

    def test_sheet_component_type_is_e_control_test(self, schema):
        """The sheet must declare component_type: e-control-test."""
        sheets = schema.get("sheets", {})
        # A14-6 sheet name: T4非财务报告内部控制缺陷评价
        sheet_key = list(sheets.keys())[0]
        sheet = sheets[sheet_key]
        assert sheet.get("component_type") == "e-control-test"

    def test_sheet_has_dynamic_table(self, schema):
        sheets = schema.get("sheets", {})
        sheet_key = list(sheets.keys())[0]
        sheet = sheets[sheet_key]
        dt = sheet.get("dynamic_table")
        assert dt is not None
        assert dt.get("start_row") == 10
        assert dt.get("header_row") == 9

    def test_template_path_references_xlsx(self, schema):
        tp = schema.get("template_path", "")
        assert "A14-6" in tp
        assert tp.endswith(".xlsx")
