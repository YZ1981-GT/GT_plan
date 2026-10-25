"""Formula Task 2 mutation: CSS class must not become a named outlet capability."""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLBAR = ROOT / "audit-platform/frontend/src/components/workpaper/GtWpToolbar.vue"
INVENTORY = (
    ROOT / "audit-platform/frontend/src/shell/formula/workpaperHostInventory.ts"
)
TELEMETRY = ROOT / "audit-platform/frontend/src/shell/formula/hostAdapterTelemetry.ts"
PYTEST_CWD = ROOT / "audit-platform/frontend"
VITEST_CMD = (
    "npx vitest run src/shell/formula/__tests__/workpaperHostInventory.spec.ts"
)
ENVPATCH = {**os.environ, "PYTHONIOENCODING": "utf-8"}


@dataclass(frozen=True)
class Case:
    id: str
    file: Path
    anchor: str
    replacement: str
    wants: tuple[str, ...]
    literal: bool = False


CASES = [
    Case(
        id="M1-remove-real-compat-slot",
        file=TOOLBAR,
        anchor=(
            '      <span\n'
            '        class="gt-wp-toolbar__compat-outlet"\n'
            '        data-toolbar-outlet="page-capabilities-compatibility"\n'
            '        data-testid="page-capabilities-compatibility"\n'
            '      >\n'
            '        <slot name="page-capabilities-compatibility" />\n'
            '      </span>\n'
        ),
        replacement="      <!-- mutation: removed real compatibility outlet -->\n",
        wants=("hasPageCapabilitiesCompatibilitySlot",),
        literal=True,
    ),
    Case(
        id="M2-allow-css-selector-as-outlet",
        file=TELEMETRY,
        anchor=(
            "  if (fact.namedOutletSlot && fact.namedOutletSlot.startsWith('.')) {\n"
            "    throw new Error(\n"
            "      'hostAdapterTelemetry: CSS class selectors are not named outlets',\n"
            "    )\n"
            "  }"
        ),
        replacement="  // mutation: CSS class selectors allowed as outlets",
        wants=("rejects CSS selector as namedOutletSlot",),
        literal=True,
    ),
    Case(
        id="M3-hardcode-supported-without-telemetry",
        file=INVENTORY,
        anchor=r"^      primary: 'unsupported',$",
        replacement="      primary: 'supported',",
        wants=("empty telemetry",),
    ),
]


def _count(text: str, pattern: str, *, literal: bool) -> int:
    if literal:
        return text.count(pattern)
    return len(re.findall(pattern, text, re.MULTILINE))


def check_anchors() -> int:
    bad = 0
    for case in CASES:
        n = _count(case.file.read_text(encoding="utf-8"), case.anchor, literal=case.literal)
        print(f"  [{'OK' if n == 1 else 'ANCHOR-MISS'}] {case.id} (n={n})")
        if n != 1:
            bad += 1
    return 1 if bad else 0


def run_vitest() -> tuple[int, str]:
    proc = subprocess.run(
        VITEST_CMD,
        cwd=str(PYTEST_CWD),
        capture_output=True,
        env=ENVPATCH,
        shell=True,
    )
    out = (proc.stdout or b"").decode("utf-8", errors="replace") + (
        proc.stderr or b""
    ).decode("utf-8", errors="replace")
    return proc.returncode, out


def apply_one(case: Case) -> str:
    text = case.file.read_text(encoding="utf-8")
    if _count(text, case.anchor, literal=case.literal) != 1:
        return f"{case.id}: ANCHOR-MISS"
    if case.literal:
        new_text = text.replace(case.anchor, case.replacement, 1)
        cnt = 1 if new_text != text else 0
    else:
        new_text, cnt = re.subn(
            case.anchor, case.replacement, text, count=1, flags=re.MULTILINE,
        )
    if cnt != 1:
        return f"{case.id}: ANCHOR-MISS"
    backup = case.file.with_suffix(case.file.suffix + ".bak")
    shutil.copy2(case.file, backup)
    try:
        case.file.write_text(new_text, encoding="utf-8")
        rc, out = run_vitest()
        if rc == 0:
            return f"{case.id}: GREEN FAIL"
        hit = [w for w in case.wants if w in out]
        if len(hit) != len(case.wants):
            return f"{case.id}: WRONG-TEST FAIL\n{out[-1500:]}"
        return f"{case.id}: RED OK -- {hit}"
    finally:
        shutil.copy2(backup, case.file)
        backup.unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-anchors", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if args.check_anchors:
        return check_anchors()
    if not args.apply:
        print(__doc__)
        return 0
    rc, out = run_vitest()
    if rc != 0:
        print("baseline not green")
        print(out[-2000:])
        return 1
    print("OK baseline green")
    bad = 0
    for case in CASES:
        result = apply_one(case)
        print(f"  {result}")
        if "RED OK" not in result:
            bad += 1
    print(f"\nbad={bad}/{len(CASES)}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
