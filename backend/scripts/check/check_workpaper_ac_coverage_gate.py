"""Archival gate over the AC coverage matrix (Requirement 14.15).

spec: .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/
Wave 0 Task 8 - Requirements 1.8, 14.13, 14.15 - Property 57

The gate is expected to stay red for most of this spec's life. Requirement 14.15 makes a
dangling AC, a missing Design oracle, a missing dependency edge, single-task
self-certification or a missing evidence type an *archival* blocker, and Requirement 1.8
says the undecided count may only fall. A gate that went green before the work existed
would be the assertion-shaped version of the same defect it is meant to catch, so:

* exit 0 - no defect and nothing stale
* exit 1 - defects remain (the normal state while waves are open); every offending AC and
  every reason is named, so the count is auditable rather than a bare number
* exit 2 - the stored matrix no longer matches the spec documents, or a document cannot be
  parsed at all. Staleness outranks defect counting: a stale matrix makes any count a lie.

Usage from the repository root::

    python backend/scripts/check/check_workpaper_ac_coverage_gate.py
    python backend/scripts/check/check_workpaper_ac_coverage_gate.py --max-listed 5
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO / "backend" / "scripts" / "gen"))

from generate_workpaper_ac_coverage_matrix import (  # noqa: E402
    _MATRIX,
    CoverageMatrixError,
    generate,
    render,
)

#: Reason text per defect code. Kept next to the gate rather than in the generated file so
#: the JSON stays machine facts only.
_REASONS: dict[str, str] = {
    "dangling_ac": "no task lists this AC under _Requirements:",
    "no_oracle_family": "outside every row of design.md '## Acceptance Oracle Matrix'",
    "no_property_oracle": "no '### Property N' declares '**Validates: Requirements <ac>**'",
    "self_certified_single_task": "one single task both implements and verifies it",
    "no_dependency_edge": "several tasks cover it but none depends on another, so no task "
    "verifies work the other one did",
    "no_evidence_type": "its oracle family has no reviewed evidence class",
    "dangling_property": "no task declares it verifies this Property",
}


def _stored_text() -> str:
    """Raw bytes of the generated matrix. A seam, so the staleness branch is testable."""
    if not _MATRIX.is_file():
        raise CoverageMatrixError(f"missing generated matrix: {_MATRIX}")
    return _MATRIX.read_text(encoding="utf-8")


def _load_stored() -> dict[str, Any]:
    return json.loads(_stored_text())


def evaluate() -> tuple[int, list[str]]:
    """Return ``(exit_code, report_lines)``."""
    lines: list[str] = []
    fresh = generate()
    stored = _load_stored()
    if _stored_text() != render(fresh):
        lines.append(
            "[STALE] the stored matrix no longer matches requirements.md / design.md / tasks.md"
        )
        lines.append(f"        stored digest {stored.get('matrix_digest')}")
        lines.append(f"        source digest {fresh['matrix_digest']}")
        lines.append(
            "        run: python backend/scripts/gen/generate_workpaper_ac_coverage_matrix.py"
            " --apply"
        )
        return 2, lines

    stats = fresh["stats"]
    lines.append(
        f"[SCOPE] ac={stats['ac_count']} property={stats['property_count']} "
        f"task={stats['task_count']} oracle_family={stats['oracle_family_count']}"
    )
    lines.append(
        f"[SCOPE] clean_ac={stats['clean_ac_count']} defective_ac={stats['ac_with_defects']}"
    )

    stale = fresh["stale_references"]
    if stats["stale_reference_count"]:
        lines.append("[FAIL] cross-document references point at things that do not exist:")
        for kind, ids in sorted(stale.items()):
            if ids:
                lines.append(f"  !! {kind}: {ids}")
        return 2, lines
    if fresh["duplicate_family_coverage"]:
        lines.append(
            f"[FAIL] AC covered by more than one oracle family: "
            f"{fresh['duplicate_family_coverage']}"
        )
        return 2, lines

    by_code: dict[str, list[str]] = defaultdict(list)
    for entry in fresh["acceptance_criteria"]:
        for code in entry["defects"]:
            by_code[code].append(entry["ac_id"])
    for entry in fresh["properties"]:
        for code in entry["defects"]:
            by_code[code].append(f"Property {entry['property']}")
    unknown = sorted(set(by_code) - set(_REASONS))
    if unknown:
        lines.append(f"[FAIL] generator reported defect codes the gate cannot explain: {unknown}")
        return 2, lines
    return (1 if by_code else 0), lines + _render_defects(fresh, by_code)


def _render_defects(fresh: dict[str, Any], by_code: dict[str, list[str]]) -> list[str]:
    lines: list[str] = []
    if not by_code:
        lines.append("[OK] every AC has an oracle family, a Design oracle Property, an "
                     "implementing task, an independent verifying task with a dependency edge, "
                     "and a reviewed evidence type")
        return lines
    lines.append("[RED] Requirement 14.15 blockers remain:")
    for code in sorted(by_code):
        ids = by_code[code]
        lines.append(f"  !! {code} x{len(ids)} - {_REASONS[code]}")
        lines.append(f"     {', '.join(ids)}")
    lines.append("")
    lines.append("[WAVE] defects by the earliest wave that touches the AC "
                 "(wave 0 items are live, later waves are plan gaps to close before that wave):")
    for wave, counts in fresh["stats"]["defects_by_earliest_wave"].items():
        lines.append(f"  wave {wave}: {counts}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-listed",
        type=int,
        default=0,
        help="truncate each defect's id list to N entries (0 = list everything)",
    )
    args = parser.parse_args(argv)
    code, lines = evaluate()
    for line in lines:
        if args.max_listed > 0 and line.startswith("     "):
            ids = [chunk.strip() for chunk in line.strip().split(",")]
            if len(ids) > args.max_listed:
                shown = ", ".join(ids[: args.max_listed])
                line = f"     {shown}, ... (+{len(ids) - args.max_listed} more)"
        print(line)
    return code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CoverageMatrixError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
