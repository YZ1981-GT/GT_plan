#!/usr/bin/env python
"""Emit C1 catalog milestone evidence (guidance Task 21).

Freezes a catalog inventory snapshot + stage accounting. Verdict is PASS only when
effective_required is fully covered by complete with pending=blocked=0.

When incomplete (expected while Task 7 unmapped content remains), verdict is FAIL
with real counters — never invent complete entries.

Usage:
  python backend/scripts/fix/emit_c1_catalog_milestone.py
  python backend/scripts/fix/emit_c1_catalog_milestone.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.guidance_inventory_snapshots import (  # noqa: E402
    SnapshotStore,
    build_catalog_snapshot,
    get_snapshot_store,
)

EVIDENCE_DIR = (
    ROOT
    / ".kiro"
    / "specs"
    / "workpaper-guidance-content-closure"
    / "evidence"
    / "C1"
)
BASIS = (
    ROOT
    / ".kiro"
    / "specs"
    / "workpaper-guidance-content-closure"
    / "basis"
    / "T21-c1-catalog-milestone.json"
)


def emit_c1(*, persist: bool = True) -> dict:
    cutoff = datetime.now(UTC)
    snap = build_catalog_snapshot(
        cutoff_at=cutoff,
        run_id=f"c1-{cutoff.strftime('%Y%m%dT%H%M%SZ')}",
    )
    store = get_snapshot_store() if persist else SnapshotStore()
    if persist:
        store.put(snap)

    acct = snap.stage_accounting
    counters = dict(acct.counters)
    pass_ = bool(acct.pass_)
    verdict = "PASS" if pass_ else "FAIL"
    reason_codes: list[str] = []
    if counters.get("pending", 0):
        reason_codes.append("pending_entries_present")
    if counters.get("blocked", 0):
        reason_codes.append("blocked_entries_present")
    if not pass_ and not reason_codes:
        reason_codes.append("effective_required_incomplete")

    payload = {
        "milestone": "C1",
        "contractVersion": "1.0",
        "producerSpec": "workpaper-guidance-content-closure",
        "producerTask": 21,
        "recordedAt": cutoff.isoformat(),
        "verdict": verdict,
        "reasonCodes": reason_codes,
        "runId": snap.run_id,
        "inventoryDigest": snap.inventory_digest,
        "cutoffAt": snap.cutoff_at,
        "inputDigests": dict(snap.input_digests),
        "stageAccounting": {
            "gross_required": counters.get("gross_required", 0),
            "effective_required": counters.get("effective_required", 0),
            "complete": counters.get("complete", 0),
            "pending": counters.get("pending", 0),
            "blocked": counters.get("blocked", 0),
            "valid_exempted": counters.get("valid_exempted", 0),
            "out_of_scope": counters.get("out_of_scope", 0),
            "pass": pass_,
        },
        "entryCount": len(snap.entries),
        "notes": [
            "C1 PASS requires effective_required == complete and pending=blocked=0",
            "FAIL here is expected until Task 7 nine-section content/publication closes unmapped sheets",
            "This freeze does not mutate historical milestones; later catalog changes need a new run",
        ],
    }
    return payload


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="print payload only")
    ap.add_argument("--no-persist", action="store_true", help="do not write snapshot store")
    args = ap.parse_args()

    payload = emit_c1(persist=not args.no_persist)
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    BASIS.parent.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_DIR / "c1_catalog_milestone.json").write_text(text, encoding="utf-8")
    (EVIDENCE_DIR / "INDEX.md").write_text(
        "\n".join(
            [
                "# C1 Catalog Milestone",
                "",
                f"**Verdict:** {payload['verdict']}",
                f"**Run:** `{payload['runId']}`",
                f"**Digest:** `{payload['inventoryDigest']}`",
                f"**Accounting:** {json.dumps(payload['stageAccounting'], ensure_ascii=False)}",
                "",
                "PASS only when Task 7 closes pending/blocked on the catalog effective denominator.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    BASIS.write_text(text, encoding="utf-8")

    if args.json:
        sys.stdout.write(text)
    else:
        acct = payload["stageAccounting"]
        print(
            f"C1 verdict={payload['verdict']} "
            f"effective={acct['effective_required']} complete={acct['complete']} "
            f"pending={acct['pending']} blocked={acct['blocked']}"
        )
        print(f"evidence={EVIDENCE_DIR / 'c1_catalog_milestone.json'}")

    # Exit 0 even on FAIL — honest freeze is success of the emitter;
    # Task 21 checkbox stays [~] until verdict=PASS.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
