#!/usr/bin/env python
"""Guidance Task 17 — batch backend/data/contract mutation RED report.

Runs every backend ``mutate_guidance_*.py`` (excludes frontend T18 script),
records per-script RED/GREEN, writes evidence under the guidance spec basis/.

Usage:
  python backend/scripts/diagnose/run_guidance_task17_mutations.py
  python backend/scripts/diagnose/run_guidance_task17_mutations.py --check-anchors-only
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DIAG = ROOT / "backend" / "scripts" / "diagnose"
EVIDENCE = (
    ROOT
    / ".kiro"
    / "specs"
    / "workpaper-guidance-content-closure"
    / "basis"
    / "T17-backend-mutation-report.json"
)

ENV = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}

# Backend/data/contract mutators only (frontend is Task 18).
SCRIPTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("mutate_guidance_gc0_inventory_resolution_guards.py", ()),
    ("mutate_guidance_contract_inventory_guards.py", ()),
    ("mutate_guidance_source_ref_wiring_guards.py", ()),
    ("mutate_guidance_resolution_guards.py", ()),
    ("mutate_guidance_resolution_task8_guards.py", ()),
    ("mutate_guidance_gid_guards.py", ("--apply",)),
    ("mutate_guidance_publication_guards.py", ()),
    ("mutate_guidance_supplement_completion_guards.py", ()),
    ("mutate_guidance_api_task9_guards.py", ()),
    ("mutate_guidance_handoff_consumer_guards.py", ()),
    ("mutate_guidance_task5_snapshots.py", ()),
)


def _run(script: str, extra: tuple[str, ...], check_anchors: bool) -> dict:
    path = DIAG / script
    if not path.is_file():
        return {"script": script, "verdict": "MISSING", "rc": 127, "tail": ""}
    args = [sys.executable, str(path)]
    if check_anchors:
        args.append("--check-anchors")
    else:
        args.extend(extra)
    proc = subprocess.run(
        args,
        cwd=str(ROOT),
        capture_output=True,
        env=ENV,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    # Anchor-only: rc 0 means OK.
    if check_anchors:
        verdict = "ANCHORS-OK" if proc.returncode == 0 else "ANCHOR-MISS"
    else:
        verdict = "RED" if proc.returncode == 0 else "GREEN-OR-FAIL"
        # Some scripts print allRed in JSON; prefer that when present.
        if '"allRed": true' in out or "allRed\": true" in out:
            verdict = "RED"
        if '"allRed": false' in out:
            verdict = "GREEN-OR-FAIL"
        if proc.returncode != 0 and "ANCHOR-MISS" in out:
            verdict = "ANCHOR-MISS"
        if proc.returncode != 0 and "baseline" in out.lower() and "green" not in out.lower():
            # baseline not green
            if "baseline not green" in out or "SKIP(基线红)" in out or "HARNESS-DIRTY" in out:
                verdict = "BASE-RED"
    return {
        "script": script,
        "verdict": verdict,
        "rc": proc.returncode,
        "tail": out[-2500:],
    }


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check-anchors-only", action="store_true")
    args = ap.parse_args()

    results = []
    for script, extra in SCRIPTS:
        print(f"== {script} ==")
        row = _run(script, extra, check_anchors=args.check_anchors_only)
        print(f"  {row['verdict']} rc={row['rc']}")
        results.append({k: v for k, v in row.items() if k != "tail"} | (
            {"tail": row["tail"]} if row["verdict"] not in {"RED", "ANCHORS-OK"} else {}
        ))

    if args.check_anchors_only:
        ok = all(r["verdict"] == "ANCHORS-OK" for r in results)
        print(f"anchors ok={ok} {sum(1 for r in results if r['verdict']=='ANCHORS-OK')}/{len(results)}")
        return 0 if ok else 1

    red_ok = all(r["verdict"] == "RED" for r in results)
    report = {
        "task": 17,
        "recordedAt": datetime.now(timezone.utc).isoformat(),
        "allRed": red_ok,
        "scripts": len(results),
        "redCount": sum(1 for r in results if r["verdict"] == "RED"),
        "results": results,
        "coverage": [
            "C0 schema/matrix/fixture",
            "identity/registry (G-ID)",
            "inventory/accounting/snapshots",
            "publication + supplement/completion",
            "resolver/provenance (task8)",
            "cache/ETag (task9)",
            "handoff/ACK visibility",
            "source_ref wiring",
        ],
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"allRed={red_ok} evidence={EVIDENCE}")
    return 0 if red_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
