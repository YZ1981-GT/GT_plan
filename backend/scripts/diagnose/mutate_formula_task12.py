"""Mutations for formula Task 12."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FE = ROOT / "audit-platform/frontend"
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


@dataclass(frozen=True)
class Case:
    id: str
    file: Path
    anchor: str
    replacement: str
    wants: tuple[str, ...]


CASES = [
    Case(
        id="T12-M1-broad-catch-success",
        file=FE / "src/shell/formula/shellStructuredError.ts",
        anchor=(
            "  if (input.caught && input.reportedSuccess) {\n"
            "    return { ok: false, reasonCode: 'broad_catch_success_forbidden' }\n"
            "  }\n"
            "  return { ok: true, reasonCode: null }\n"
        ),
        replacement=(
            "  if (input.caught && input.reportedSuccess) {\n"
            "    return { ok: true, reasonCode: null } // mutation: allow broad catch success\n"
            "  }\n"
            "  return { ok: true, reasonCode: null }\n"
        ),
        wants=("broad_catch_success_forbidden",),
    ),
]


def run_vitest() -> tuple[int, str]:
    proc = subprocess.run(
        "npx vitest run src/shell/formula/__tests__/shellTask12.spec.ts",
        cwd=str(FE),
        capture_output=True,
        env=ENV,
        shell=True,
    )
    out = (proc.stdout or b"").decode("utf-8", errors="replace") + (
        proc.stderr or b""
    ).decode("utf-8", errors="replace")
    return proc.returncode, out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-anchors", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if args.check_anchors:
        bad = 0
        for c in CASES:
            n = c.file.read_text(encoding="utf-8").count(c.anchor)
            print(f"  [{'OK' if n == 1 else 'MISS'}] {c.id} (n={n})")
            if n != 1:
                bad += 1
        return 1 if bad else 0
    if not args.apply:
        print(__doc__)
        return 0
    rc, out = run_vitest()
    if rc != 0:
        print("baseline not green")
        print(out[-2000:].encode("ascii", errors="replace").decode("ascii"))
        return 1
    print("OK baseline")
    bad = 0
    for case in CASES:
        text = case.file.read_text(encoding="utf-8")
        if text.count(case.anchor) != 1:
            print(f"  {case.id}: ANCHOR-MISS")
            bad += 1
            continue
        bak = case.file.with_suffix(case.file.suffix + ".bak")
        shutil.copy2(case.file, bak)
        try:
            case.file.write_text(text.replace(case.anchor, case.replacement, 1), encoding="utf-8")
            rc, out = run_vitest()
            if rc == 0:
                print(f"  {case.id}: GREEN FAIL")
                bad += 1
            elif not all(w in out for w in case.wants):
                print(f"  {case.id}: WRONG-TEST")
                bad += 1
            else:
                print(f"  {case.id}: RED OK")
        finally:
            shutil.copy2(bak, case.file)
            bak.unlink(missing_ok=True)
    print(f"bad={bad}/{len(CASES)}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
