"""Blocking unified-revision gate for every workpaper content writer and resolver.

Reads the generated inventory (`backend/data/workpaper_writer_inventory.json`) and exits
non-zero while any migration debt remains. The gate is intentionally red during Wave 0:
`ContentMutationService` does not exist yet, so every production content writer still owns
its own commit and its own `_version`/`file_version` counter.

Two guarantees keep this from degrading into an allowlist:

1. **Source digest fail-closed.** The gate re-derives the inventory from the AST on every
   run and refuses to evaluate a stale file. Editing production source without
   regenerating the inventory is a failure, not a pass.
2. **No exemption column.** A reviewed domain adjudication answers "which lane is this
   writer in", never "is this writer allowed to bypass". `bypasses_unified_commit` is
   derived from source, so an adjudicated writer stays red until it actually routes
   through the unified commit boundary.

`--expect-open-debt` is for the Wave 0 characterization test only: it succeeds when the
inventory is structurally valid *and* still red, which is what prevents current debt from
being silently converted into a baseline.

Validates: Property 4, Property 61
Requirements: 2.1, 2.2, 2.12, 9.11, 13.4
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

_REPO = Path(__file__).resolve().parents[3]
_INVENTORY_PATH = _REPO / "backend" / "data" / "workpaper_writer_inventory.json"
_OVERLAY_PATH = _REPO / "backend" / "data" / "workpaper_writer_domain_overlay.json"
_GENERATOR_PATH = (
    _REPO / "backend" / "scripts" / "gen" / "generate_workpaper_writer_inventory.py"
)

#: Domains Task 3 requires the inventory to cover. A domain that loses its last row means
#: the discovery predicate silently stopped seeing a whole lane.
_REQUIRED_DOMAINS: tuple[str, ...] = (
    "html_save",
    "dedicated_router",
    "upload_import",
    "wopi",
    "oo_callback",
    "custom",
    "f2_word_sync",
    "rollback",
    "history_restore",
    "export_storage_resolver",
    "orchestrator_side_effect",
)

_WRITER_KINDS = frozenset({"writer", "writer_resolver"})
_RESOLVER_KINDS = frozenset({"resolver", "writer_resolver"})


class WriterGateError(RuntimeError):
    """The generated inventory is missing, stale or structurally invalid."""


def load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "workpaper_writer_inventory_generator", _GENERATOR_PATH
    )
    if spec is None or spec.loader is None:
        raise WriterGateError(f"cannot load inventory generator: {_GENERATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_inventory() -> dict[str, Any]:
    try:
        value = json.loads(_INVENTORY_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise WriterGateError(f"cannot load {_INVENTORY_PATH}: {exc}") from exc
    if not isinstance(value, dict):
        raise WriterGateError(f"JSON root must be an object: {_INVENTORY_PATH}")
    return value


def assert_inventory_is_current(inventory: dict[str, Any]) -> dict[str, Any]:
    """Re-derive from source and reject a stale or hand-edited inventory.

    Three independent checks, because any one of them alone is fail-open:
    self-consistency catches a row deleted from `entries` while the digest fields still
    look right, the source digest catches production source moving without regeneration,
    and the row comparison catches a digest recomputed over doctored content.
    """
    generator = load_generator()
    stored_digest = inventory.get("inventory_digest")
    recomputed = generator.recompute_inventory_digest(inventory)
    if stored_digest != recomputed:
        raise WriterGateError(
            "inventory is internally inconsistent: its stored content does not hash to "
            f"its own inventory_digest (stored {stored_digest!r}, recomputed {recomputed!r}); "
            "rows were edited or removed by hand"
        )

    rows, function_facts = generator.collect_source_facts()
    overlay = json.loads(_OVERLAY_PATH.read_text(encoding="utf-8"))
    expected = generator.build_inventory(rows, overlay, function_facts)
    if expected["source_digest"] != inventory.get("source_digest"):
        raise WriterGateError(
            "inventory source digest is stale: production source changed without "
            "regenerating backend/data/workpaper_writer_inventory.json "
            f"(on disk {inventory.get('source_digest')!r}, "
            f"from source {expected['source_digest']!r})"
        )
    if expected["entries"] != inventory.get("entries"):
        raise WriterGateError(
            "inventory rows do not match the rows re-derived from source: "
            f"on disk {len(inventory.get('entries') or [])} rows, "
            f"from source {len(expected['entries'])} rows"
        )
    if expected["retired_writers"] != inventory.get("retired_writers"):
        raise WriterGateError(
            "retired writer ledger does not match the ledger re-derived from source: "
            f"on disk {len(inventory.get('retired_writers') or [])} rows, "
            f"from source {len(expected['retired_writers'])} rows -- a retired writer's "
            "measured facts moved without regenerating the inventory"
        )
    stored_lane = inventory.get("representation_upgrade_lane")
    if expected["representation_upgrade_lane"] != stored_lane:
        raise WriterGateError(
            "representation upgrade lane does not match the lane re-derived from source: "
            f"on disk {len(stored_lane or [])} rows, "
            f"from source {len(expected['representation_upgrade_lane'])} rows -- the "
            "upgrader's version-domain facts moved without regenerating the inventory"
        )
    if expected["inventory_digest"] != stored_digest:
        raise WriterGateError(
            "inventory digest does not match the regenerated inventory: the file was "
            "hand-edited or the overlay changed without regeneration"
        )
    return expected


def evaluate_gate(inventory: dict[str, Any]) -> dict[str, list[str]]:
    """Return the blocking-fact map. Empty lists everywhere means the gate is green."""
    entries = inventory.get("entries")
    if not isinstance(entries, list) or not entries:
        raise WriterGateError("inventory entry denominator is empty")

    issues: dict[str, list[str]] = {
        "unadjudicated_writer": [],
        "unadjudicated_resolver": [],
        "bypasses_unified_commit": [],
        "writes_legacy_version_field": [],
        "owns_direct_commit": [],
        "keeps_legacy_write_path_beside_unified_commit": [],
        "after_save_still_increments_revision": [],
        "representation_upgrade_increments_business_revision": [],
        "artifact_snapshot_writer_not_verifiable": [],
        "retired_writer_not_verifiable": [],
        "multi_resolver": [],
        "non_canonical_resolver_only": [],
        "writer_without_characterization_test": [],
        "missing_required_domain": [],
    }

    seen_domains: set[str] = set()
    unified_commit_writers = 0
    for entry in entries:
        writer_id = entry.get("writer_id")
        if not writer_id:
            raise WriterGateError("inventory row has no writer_id")
        kind = entry.get("kind")
        verdicts = entry.get("verdicts") or {}
        adjudication = entry.get("adjudication") or {}
        domain = adjudication.get("domain")
        if domain:
            seen_domains.add(domain)

        is_writer = kind in _WRITER_KINDS
        is_resolver = kind in _RESOLVER_KINDS

        if adjudication.get("status") != "adjudicated":
            if is_writer:
                issues["unadjudicated_writer"].append(writer_id)
            elif is_resolver:
                issues["unadjudicated_resolver"].append(writer_id)

        if is_writer and verdicts.get("bypasses_unified_commit"):
            issues["bypasses_unified_commit"].append(writer_id)
        if is_writer and verdicts.get("writes_legacy_version_field"):
            issues["writes_legacy_version_field"].append(writer_id)
        if is_writer and verdicts.get("owns_direct_commit"):
            issues["owns_direct_commit"].append(writer_id)

        # Property 4 / Property 61: reaching the unified boundary is only half of the
        # migration. A writer that also keeps its own `_version`/`file_version`, bumps
        # `content_revision` itself, or owns a second transaction boundary produces the
        # double-revision shape Task 15 forbids -- one business application, two version
        # movements. Task 20 requires an *injected* legacy path to be reported here.
        if entry["facts"].get("unified_commit_calls"):
            unified_commit_writers += 1
            if verdicts.get("keeps_legacy_write_path_beside_unified_commit"):
                issues["keeps_legacy_write_path_beside_unified_commit"].append(writer_id)

        # An artifact-snapshot writer copies already-committed bytes into a snapshot
        # namespace, so it has no business content to route through the unified commit and
        # `bypasses_unified_commit` does not apply to it. That is a reclassification, not
        # a pass: the row takes on its own obligations here -- it must be adjudicated, it
        # must read the *unified* counter (so the snapshot name follows the counter that
        # actually moves), and it must not touch a legacy version field.
        if verdicts.get("artifact_snapshot_only"):
            version_reads = set(entry["facts"].get("version_fields_read") or [])
            legacy = {"file_version", "parsed_data._version"}
            if (
                adjudication.get("status") != "adjudicated"
                or "content_revision" not in version_reads
                or version_reads & legacy
                or verdicts.get("writes_legacy_version_field")
                or verdicts.get("writes_business_content")
            ):
                issues["artifact_snapshot_writer_not_verifiable"].append(writer_id)
        if is_writer and not verdicts.get("has_characterization_test"):
            issues["writer_without_characterization_test"].append(writer_id)
        if verdicts.get("multi_resolver"):
            issues["multi_resolver"].append(writer_id)
        if is_resolver and verdicts.get("non_canonical_resolver_only"):
            issues["non_canonical_resolver_only"].append(writer_id)

        # Requirement 13.4 / Property 4: the post-save side-effect handler must stop
        # moving any version field. It still increments `file_version` today.
        if domain == "orchestrator_side_effect" and (
            verdicts.get("writes_legacy_version_field")
            or verdicts.get("writes_unified_content_revision")
        ):
            issues["after_save_still_increments_revision"].append(writer_id)

    # A migrated writer leaves `entries`, so "no row writes a version field any more" is
    # also what a *deleted* function produces. The retired ledger is therefore evaluated
    # positively: each retirement must still point at a function that exists in source and
    # whose claimed-empty facts are really empty. Without this, every judgement about a
    # migrated writer would live in an unreachable branch.
    retired = inventory.get("retired_writers")
    if retired is None:
        raise WriterGateError(
            "inventory has no retired_writers ledger: regenerate it with the current "
            "generator, otherwise migrated writers have no positive verdict at all"
        )
    if not isinstance(retired, list):
        raise WriterGateError("inventory.retired_writers must be a list")
    for item in retired:
        writer_id = item.get("writer_id")
        if not writer_id:
            raise WriterGateError("retired_writers row has no writer_id")
        domain = item.get("domain")
        if domain:
            seen_domains.add(domain)
        if item.get("source_state") != "present_and_clean":
            issues["retired_writer_not_verifiable"].append(writer_id)
            continue
        facts = item.get("facts") or {}
        if facts.get("version_fields_written") or facts.get("sql_update_columns"):
            issues["after_save_still_increments_revision"].append(writer_id)

    # Property 4: a pure representation upgrade must not move the business content
    # revision. The upgrader is invisible in `entries`, so this criterion runs on its own
    # source-backed denominator -- and an empty denominator is refused rather than
    # reported as zero violations, because "nothing stages a candidate any more" is what a
    # broken discovery predicate produces too.
    lane = inventory.get("representation_upgrade_lane")
    if not isinstance(lane, list) or not lane:
        raise WriterGateError(
            "representation upgrade lane is empty: no function stages or registers a "
            "non-current upgrade candidate any more, so the Property 4 criterion would "
            "be evaluated over an empty denominator (a tautology). Regenerate the "
            "inventory; if the upgrader really moved, the discovery markers must move too"
        )
    for item in lane:
        function_id = item.get("function_id")
        if not function_id:
            raise WriterGateError("representation_upgrade_lane row has no function_id")
        if (
            item.get("version_fields_written")
            or item.get("revision_bump_calls")
            or item.get("sql_update_columns")
        ):
            issues["representation_upgrade_increments_business_revision"].append(function_id)

    # Same anti-tautology reasoning for the double-revision criterion: with zero writers
    # at the unified boundary it could never fire.
    if not unified_commit_writers:
        raise WriterGateError(
            "no writer reaches the unified commit boundary, so "
            "`keeps_legacy_write_path_beside_unified_commit` has an empty denominator; "
            "the migrated writers lost their `ContentMutationService` wiring or the "
            "unified-commit markers stopped matching"
        )

    missing = [domain for domain in _REQUIRED_DOMAINS if domain not in seen_domains]
    issues["missing_required_domain"].extend(missing)

    return {name: sorted(values) for name, values in issues.items()}


def _print_report(inventory: dict[str, Any], issues: dict[str, list[str]]) -> None:
    stats = inventory["stats"]
    print("Workpaper writer / resolver unified-revision gate")
    print(
        f"  rows={stats['row_count']} writers={stats['writer_count']} "
        f"resolvers={stats['resolver_count']} "
        f"retired={stats.get('retired_writer_count', 0)}"
    )
    print(f"  content stores written: {stats['by_content_store']}")
    print(f"  version fields written: {stats['version_field_write_histogram']}")
    print(
        f"  artifact-snapshot-only writers: {stats['artifact_snapshot_only_count']}"
        f" | representation upgrade lane: {len(inventory['representation_upgrade_lane'])}"
    )
    for name, values in issues.items():
        sample = ", ".join(values[:4])
        suffix = "" if len(values) <= 4 else f" ... +{len(values) - 4}"
        detail = f" [{sample}{suffix}]" if sample else ""
        print(f"  {name}: {len(values)}{detail}")
    print(f"  total blocking facts: {sum(len(values) for values in issues.values())}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--expect-open-debt",
        action="store_true",
        help="Wave 0 only: require a structurally valid but still-red gate",
    )
    parser.add_argument(
        "--skip-source-check",
        action="store_true",
        help="evaluate the stored inventory without re-deriving it from the AST",
    )
    parser.add_argument("--json", action="store_true", help="print the issue map as JSON")
    args = parser.parse_args(argv)

    try:
        inventory = load_inventory()
        if not args.skip_source_check:
            assert_inventory_is_current(inventory)
        issues = evaluate_gate(inventory)
    except WriterGateError as exc:
        print(f"[FAIL] {exc}")
        return 2

    if args.json:
        print(json.dumps(issues, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_report(inventory, issues)

    has_debt = any(issues.values())
    if args.expect_open_debt:
        if not has_debt:
            print("[FAIL] expected an open Wave 0 writer debt baseline, but the gate is green")
            return 3
        print("[OK] open writer debt is explicit; the default gate command remains blocking")
        return 0
    if has_debt:
        print("[BLOCKED] workpaper writers have not converged on a single revision domain")
        return 1
    print("[OK] every workpaper content writer is in the unified revision domain")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
