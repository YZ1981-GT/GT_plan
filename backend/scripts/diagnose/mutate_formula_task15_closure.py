"""Task 15 — full inventory gate mutations must RED; finally restore bytes.

Mutations:
  - smuggle second FormulaManagerDialog mount
  - drop domain exclusion path recognition
  - force inventoryDigest null in gate payload
  - expire/break grid exemption digest
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FE = ROOT / "audit-platform/frontend"
SPEC = ROOT / ".kiro/specs/workpaper-page-formula-toolbar-closure"
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


@dataclass(frozen=True)
class Case:
    id: str
    file: Path
    anchor: str
    replacement: str
    wants: tuple[str, ...]


CASES: list[Case] = [
    Case(
        id="T15-M01-second-formula-dialog",
        file=FE / "src/views/WorkpaperEditor.vue",
        anchor="  <!-- 主内容区 + WorkpaperCapabilityShell（rail/location/capability 唯一 owner） -->\n",
        replacement=(
            "  <!-- 主内容区 + WorkpaperCapabilityShell（rail/location/capability 唯一 owner） -->\n"
            "  <FormulaManagerDialog v-if=\"false\" />\n"
            "  <!-- mutation: second FormulaManagerDialog mount on workpaper route -->\n"
        ),
        wants=("adjudicates five hosts, zero forbidden duplicates, pins inventoryDigest",),
    ),
    Case(
        id="T15-M02-null-inventory-digest",
        file=FE / "src/shell/formula/fullInventoryGate.ts",
        anchor="  const inventoryDigest = inventoryRun.digests.run\n",
        replacement="  const inventoryDigest = '' // mutation: empty digest\n",
        wants=("adjudicates five hosts, zero forbidden duplicates, pins inventoryDigest",),
    ),
    Case(
        id="T15-M03-break-grid-exemption",
        file=SPEC / "basis/T15-grid-host-exemption.json",
        anchor='"expiresAt": "2026-12-31T23:59:59Z",',
        replacement='"expiresAt": "2020-01-01T00:00:00Z",',
        wants=("adjudicates five hosts, zero forbidden duplicates, pins inventoryDigest",),
    ),
]


def run_vitest(filter_name: str) -> subprocess.CompletedProcess[str]:
    # Windows: prefer cmd /c npx so PATH resolution works under non-interactive Python.
    cmd = (
        f'npx vitest run src/shell/formula/__tests__/fullInventoryGate.spec.ts '
        f'-t "{filter_name}" --reporter=dot'
    )
    return subprocess.run(
        cmd,
        cwd=str(FE),
        env=ENV,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        shell=True,
    )


def main() -> int:
    results = []
    for case in CASES:
        original = case.file.read_text(encoding="utf-8")
        if case.anchor not in original:
            results.append({"id": case.id, "verdict": "ANCHOR-MISS"})
            continue
        mutated = original.replace(case.anchor, case.replacement, 1)
        case.file.write_text(mutated, encoding="utf-8")
        try:
            # Prefer the first want filter for the RED check.
            filt = case.wants[0]
            proc = run_vitest(filt)
            out = (proc.stdout or "") + (proc.stderr or "")
            red = proc.returncode != 0
            results.append(
                {
                    "id": case.id,
                    "verdict": "RED" if red else "GREEN",
                    "returncode": proc.returncode,
                    "tail": out[-800:],
                }
            )
        finally:
            case.file.write_text(original, encoding="utf-8")

    report = {
        "task": 15,
        "recordedAt": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
        "cases": results,
        "allRed": all(r.get("verdict") == "RED" for r in results),
    }
    out_path = SPEC / "basis/T15-mutation-report.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
    # ASCII-only console on Windows GBK consoles.
    print(json.dumps({
        "allRed": report["allRed"],
        "cases": [{"id": c["id"], "verdict": c["verdict"]} for c in results],
    }, indent=2))
    return 0 if report["allRed"] else 1


if __name__ == "__main__":
    sys.exit(main())
