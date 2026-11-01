"""参数化 cycle current projection 守卫。"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[3]
GENERATOR = ROOT / "backend/scripts/gen/generate_workpaper_sync_cycle_projection.py"
OUTPUT = ROOT / "backend/data/workpaper_sync_cycle_current_projection.json"
MANIFEST = ROOT / "backend/data/workpaper_sync_entry_manifest.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("workpaper_sync_cycle_projection_gen", GENERATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_projection_is_current_and_idempotent() -> None:
    generator = load_generator()
    first = generator.build_projection()
    second = generator.build_projection()
    assert first == second
    assert OUTPUT.read_text(encoding="utf-8") == generator.render(first)


def test_each_independent_entry_is_owned_exactly_once() -> None:
    projection = load(OUTPUT)
    manifest = load(MANIFEST)
    projected = [
        row["entry_id"]
        for group in projection["groups"].values()
        for row in group["entries"]
    ]
    expected = [
        row["entry_id"] for row in manifest["entries"] if row["independent_entry"]
    ]
    assert len(projected) == len(set(projected))
    assert sorted(projected) == sorted(expected)
    assert projection["independent_entry_count"] == len(expected)


def test_group_counts_and_digests_are_derived() -> None:
    generator = load_generator()
    projection = load(OUTPUT)
    for key, group in projection["groups"].items():
        rows = group["entries"]
        assert group["counts"]["entries"] == len(rows), key
        assert group["counts"]["pending"] == sum(
            row["capability"] is None for row in rows
        ), key
        without_digest = dict(group)
        actual_digest = without_digest.pop("projection_digest")
        assert actual_digest == generator.canonical_digest(without_digest), key


def test_every_historical_slice_points_to_the_current_projection() -> None:
    generator = load_generator()
    for path in generator.SLICE_PATHS.values():
        document = load(path)
        assert document["current_projection_schema_version"] == generator.SCHEMA
        assert document["current_projection_ref"] == generator.OUTPUT_REF


def test_current_projection_preserves_pending_semantics() -> None:
    projection = load(OUTPUT)
    rows = [row for group in projection["groups"].values() for row in group["entries"]]
    pending = [row for row in rows if row["capability"] is None]
    assert pending
    for row in pending:
        assert row["adjudication_state"] == "pending"
        assert row["capability_target"]
        assert row["capability_target_blocked_by"]
        assert row["adapter_id"] is None


def test_d2_supplemental_entry_is_in_d_cycle() -> None:
    projection = load(OUTPUT)
    d_ids = {row["entry_id"] for row in projection["groups"]["d"]["entries"]}
    assert "xlsx/gt-d2-inspection" in d_ids
