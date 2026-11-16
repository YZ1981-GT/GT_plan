"""SheetOpenBindingResolver 行为守卫。"""
from __future__ import annotations

import json
from pathlib import Path

from app.services.workpaper_sync.sheet_open_bindings import SheetOpenBindingResolver


def _resolver(tmp_path: Path, rows: list[dict]) -> SheetOpenBindingResolver:
    path = tmp_path / "bindings.json"
    path.write_text(json.dumps({"schema_version": "sheet-open-binding:v1", "bindings": rows}), encoding="utf-8")
    return SheetOpenBindingResolver(path)


def _manifest(*entry_ids: str) -> dict:
    return {"entries": [{"entry_id": entry_id} for entry_id in entry_ids]}


def test_provider_binding_does_not_guess_sheet_name(tmp_path: Path) -> None:
    resolver = _resolver(tmp_path, [{
        "entry_id": "xlsx/gt-k11-asset-impairment-loss",
        "effective_entry_id": "xlsx/gt-k11-asset-impairment-loss",
        "source_wp_code": "K11",
        "document_type": "xlsx",
        "document_scope": "single_sheet",
        "mapping_kind": "provider",
        "status": "pending",
    }])
    result = resolver.resolve(
        source_wp_code="K11",
        sheet_name="任意运行时名称K11-1",
        whole_workbook=False,
        manifest=_manifest("xlsx/gt-k11-asset-impairment-loss"),
    )
    assert result.binding is None
    assert result.status == "pending"
    assert result.reason == "sheet_binding_provider_review_required"


def test_exact_binding_resolves_only_when_target_sheet_matches(tmp_path: Path) -> None:
    resolver = _resolver(tmp_path, [{
        "entry_id": "xlsx/gt-d4-operating-revenue",
        "effective_entry_id": "xlsx/gt-d4-operating-revenue",
        "source_wp_code": "D4",
        "document_type": "xlsx",
        "document_scope": "single_sheet",
        "target_sheet": "收入披露表D4-8",
        "mapping_kind": "exact",
        "status": "ready",
        "binding_id": "sha256:binding",
    }])
    manifest = _manifest("xlsx/gt-d4-operating-revenue")
    ok = resolver.resolve(source_wp_code="D4", sheet_name="收入披露表D4-8", whole_workbook=False, manifest=manifest)
    assert ok.binding is not None
    assert ok.status == "ready"
    miss = resolver.resolve(source_wp_code="D4", sheet_name="父级模板D4", whole_workbook=False, manifest=manifest)
    assert miss.binding is None
    assert miss.reason == "sheet_target_not_declared"


def test_binding_to_missing_manifest_entry_is_pending_not_room_ready(tmp_path: Path) -> None:
    resolver = _resolver(tmp_path, [{
        "entry_id": "xlsx/gt-d4-operating-revenue",
        "effective_entry_id": "xlsx/gt-d4-operating-revenue",
        "source_wp_code": "D4",
        "document_type": "xlsx",
        "document_scope": "single_sheet",
        "target_sheet": "D4-8",
        "mapping_kind": "exact",
        "status": "ready",
    }])
    result = resolver.resolve(
        source_wp_code="D4",
        sheet_name="D4-8",
        whole_workbook=False,
        manifest=_manifest("xlsx/other-entry"),
    )
    assert result.status == "pending"
    assert result.reason == "sheet_binding_entry_not_in_manifest"
    assert result.binding is not None


def test_duplicate_exact_bindings_are_ambiguous(tmp_path: Path) -> None:
    row = {
        "entry_id": "xlsx/one",
        "effective_entry_id": "xlsx/one",
        "source_wp_code": "D4",
        "document_type": "xlsx",
        "document_scope": "single_sheet",
        "target_sheet": "D4-8",
        "mapping_kind": "exact",
        "status": "ready",
    }
    resolver = _resolver(tmp_path, [row, {**row, "entry_id": "xlsx/two", "effective_entry_id": "xlsx/two"}])
    result = resolver.resolve(
        source_wp_code="D4", sheet_name="D4-8", whole_workbook=False,
        manifest=_manifest("xlsx/one", "xlsx/two"),
    )
    assert result.binding is None
    assert result.reason == "sheet_binding_ambiguous"
