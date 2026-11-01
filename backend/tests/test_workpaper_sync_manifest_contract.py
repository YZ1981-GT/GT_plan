"""Contract guards for the generated workpaper sync entry manifest.

Validates workpaper-html-onlyoffice-bidirectional-writeback-closure Properties 1-3.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

_REPO = Path(__file__).resolve().parents[2]
_GENERATOR_PATH = _REPO / "backend" / "scripts" / "gen" / "generate_workpaper_sync_manifest.py"
_OVERLAY_PATH = _REPO / "backend" / "data" / "workpaper_sync_entry_overlay.json"
_MANIFEST_PATH = _REPO / "backend" / "data" / "workpaper_sync_entry_manifest.json"
_FRONTEND_PATH = (
    _REPO
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "sync"
    / "workpaperSyncManifest.generated.ts"
)
_CAPABILITIES = {"bidirectional", "single_html", "single_onlyoffice", "unreachable"}
_REQUIRED_FIELDS = {
    "entry_id",
    "effective_entry_id",
    "host_path",
    "mounts",
    "independent_entry",
    "parent_entry_id",
    "wp_match",
    "document_type",
    "html_store",
    "html_counterpart_verdict",
    "html_counterpart_source_refs",
    "adjudication_state",
    "canonical_resolver",
    "adapter_id",
    "capability",
    "migration_state",
    "evidence",
    # Requirement 1.2 (Task 73 closed the Task 1 debt): the three source-backed profile
    # fields plus their provenance are part of the entry schema, not an optional extra.
    "editability",
    "room_model",
    "scenario_profile",
    "profile_source",
}


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("workpaper_sync_manifest_generator", _GENERATOR_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generated() -> tuple[ModuleType, dict, dict, dict]:
    module = _load_generator()
    discovery = module.discover_source()
    overlay = json.loads(_OVERLAY_PATH.read_text(encoding="utf-8"))
    expected = module.build_manifest(discovery, overlay)
    on_disk = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    return module, discovery, expected, on_disk


def test_manifest_mount_set_equals_ast_source(generated: tuple[ModuleType, dict, dict, dict]) -> None:
    """Every physical production mount is represented exactly once, in both directions."""
    _, discovery, _, manifest = generated
    source_ids = {mount["mountId"] for mount in discovery["mounts"]}
    manifest_mounts = [
        mount
        for entry in manifest["entries"]
        for mount in entry["mounts"]
        if mount["sourceKind"] == "template_ast"
    ]
    manifest_ids = {mount["mountId"] for mount in manifest_mounts}

    assert source_ids
    assert len(manifest_mounts) == len(manifest_ids), "one source mount was counted more than once"
    assert manifest_ids == source_ids
    assert manifest["stats"]["mount_count"] == len(source_ids)
    assert manifest["stats"]["host_count"] == len(
        {mount["file"] for mount in discovery["mounts"]}
    )


def test_manifest_and_frontend_projection_are_current(
    generated: tuple[ModuleType, dict, dict, dict],
) -> None:
    module, _, expected, on_disk = generated
    assert on_disk == expected
    assert _MANIFEST_PATH.read_text(encoding="utf-8") == module.render_manifest(expected)
    assert _FRONTEND_PATH.read_text(encoding="utf-8") == module.render_frontend(expected)


def test_capability_and_entry_schema_are_closed(
    generated: tuple[ModuleType, dict, dict, dict],
) -> None:
    _, _, _, manifest = generated
    entries = manifest["entries"]
    ids = [entry["entry_id"] for entry in entries]
    assert len(ids) == len(set(ids))
    assert all(_REQUIRED_FIELDS <= entry.keys() for entry in entries)
    assert {
        entry["capability"] for entry in entries if entry["capability"] is not None
    } <= _CAPABILITIES
    assert all(entry["document_type"] in {"xlsx", "docx"} for entry in entries)
    assert all(entry["evidence"].get("review_status") for entry in entries)
    assert all(entry["wp_match"].get("source_host") == entry["host_path"] for entry in entries)

    pending = [
        entry
        for entry in entries
        if entry["independent_entry"] and entry["capability"] is None
    ]
    assert pending, "当前迁移期必须有诚实 pending 分母；空集合会让反例门空跑"
    assert manifest["stats"]["unadjudicated_count"] == len(pending)
    for entry in pending:
        assert entry["adjudication_state"] == "pending"
        assert entry["capability_verdict_stage"]
        assert entry["capability_target"] in _CAPABILITIES
        assert entry["capability_target_blocked_by"]
        assert entry["adapter_id"] is None

    assert all(
        not entry["independent_entry"]
        or entry["capability"] != "bidirectional"
        or entry["adapter_id"]
        for entry in entries
    )
    assert all(
        entry["capability"] != "single_onlyoffice"
        or entry["html_counterpart_verdict"] == "none"
        for entry in entries
    )


def test_parent_duplicates_reference_one_independent_entry(
    generated: tuple[ModuleType, dict, dict, dict],
) -> None:
    _, _, _, manifest = generated
    by_id = {entry["entry_id"]: entry for entry in manifest["entries"]}
    duplicates = [entry for entry in manifest["entries"] if entry["parent_entry_id"]]

    assert duplicates
    assert manifest["stats"]["parent_duplicate_count"] == len(duplicates)
    for duplicate in duplicates:
        parent = by_id[duplicate["parent_entry_id"]]
        assert duplicate["independent_entry"] is False
        assert duplicate["adapter_id"] is None
        assert duplicate["effective_entry_id"] == parent["entry_id"]
        assert duplicate["capability"] == parent["capability"]
        assert duplicate["adjudication_state"] == "inherited"
        assert parent["independent_entry"] is True
        assert parent["document_type"] == duplicate["document_type"]
        assert parent["parent_entry_id"] is None


def test_unreachable_stub_is_explicit_and_not_counted_as_independent(
    generated: tuple[ModuleType, dict, dict, dict],
) -> None:
    _, _, _, manifest = generated
    unreachable = [entry for entry in manifest["entries"] if entry["capability"] == "unreachable"]
    assert unreachable
    assert manifest["stats"]["unreachable_count"] == len(unreachable)
    assert all(entry["independent_entry"] is False for entry in unreachable)
    assert all(entry["migration_state"] == "unreachable_pending_delete" for entry in unreachable)
    assert all(entry["evidence"].get("unreachable_reason") for entry in unreachable)


def test_unreviewed_source_digest_fails_closed(
    generated: tuple[ModuleType, dict, dict, dict],
) -> None:
    module, discovery, _, _ = generated
    changed = copy.deepcopy(discovery)
    changed["sourceDigest"] = "0" * 64
    overlay = json.loads(_OVERLAY_PATH.read_text(encoding="utf-8"))

    with pytest.raises(module.ManifestGenerationError, match="source mounts changed"):
        module.build_manifest(changed, overlay)


def test_reviewed_wp_code_adjudication_overrides_filename_heuristics(
    generated: tuple[ModuleType, dict, dict, dict],
) -> None:
    _, _, _, manifest = generated
    by_id = {entry["entry_id"]: entry for entry in manifest["entries"]}
    e1 = by_id["xlsx/gt-e1-monetary-fund"]
    assert e1["wp_match"]["wp_code_patterns"] == ["E1"]
    assert e1["wp_match"]["wp_code_adjudication_source"].endswith(
        "workpaper_sync_entry_wp_code_adjudication.json"
    )
    assert manifest["wp_code_adjudication_digest"]
