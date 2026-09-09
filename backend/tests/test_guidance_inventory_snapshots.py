"""Task 5 — materialized catalog/runtime inventory snapshots + stage accounting."""

from __future__ import annotations

from datetime import UTC, datetime

from app.services.guidance_inventory import (
    CANONICAL_SECTION_KEYS,
    GuidanceInventoryEntry,
    RuntimeGuidanceExemption,
    build_runtime_guidance_inventory,
)
from app.services.guidance_inventory_snapshots import (
    SnapshotStore,
    build_catalog_snapshot,
    build_runtime_snapshot_from_inventory,
    compute_stage_accounting,
    evaluate_platform_guidance_health,
    get_snapshot_store,
    map_runtime_entry_bucket,
    reset_snapshot_store_for_tests,
)


def _static(code: str, *, status: str = "exact") -> GuidanceInventoryEntry:
    return GuidanceInventoryEntry(
        wp_code=code,
        path=f"/guidance/{code}.json",
        parse_status="ok",
        source_digest="a" * 64,
        exact_status=status,  # type: ignore[arg-type]
        missing_sections=() if status == "exact" else CANONICAL_SECTION_KEYS,
        reason="ok",
        source_ref_status="valid",
        source_ref_facts_digest="f" * 64,
    )


def _render(code: str, name: str) -> dict:
    return {
        "sheet_code": code,
        "sheet_name": name,
        "sheet_code_reason": "explicit_code",
        "whole_workbook": False,
        "componentType": "d-form-table",
    }


def test_stage_accounting_disjoint_and_effective_denominator():
    acct = compute_stage_accounting(
        {
            "a": "complete",
            "b": "pending",
            "c": "blocked",
            "d": "valid_exempted",
            "e": "out_of_scope",
        }
    )
    assert acct.gross_required == frozenset({"a", "b", "c", "d"})
    assert acct.effective_required == frozenset({"a", "b", "c"})
    assert "d" not in acct.effective_required
    assert "e" not in acct.gross_required
    assert acct.pass_ is False


def test_stage_accounting_pass_when_complete_covers_effective():
    acct = compute_stage_accounting({"a": "complete", "b": "valid_exempted"})
    assert acct.pass_ is True
    assert acct.effective_required == frozenset({"a"})


def test_catalog_snapshot_immutable_and_keyed():
    snap1 = build_catalog_snapshot(
        static_entries=[_static("A1"), _static("B1", status="missing")],
        template_lineage_id="L1",
        template_version_id="V1",
        cutoff_at=datetime(2026, 9, 9, tzinfo=UTC),
        run_id="run-cat-1",
    )
    assert snap1.scope == "catalog"
    assert snap1.inventory_digest
    assert snap1.stage_accounting.counters["pending"] == 1
    assert snap1.stage_accounting.counters["complete"] == 1
    snap2 = build_catalog_snapshot(
        static_entries=[_static("A1"), _static("B1", status="missing")],
        template_lineage_id="L1",
        template_version_id="V1",
        cutoff_at=datetime(2026, 9, 9, tzinfo=UTC),
        run_id="run-cat-2",
    )
    assert snap1.inventory_digest == snap2.inventory_digest
    assert all("key" in row and "template_lineage_id" in row["key"] for row in snap1.entries)


def test_runtime_snapshot_uses_runtime_keys():
    inv = build_runtime_guidance_inventory(
        parent_wp_code="D2",
        render_sheets=[_render("D2", "AR"), _render("D2-1", "Detail")],
        static_entries=[_static("D2"), _static("D2-1", status="missing")],
        exemptions=(
            RuntimeGuidanceExemption(
                kind="sheet",
                target_sheet_code="D2-1",
                target_sheet_name=None,
                inherits_from="parent",
                reason_code="deferred",
                basis_refs=("doc:1",),
                approved_by="owner",
                approved_at="2026-01-01T00:00:00+00:00",
                review_after="2099-01-01T00:00:00+00:00",
            ),
        ),
        now=datetime(2026, 9, 9, tzinfo=UTC),
        run_id="run-rt-1",
    )
    snap = build_runtime_snapshot_from_inventory(
        inv,
        organization_id="org-1",
        project_id="proj-1",
        wp_id="wp-1",
        cutoff_at=datetime(2026, 9, 9, tzinfo=UTC),
        run_id="run-rt-1",
    )
    assert snap.scope == "runtime"
    assert any(row["key"]["organization_id"] == "org-1" for row in snap.entries)


