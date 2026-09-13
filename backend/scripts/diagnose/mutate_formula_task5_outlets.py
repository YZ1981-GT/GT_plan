"""Formula Task 5 mutations: primary priority + collision fail-closed."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ARB = ROOT / "audit-platform/frontend/src/shell/formula/toolbarOutletArbiter.ts"
VITEST_CWD = ROOT / "audit-platform/frontend"
ENVPATCH = {**os.environ, "PYTHONIOENCODING": "utf-8"}
VITEST_CMD = (
    "npx vitest run src/shell/formula/__tests__/toolbarOutletArbiter.spec.ts"
)


@dataclass(frozen=True)
class MutCase:
    id: str
    file: Path
    anchor: str
    replacement: str
    wants: tuple[str, ...]


CASES = [
    MutCase(
        id="M1-compat-steals-before-primary-unavailable",
        file=ARB,
        anchor=(
            "    if (compat && !this.primaryUnavailable) {\n"
            "      // Fallback must not steal while primary is still pending/available.\n"
            "      this.placement = { status: 'pending', ownerEpoch: this.ownerEpoch }\n"
            "      return\n"
            "    }\n"
        ),
        replacement=(
            "    if (compat && !this.primaryUnavailable) {\n"
            "      // mutation: allow compat to steal\n"
            "      this.placement = { status: 'registered', selected: compat }\n"
            "      return\n"
            "    }\n"
        ),
        wants=("primary wins; compatibility waits",),
    ),
    MutCase(
        id="M2-allow-duplicate-kind",
        file=ARB,
        anchor=(
            "    if (existing && existing.hostInstanceId !== input.hostInstanceId) {\n"
            "      this.placement = {\n"
            "        status: 'blocked',\n"
            "        ownerEpoch: this.ownerEpoch,\n"
            "        reasonCode: 'duplicate_kind_collision',\n"
            "        detail: `kind=${input.kind} already registered by ${existing.hostInstanceId}`,\n"
            "      }\n"
            "      return { ok: false, reasonCode: 'duplicate_kind_collision' }\n"
            "    }\n"
        ),
        replacement="    // mutation: duplicate kind allowed\n",
        wants=("rejects duplicate kind, cross-epoch, and CSS-class-only outlet",),
    ),
    MutCase(
        id="M3-allow-css-class-outlet",
        file=ARB,
        anchor=(
            "    if (input.outletElement.classList?.contains('gt-wp-toolbar__right')\n"
            "      && !input.outletElement.hasAttribute('data-toolbar-outlet')) {\n"
            "      return { ok: false, reasonCode: 'css_class_not_outlet' }\n"
            "    }\n"
        ),
        replacement="    // mutation: CSS class accepted as outlet\n",
        wants=("rejects duplicate kind, cross-epoch, and CSS-class-only outlet",),
    ),
]


def check_anchors() -> int:
    bad = 0
    for case in CASES:
        n = case.file.read_text(encoding="utf-8").count(case.anchor)
        print(f"  [{'OK' if n == 1 else 'ANCHOR-MISS'}] {case.id} (n={n})")
        if n != 1:
            bad += 1
    return 1 if bad else 0


def run_vitest() -> tuple[int, str]:
    proc = subprocess.run(
        VITEST_CMD, cwd=str(VITEST_CWD), capture_output=True, env=ENVPATCH, shell=True,
    )
    out = (proc.stdout or b"").decode("utf-8", errors="replace") + (
        proc.stderr or b""
    ).decode("utf-8", errors="replace")
    return proc.returncode, out


def apply_one(case: MutCase) -> str:
    text = case.file.read_text(encoding="utf-8")
    if text.count(case.anchor) != 1:
        return f"{case.id}: ANCHOR-MISS"
    new_text = text.replace(case.anchor, case.replacement, 1)
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
        safe = out[-2000:].encode("ascii", errors="replace").decode("ascii")
        print(safe)
        return 1
    print("OK baseline green")
    bad = 0
    for case in CASES:
        result = apply_one(case)
        print(f"  {result}".encode("ascii", errors="replace").decode("ascii"))
        if "RED OK" not in result:
            bad += 1
    print(f"\nbad={bad}/{len(CASES)}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
