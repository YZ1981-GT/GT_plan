"""
Tests for D1/D2 inventory report structure.

Validates Requirements 1.2, 2.2, 4.1:
- Inventory report can distinguish production schema, generated drafts,
  registry suggestions, and confirmed mappings.
- generated/*.yaml is NOT treated as production schema source.
- Conflicts are properly marked with pending_inventory_reconciliation status.
"""

import json
import os
from pathlib import Path

import pytest

# Paths relative to repo root
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "backend" / "data"
SCHEMA_DIR = DATA_DIR / "ledger_adapters" / "wp_render_schema"
GENERATED_DIR = SCHEMA_DIR / "generated"
INVENTORY_DOC = REPO_ROOT / "docs" / "reference" / "workpaper-d1-d2-inventory.md"


class TestInventoryDocumentStructure:
    """Test that the inventory document exists and has required sections."""

    def test_inventory_document_exists(self):
        """Inventory markdown must exist as Task 3 deliverable."""
        assert INVENTORY_DOC.exists(), (
            f"Inventory document not found at {INVENTORY_DOC}"
        )

    def test_inventory_contains_machine_readable_json(self):
        """Inventory must contain a JSON block that downstream tools can parse."""
        content = INVENTORY_DOC.read_text(encoding="utf-8")
        # Extract JSON block between ```json and ```
        json_start = content.find("```json")
        json_end = content.find("```", json_start + 7)
        assert json_start != -1, "No ```json block found in inventory document"
        assert json_end != -1, "JSON block not properly closed"

        json_text = content[json_start + 7:json_end].strip()
        data = json.loads(json_text)

        # Validate structure
        assert "items" in data
        assert "reconciliation_rules" in data
        assert data["reconciliation_rules"]["generated_is_not_production"] is True

    def test_inventory_items_have_required_fields(self):
        """Each inventory item must contain the required reconciliation fields."""
        content = INVENTORY_DOC.read_text(encoding="utf-8")
        json_start = content.find("```json")
        json_end = content.find("```", json_start + 7)
        json_text = content[json_start + 7:json_end].strip()
        data = json.loads(json_text)

        required_fields = [
            "wp_code",
            "account_code",
            "account_name",
            "report_row",
            "note_section",
            "cross_ref_note_code",
            "production_schema_path",
            "generated_schema_path",
            "sheet_inventory",
            "known_conflicts",
            "mapping_status",
        ]

        for item in data["items"]:
            for field in required_fields:
                assert field in item, (
                    f"Item {item.get('wp_code', '?')} missing field: {field}"
                )


class TestProductionVsGeneratedDistinction:
    """Test that inventory correctly distinguishes production from generated schemas."""

    def test_production_schemas_exist_at_root(self):
        """Production schemas referenced in inventory must exist at schema root."""
        production_files = [
            "C-D1-disclosure.yaml",
            "C-D2-disclosure.yaml",
            "D2A.yaml",
            "D-D2-8.yaml",
            "D-D2-13.yaml",
        ]
        for fname in production_files:
            path = SCHEMA_DIR / fname
            assert path.exists(), (
                f"Production schema {fname} not found at {SCHEMA_DIR}"
            )

    def test_generated_schemas_exist_in_generated_dir(self):
        """Generated schemas referenced must be in the generated/ subdirectory."""
        generated_files = [
            "D1.yaml",
            "D2.yaml",
            "D2-1.yaml",
            "D2-6.yaml",
        ]
        for fname in generated_files:
            path = GENERATED_DIR / fname
            assert path.exists(), (
                f"Generated schema {fname} not found at {GENERATED_DIR}"
            )

    def test_generated_not_in_production_root(self):
        """generated/*.yaml must NOT appear as root-level production schemas."""
        # The key D1/D2 generated files should not be at root level
        # (they should only be in generated/ subdir)
        root_files = [f.name for f in SCHEMA_DIR.iterdir() if f.is_file()]
        # D1.yaml should not be at root (only C-D1-disclosure.yaml is production)
        assert "D1.yaml" not in root_files, (
            "D1.yaml should not be at production root — "
            "only C-D1-disclosure.yaml is production"
        )
        # D2.yaml should not be at root (only C-D2-disclosure.yaml is production)
        assert "D2.yaml" not in root_files, (
            "D2.yaml should not be at production root — "
            "only C-D2-disclosure.yaml is production"
        )

    def test_inventory_marks_generated_as_non_production(self):
        """Inventory JSON must declare generated_is_not_production=true."""
        content = INVENTORY_DOC.read_text(encoding="utf-8")
        json_start = content.find("```json")
        json_end = content.find("```", json_start + 7)
        json_text = content[json_start + 7:json_end].strip()
        data = json.loads(json_text)

        rules = data["reconciliation_rules"]
        assert rules["generated_is_not_production"] is True
        assert "generated" in rules["generated_schema_dir"]
        assert "generated" not in rules["production_schema_dir"]


