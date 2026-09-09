#!/usr/bin/env python
"""Guidance Task 22 — consumer verdict over custom X-HANDOFF-CONFORMANCE.

Does not modify custom runtime. Records BLOCKED/PARTIAL/PASS against the
external milestone file only.

Usage:
  python backend/scripts/ops/emit_g22_x_handoff_consumer_verdict.py
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
X_PATH = (
    ROOT
    / ".kiro"
    / "specs"
    / "custom-workpaper-template-ingestion-and-sync-closure"
    / "evidence"
    / "X-HANDOFF-CONFORMANCE.json"
)
OUT = (
    ROOT
    / ".kiro"
    / "specs"
    / "workpaper-guidance-content-closure"
    / "basis"
    / "T22-x-handoff-consumer-verdict.json"
)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass

    if not X_PATH.is_file():
        payload = {
            "task": 22,
            "recordedAt": datetime.now(UTC).isoformat(),
            "verdict": "BLOCKED",
            "reasonCodes": ["x_handoff_conformance_missing"],
            "xPath": str(X_PATH.relative_to(ROOT)).replace("\\", "/"),
        }
    else:
        x = json.loads(X_PATH.read_text(encoding="utf-8"))
        x_verdict = str(x.get("verdict") or "").upper()
        if x_verdict == "PASS":
            verdict = "PASS"
            reasons = []
        elif x_verdict == "PARTIAL":
            verdict = "BLOCKED"
            reasons = ["x_handoff_conformance_partial", "sync_gates_incomplete"]
        else:
            verdict = "BLOCKED"
            reasons = [f"x_handoff_verdict_{x_verdict or 'unknown'}"]
        payload = {
            "task": 22,
            "recordedAt": datetime.now(UTC).isoformat(),
            "verdict": verdict,
            "reasonCodes": reasons,
            "xPath": str(X_PATH.relative_to(ROOT)).replace("\\", "/"),
            "xMilestone": x.get("milestone"),
            "xVerdict": x.get("verdict"),
            "xNotes": x.get("notes") or [],
            "consumerPolicy": "guidance_does_not_modify_custom_runtime",
            "projectionModesRequired": [
                "candidate",
                "finalized",
                "confirmed_stale_rollback",
            ],
            "notes": [
                "on_missing=BLOCKED until custom Task 19 publishes PASS X-HANDOFF-CONFORMANCE",
                "G-HANDOFF-CONSUMER (guidance T16) and F-SHELL are available; custom SYNC still blocks",
            ],
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"T22 verdict={payload['verdict']} reasons={payload.get('reasonCodes')}")
    print(f"evidence={OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
