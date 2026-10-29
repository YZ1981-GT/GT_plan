import json
from pathlib import Path

from app.services.ledger_import_application_service import LedgerImportApplicationService
from app.services.smart_import_engine import _resolve_sheet_mapping
from app.services.ledger_import_mapping_contract import (
    normalize_custom_mapping,
    resolve_sheet_mapping,
)


def test_legacy_file_sheet_mapping_is_not_lost():
    source = {"总账.xlsx/序时账": {"账簿类型": "company_name", "凭证字": "voucher_type"}}
    normalized = normalize_custom_mapping(source)
    assert normalized == {
        "confirmed_mappings": [{
            "file_name": "总账.xlsx",
            "sheet_name": "序时账",
            "mappings": source["总账.xlsx/序时账"],
        }]
    }
    assert resolve_sheet_mapping(normalized, "总账.xlsx", "序时账") == source["总账.xlsx/序时账"]


def test_exact_file_wins_over_sheet_only_and_default():
    mapping = {
        "confirmed_mappings": [
            {"file_name": "", "sheet_name": "序时账", "mappings": {"A": "sheet"}},
            {"file_name": "a.xlsx", "sheet_name": "序时账", "mappings": {"A": "exact"}},
        ],
        "default_mappings": {"A": "default"},
    }
    assert resolve_sheet_mapping(mapping, "a.xlsx", "序时账") == {"A": "exact"}
    assert resolve_sheet_mapping(mapping, "b.xlsx", "序时账") == {"A": "sheet"}
    assert resolve_sheet_mapping(mapping, "b.xlsx", "余额表") == {"A": "default"}


def test_direct_header_mapping_becomes_default():
    mapping = {"凭证号": "voucher_no", "日期": "voucher_date"}
    normalized = normalize_custom_mapping(mapping)
    assert normalized["default_mappings"] == mapping
    assert resolve_sheet_mapping(normalized, "任意.xlsx", "任意") == mapping


def test_canonical_mapping_is_copied_and_invalid_entries_are_ignored():
    original = {"confirmed_mappings": [None, {"file_name": "a", "sheet_name": "s", "mappings": None}]}
    normalized = normalize_custom_mapping(original)
    assert normalized == {"confirmed_mappings": [{"file_name": "a", "sheet_name": "s", "mappings": {}}]}
    assert normalized is not original


def test_application_service_normalizes_frontend_legacy_payload():
    raw = {"总账.xlsx/序时账": {"账簿类型": "company_name", "凭证字": "voucher_type"}}
    parsed = LedgerImportApplicationService.parse_custom_mapping(json.dumps(raw, ensure_ascii=False))
    assert parsed["confirmed_mappings"][0]["mappings"] == raw["总账.xlsx/序时账"]
    assert _resolve_sheet_mapping(parsed, "总账.xlsx", "序时账") == raw["总账.xlsx/序时账"]


def test_both_pipeline_files_import_shared_mapping_resolver():
    root = Path(__file__).resolve().parents[1] / "app/services"
    pipeline = (root / "ledger_import/pipeline.py").read_text(encoding="utf-8")
    smart = (root / "smart_import_engine.py").read_text(encoding="utf-8")
    assert "from app.services.ledger_import_mapping_contract import resolve_sheet_mapping" in pipeline
    assert "from app.services.ledger_import_mapping_contract import resolve_sheet_mapping" in smart
    assert "confirmed.get(sheet_key)" not in pipeline


def test_v2_mapping_entries_are_converted_for_current_pipeline():
    original = {
        "confirmed_mappings": [{
            "file_name": "总账.xlsx",
            "sheet_name": "序时账",
            "mapping_entries": [
                {"column_index": 0, "original_header": "凭证号", "canonical_header": "凭证号", "standard_field": "voucher_no"},
                {"column_index": 1, "original_header": "凭证字", "canonical_header": "凭证字", "standard_field": "voucher_type"},
            ],
        }]
    }
    normalized = normalize_custom_mapping(original)
    assert resolve_sheet_mapping(normalized, "总账.xlsx", "序时账") == {
        "凭证号": "voucher_no",
        "凭证字": "voucher_type",
    }
