"""Task 5 — inventory snapshot mutations must RED; finally restore bytes."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BE = ROOT / "backend"
MOD = BE / "app/services/guidance_inventory_snapshots.py"
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


@dataclass(frozen=True)
class Case:
    id: str
    anchor: str
    replacement: str
    wants: str


CASES = [
    Case(
        id="T5-M01-effective-includes-exempted",
        anchor="    effective_required = frozenset(gross_required - valid_exempted)\n",
        replacement="    effective_required = frozenset(gross_required)  # mutation: keep exempted\n",
        wants="test_stage_accounting_pass_when_complete_covers_effective",
    ),
    Case(
        id="T5-M02-overwrite-immutable-snapshot",
        anchor=(
            "            existing = self._by_digest.get(snapshot.inventory_digest)\n"
            "            if existing is not None:\n"
            "                self._latest[snapshot.scope] = snapshot.inventory_digest\n"
            "                return existing\n"
        ),
        replacement=(
            "            existing = self._by_digest.get(snapshot.inventory_digest)\n"
            "            if existing is not None:\n"
            "                self._by_digest[snapshot.inventory_digest] = snapshot  # mutation overwrite\n"
            "                self._latest[snapshot.scope] = snapshot.inventory_digest\n"
            "                return snapshot\n"
        ),
        wants="test_snapshot_store_rejects_digest_overwrite_semantics",
    ),
    Case(
        id="T5-M03-health-ignores-blocked",
        anchor="    if acct.blocked:\n        return PlatformGuidanceHealth(\n            status=\"BLOCKED\",\n",
        replacement=(
            "    if False and acct.blocked:  # mutation: ignore blocked\n"
            "        return PlatformGuidanceHealth(\n"
            "            status=\"BLOCKED\",\n"
        ),
        wants="test_platform_guidance_health_states",
    ),
]


def run_pytest(node_id: str) -> subprocess.CompletedProcess[str]:
    cmd = f'python -m pytest tests/test_guidance_inventory_snapshots.py::{node_id} -q'
    return subprocess.run(
        cmd,
        cwd=str(BE),
        env=ENV,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        shell=True,
    )


def main() -> int:
    original = MOD.read_text(encoding="utf-8")
    results = []
    try:
        for case in CASES:
            if case.anchor not in original:
                results.append({"id": case.id, "verdict": "ANCHOR-MISS"})
                continue
            MOD.write_text(original.replace(case.anchor, case.replacement, 1), encoding="utf-8")
            proc = run_pytest(case.wants)
            red = proc.returncode != 0
            results.append({"id": case.id, "verdict": "RED" if red else "GREEN", "rc": proc.returncode})
            MOD.write_text(original, encoding="utf-8")
    finally:
        MOD.write_text(original, encoding="utf-8")

    report = {
        "task": 5,
        "recordedAt": datetime.now(timezone.utc).isoformat(),
        "cases": results,
        "allRed": all(r.get("verdict") == "RED" for r in results),
    }
    out = ROOT / ".kiro/specs/workpaper-guidance-content-closure/basis"
    out.mkdir(parents=True, exist_ok=True)
    (out / "T05-mutation-report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8"
    )
    print(json.dumps({"allRed": report["allRed"], "cases": results}, indent=2))
    return 0 if report["allRed"] else 1


if __name__ == "__main__":
    sys.exit(main())
