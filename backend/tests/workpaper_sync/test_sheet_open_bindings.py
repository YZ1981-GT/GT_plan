"""SheetOpenBinding 生成物守卫（onlyoffice-sheet-open-via-published-artifact Phase 1）。"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "data/workpaper_sync_sheet_open_bindings.json"
GENERATOR = ROOT / "scripts/gen/generate_workpaper_sync_sheet_open_bindings.py"
MANIFEST = ROOT / "data/workpaper_sync_entry_manifest.json"

_ALLOWED_STATUS = {"pending", "ready", "migrated", "draining", "retired", "out_of_scope"}
_ALLOWED_KIND = {"exact", "provider", "whole_workbook", "ambiguous", "out_of_scope"}


@pytest.fixture(scope="module")
def projection() -> dict:
    return json.loads(OUTPUT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_generated_projection_is_current() -> None:
    proc = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        cwd=ROOT.parent,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_projection_covers_manifest_entry_ids_exactly(projection: dict, manifest: dict) -> None:
    binding_ids = [row["entry_id"] for row in projection["bindings"]]
    manifest_ids = [row["entry_id"] for row in manifest["entries"]]
    assert len(binding_ids) == len(set(binding_ids)), "binding entry_id 重复"
    assert set(binding_ids) == set(manifest_ids)
    assert not any(entry.startswith("xlsx-sheet/") for entry in binding_ids)


def test_each_binding_has_closed_status_and_real_effective_entry(
    projection: dict, manifest: dict,
) -> None:
    manifest_ids = {row["entry_id"] for row in manifest["entries"]}
    rows = projection["bindings"]
    assert rows
    for row in rows:
        assert row["status"] in _ALLOWED_STATUS
        assert row["mapping_kind"] in _ALLOWED_KIND
        assert row["effective_entry_id"] in manifest_ids
        assert row["input_digest"] == projection["input_digest"]
        assert row["binding_id"].startswith("sha256:")
        if row["status"] == "out_of_scope":
            assert row["document_type"] != "xlsx" or row["reason"]
        if row["mapping_kind"] == "exact":
            assert row["target_sheet"] and len(row["sheet_literals"]) == 1


def test_projection_does_not_claim_migration_without_reviewed_binding(projection: dict) -> None:
    """首版生成物只能表达 pending/out_of_scope，不得凭 manifest 自动伪造 ready/migrated。"""
    claimed = [
        row for row in projection["bindings"]
        if row["status"] in {"ready", "migrated", "draining", "retired"}
    ]
    assert claimed == []


def test_summary_is_recomputed_from_rows(projection: dict) -> None:
    counts: dict[str, int] = {}
    for row in projection["bindings"]:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    assert projection["summary"] == {
        "entry_count": len(projection["bindings"]),
        "status_counts": counts,
    }
