"""Blocking closure guard for HTML/OnlyOffice workpaper synchronization.

Default execution exits non-zero while any migration debt remains. `--expect-open-debt` is
only for the Wave 0 characterization test: it succeeds when the baseline is structurally
valid *and* still red, preventing current debt from being converted into an allowlist.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
_MANIFEST_PATH = _BACKEND / "data" / "workpaper_sync_entry_manifest.json"
_BASELINE_PATH = _BACKEND / "data" / "workpaper_sync_legacy_baseline.json"

#: Registry-derived closure facts (Task 13). Kept as an explicit tuple so the wiring
#: cannot silently disappear: `test_task13_contract_registry.py` asserts that every
#: key here is produced by `build_registry_facts()` and consumed by `main()`.
REGISTRY_ISSUE_KEYS: tuple[str, ...] = (
    "registry_missing_entry_profile",
    # RG-15/16/17: the source-backed profile of a real entry contradicts its reviewed
    # capability, the descriptor mode the host actually offers, or the room facts probed
    # from the live doc_key provider. Without this key the three rules would only ever run
    # on hand-built fixtures (there are zero registered adapters), i.e. dead code.
    "registry_profile_drift",
    "registry_bidirectional_without_registered_adapter",
    "registry_fake_bidirectional",
    "registry_stale_adapter",
    "registry_contract_file_without_adapter",
)


class ClosureGuardError(RuntimeError):
    """The generated inputs are stale or structurally invalid."""


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ClosureGuardError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ClosureGuardError(f"JSON root must be an object: {path}")
    return value


def build_registry_facts(manifest: dict[str, Any]) -> dict[str, list[str]]:
    """Ask the fail-closed adapter registry what is still missing (Task 13).

    This is the registry's production consumer: Requirement 1.4/1.8 requires the
    un-adjudicated / un-registered / fake-bidirectional counts to be visible and
    blocking. Import failures are **fail closed** (raise) - a swallowed import would
    silently drop every registry fact and turn the gate green for the wrong reason.
    """
    if str(_BACKEND) not in sys.path:
        sys.path.insert(0, str(_BACKEND))
    os.environ.setdefault("DB_DISABLE_SSL", "True")
    try:
        from app.services.workpaper_sync.adapters.registry import (
            ObservedEntryFacts,
            WorkpaperSyncAdapterRegistry,
            build_production_registry,
        )
        from app.services.workpaper_sync.contracts import available_contract_ids
        from app.services.workpaper_sync.entry_source_facts import (
            observe_descriptor_facts,
            observe_room_facts,
        )
    except Exception as exc:  # noqa: BLE001 - re-raised as a closure failure below
        raise ClosureGuardError(
            f"cannot import the fail-closed adapter registry: {type(exc).__name__}: {exc}"
        ) from exc

    def observer(entry: dict[str, Any]) -> Any:
        """Live descriptor/room facts for RG-16/17.

        Deliberately observed from source + a real doc_key probe, never read back from the
        manifest: comparing the manifest against itself would make both rules pass by
        construction and could never detect a doc_key implementation drift.
        """
        return ObservedEntryFacts(
            descriptor=observe_descriptor_facts(entry), room=observe_room_facts(entry)
        )

    production = build_production_registry()
    registry = WorkpaperSyncAdapterRegistry(manifest=manifest)
    for reg in production.registrations():
        registry.register(reg)
    try:
        report = registry.build_report(
            contract_ids=available_contract_ids(), facts_observer=observer
        )
    except Exception as exc:  # noqa: BLE001 - fact collection failure must fail closed
        raise ClosureGuardError(
            f"cannot observe source-backed entry facts: {type(exc).__name__}: {exc}"
        ) from exc
    return {
        "registry_missing_entry_profile": list(report.missing_profile),
        "registry_profile_drift": list(report.profile_drift),
        "registry_bidirectional_without_registered_adapter": list(
            report.bidirectional_without_adapter
        ),
        "registry_fake_bidirectional": list(report.fake_bidirectional),
        "registry_stale_adapter": list(report.stale_adapters),
        "registry_contract_file_without_adapter": list(report.contract_files_without_adapter),
    }


def evaluate_closure(
    manifest: dict[str, Any],
    baseline: dict[str, Any],
    registry_facts: dict[str, list[str]] | None = None,
) -> dict[str, list[str]]:
    if baseline.get("manifest_digest") != manifest.get("manifest_digest"):
        raise ClosureGuardError("legacy characterization is stale for the current manifest")
    manifest_entries = manifest.get("entries") or []
    baseline_entries = baseline.get("entries") or []
    manifest_by_id = {entry.get("entry_id"): entry for entry in manifest_entries}
    baseline_by_id = {entry.get("entry_id"): entry for entry in baseline_entries}
    if not manifest_by_id or set(manifest_by_id) != set(baseline_by_id):
        raise ClosureGuardError("manifest and legacy characterization entry sets differ")

    issues: dict[str, list[str]] = {
        "unadjudicated": [],
        "legacy_fake_bidirectional": [],
        "bidirectional_without_adapter": [],
        "bidirectional_without_contract_evidence": [],
        "bidirectional_without_browser_evidence": [],
        "single_mode_switch_visible": [],
        "missing_forcesave_command": [],
        "missing_durable_callback_ack": [],
        "unreachable": [],
    }
    for entry_id, entry in manifest_by_id.items():
        legacy = baseline_by_id[entry_id]
        if entry.get("capability") == "unreachable":
            issues["unreachable"].append(entry_id)
            continue
        if not entry.get("independent_entry"):
            continue
        if entry.get("html_store") == "unresolved":
            issues["unadjudicated"].append(entry_id)
        if entry.get("migration_state") == "legacy_fake_bidirectional":
            issues["legacy_fake_bidirectional"].append(entry_id)
        if entry.get("capability") == "bidirectional":
            if not entry.get("adapter_id"):
                issues["bidirectional_without_adapter"].append(entry_id)
            evidence = entry.get("evidence") or {}
            if not evidence.get("contract_test"):
                issues["bidirectional_without_contract_evidence"].append(entry_id)
            if not evidence.get("browser_case"):
                issues["bidirectional_without_browser_evidence"].append(entry_id)
        if legacy["flags"].get("single_mode_switch_visible"):
            issues["single_mode_switch_visible"].append(entry_id)
        if legacy["flags"].get("no_forcesave_command"):
            issues["missing_forcesave_command"].append(entry_id)
        if legacy["flags"].get("no_durable_forcesave_ack"):
            issues["missing_durable_callback_ack"].append(entry_id)

    for key in REGISTRY_ISSUE_KEYS:
        issues[key] = list((registry_facts or {}).get(key) or [])
    unknown = sorted(set(registry_facts or {}) - set(REGISTRY_ISSUE_KEYS))
    if unknown:
        raise ClosureGuardError(
            f"unregistered registry closure facts: {unknown} - add them to "
            "REGISTRY_ISSUE_KEYS so they participate in the blocking total"
        )

    return {name: sorted(values) for name, values in issues.items()}


def _print_report(issues: dict[str, list[str]]) -> None:
    print("Workpaper HTML/OnlyOffice closure report")
    for name, entry_ids in issues.items():
        sample = ", ".join(entry_ids[:5])
        suffix = "" if len(entry_ids) <= 5 else f" ... +{len(entry_ids) - 5}"
        print(f"  {name}: {len(entry_ids)}{f' [{sample}{suffix}]' if sample else ''}")
    print(f"  total blocking facts: {sum(len(values) for values in issues.values())}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--expect-open-debt",
        action="store_true",
        help="Wave 0 only: require a structurally valid but still-red closure baseline",
    )
    parser.add_argument("--json", action="store_true", help="print the issue map as JSON")
    args = parser.parse_args(argv)

    try:
        manifest = _load(_MANIFEST_PATH)
        baseline = _load(_BASELINE_PATH)
        issues = evaluate_closure(manifest, baseline, build_registry_facts(manifest))
    except ClosureGuardError as exc:
        print(f"[FAIL] {exc}")
        return 2

    if args.json:
        print(json.dumps(issues, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_report(issues)
    has_debt = any(issues.values())
    if args.expect_open_debt:
        if not has_debt:
            print("[FAIL] expected an open Wave 0 debt baseline, but closure is already green")
            return 3
        print("[OK] open debt is explicit; default closure command remains blocking")
        return 0
    if has_debt:
        print("[BLOCKED] workpaper sync closure is not complete")
        return 1
    print("[OK] workpaper sync closure complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