def test_snapshot_store_latest_pointer_and_addressable():
    reset_snapshot_store_for_tests()
    store = get_snapshot_store()
    a = build_catalog_snapshot(
        static_entries=[_static("A1")],
        cutoff_at=datetime(2026, 9, 9, tzinfo=UTC),
        run_id="a",
    )
    b = build_catalog_snapshot(
        static_entries=[_static("A1"), _static("B1")],
        cutoff_at=datetime(2026, 9, 9, tzinfo=UTC),
        run_id="b",
    )
    store.put(a)
    assert store.latest("catalog").inventory_digest == a.inventory_digest
    store.put(b)
    assert store.latest("catalog").inventory_digest == b.inventory_digest
    assert store.get(a.inventory_digest) is not None


def test_snapshot_store_bound_evicts_non_latest():
    store = SnapshotStore(max_entries=2)
    snaps = []
    for i in range(4):
        s = build_catalog_snapshot(
            static_entries=[_static(f"X{i}")],
            cutoff_at=datetime(2026, 9, 9, tzinfo=UTC),
            run_id=f"r{i}",
            extra_input_digests={"i": str(i)},
        )
        store.put(s)
        snaps.append(s)
    assert store.latest("catalog").inventory_digest == snaps[-1].inventory_digest
    retained = sum(1 for s in snaps if store.get(s.inventory_digest) is not None)
    assert retained <= 2


def test_platform_guidance_health_states():
    missing = evaluate_platform_guidance_health(None)
    assert missing.status == "BLOCKED"
    assert missing.c2_reevaluation_requested is True

    inv_pending = build_runtime_guidance_inventory(
        parent_wp_code="A1",
        render_sheets=[_render("A1", "program")],
        static_entries=[_static("A1", status="missing")],
        now=datetime(2026, 9, 9, tzinfo=UTC),
        run_id="health-pending",
    )
    snap_pending = build_runtime_snapshot_from_inventory(
        inv_pending,
        organization_id="o",
        project_id="p",
        wp_id="w",
        cutoff_at=datetime(2026, 9, 9, tzinfo=UTC),
    )
    health_pending = evaluate_platform_guidance_health(snap_pending)
    assert health_pending.status == "DEGRADED"
    assert health_pending.c2_reevaluation_requested is True

    inv_blocked = build_runtime_guidance_inventory(
        parent_wp_code="A1",
        render_sheets=[_render("A1", "program")],
        static_entries=[_static("A1", status="invalid")],
        now=datetime(2026, 9, 9, tzinfo=UTC),
        run_id="health-blocked",
    )
    snap_blocked = build_runtime_snapshot_from_inventory(
        inv_blocked,
        organization_id="o",
        project_id="p",
        wp_id="w",
        cutoff_at=datetime(2026, 9, 9, tzinfo=UTC),
    )
    health_blocked = evaluate_platform_guidance_health(snap_blocked)
    assert health_blocked.status == "BLOCKED"
    assert "blocked_entries_present" in health_blocked.reason_codes


def test_snapshot_store_rejects_digest_overwrite_semantics():
    """Same digest put must keep the first stored snapshot object."""
    store = SnapshotStore(max_entries=8)
    first = build_catalog_snapshot(
        static_entries=[_static("A1")],
        cutoff_at=datetime(2026, 9, 9, tzinfo=UTC),
        run_id="first",
    )
    stored = store.put(first)
    twin = build_catalog_snapshot(
        static_entries=[_static("A1")],
        cutoff_at=datetime(2026, 9, 9, tzinfo=UTC),
        run_id="twin-different-object",
    )
    assert twin.inventory_digest == first.inventory_digest
    assert twin is not first
    again = store.put(twin)
    assert again is stored
    assert again is not twin
    assert store.get(first.inventory_digest) is stored


def test_map_runtime_entry_bucket_known():
    inv = build_runtime_guidance_inventory(
        parent_wp_code="A1",
        render_sheets=[_render("A1", "program")],
        static_entries=[_static("A1")],
        now=datetime(2026, 9, 9, tzinfo=UTC),
        run_id="map-1",
    )
    entry = inv.entries[0]
    assert map_runtime_entry_bucket(entry) in (
        "complete",
        "pending",
        "blocked",
        "out_of_scope",
        "valid_exempted",
    )