class TestMappingStatusReconciliation:
    """Test that conflict items are marked with pending_inventory_reconciliation."""

    def _load_inventory_items(self):
        content = INVENTORY_DOC.read_text(encoding="utf-8")
        json_start = content.find("```json")
        json_end = content.find("```", json_start + 7)
        json_text = content[json_start + 7:json_end].strip()
        return json.loads(json_text)["items"]

    def test_d1_has_pending_status(self):
        """D1 has known conflicts → must be pending_inventory_reconciliation."""
        items = self._load_inventory_items()
        d1 = next((i for i in items if i["wp_code"] == "D1"), None)
        assert d1 is not None, "D1 not found in inventory"
        assert d1["mapping_status"] == "pending_inventory_reconciliation"
        assert len(d1["known_conflicts"]) > 0

    def test_d2_has_pending_status(self):
        """D2 has known conflicts → must be pending_inventory_reconciliation."""
        items = self._load_inventory_items()
        d2 = next((i for i in items if i["wp_code"] == "D2"), None)
        assert d2 is not None, "D2 not found in inventory"
        assert d2["mapping_status"] == "pending_inventory_reconciliation"
        assert len(d2["known_conflicts"]) > 0

    def test_confirmed_items_have_no_conflicts(self):
        """Items with confirmed_production status must have empty known_conflicts."""
        items = self._load_inventory_items()
        confirmed = [i for i in items if i["mapping_status"] == "confirmed_production"]
        for item in confirmed:
            assert len(item["known_conflicts"]) == 0, (
                f"{item['wp_code']} is confirmed but has conflicts: "
                f"{item['known_conflicts']}"
            )

    def test_valid_mapping_statuses(self):
        """All items must use one of the valid mapping_status values."""
        content = INVENTORY_DOC.read_text(encoding="utf-8")
        json_start = content.find("```json")
        json_end = content.find("```", json_start + 7)
        json_text = content[json_start + 7:json_end].strip()
        data = json.loads(json_text)

        valid_statuses = set(data["reconciliation_rules"]["valid_mapping_statuses"])
        for item in data["items"]:
            assert item["mapping_status"] in valid_statuses, (
                f"{item['wp_code']} has invalid status: {item['mapping_status']}"
            )


class TestCrossReferenceReconciliation:
    """Test reconciliation between data sources for D1/D2."""

    def test_d1_report_row_conflict_documented(self):
        """D1 report_row conflict (BS-004 vs BS-003) must be in known_conflicts."""
        content = INVENTORY_DOC.read_text(encoding="utf-8")
        json_start = content.find("```json")
        json_end = content.find("```", json_start + 7)
        json_text = content[json_start + 7:json_end].strip()
        data = json.loads(json_text)

        d1 = next((i for i in data["items"] if i["wp_code"] == "D1"), None)
        conflicts_text = " ".join(d1["known_conflicts"])
        assert "BS-004" in conflicts_text or "BS-003" in conflicts_text, (
            "D1 report_row conflict not documented in known_conflicts"
        )

    def test_d2_note_section_conflict_documented(self):
        """D2 note_section conflict (五、3 vs 5.7) must be in known_conflicts."""
        content = INVENTORY_DOC.read_text(encoding="utf-8")
        json_start = content.find("```json")
        json_end = content.find("```", json_start + 7)
        json_text = content[json_start + 7:json_end].strip()
        data = json.loads(json_text)

        d2 = next((i for i in data["items"] if i["wp_code"] == "D2"), None)
        conflicts_text = " ".join(d2["known_conflicts"])
        assert "五、3" in conflicts_text or "5.7" in conflicts_text, (
            "D2 note_section conflict not documented in known_conflicts"
        )

    def test_wp_account_mapping_has_d1_d2(self):
        """wp_account_mapping.json must contain D1 and D2 entries."""
        mapping_path = DATA_DIR / "wp_account_mapping.json"
        assert mapping_path.exists()
        data = json.loads(mapping_path.read_text(encoding="utf-8"))
        wp_codes = [m["wp_code"] for m in data["mappings"]]
        assert "D1" in wp_codes
        assert "D2" in wp_codes

    def test_cross_wp_references_has_d1_d2_sources(self):
        """cross_wp_references.json must reference D1 and D2 as sources."""
        ref_path = DATA_DIR / "cross_wp_references.json"
        assert ref_path.exists()
        data = json.loads(ref_path.read_text(encoding="utf-8"))
        source_wps = {r["source_wp"] for r in data["references"]}
        assert "D1" in source_wps, "D1 not found as source in cross_wp_references"
        assert "D2" in source_wps, "D2 not found as source in cross_wp_references"
