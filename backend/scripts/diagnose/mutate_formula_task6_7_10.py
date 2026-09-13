"""Mutations for formula Task 6/7/10."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FE = ROOT / "audit-platform/frontend"
BE = ROOT / "backend"
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


@dataclass(frozen=True)
class Case:
    id: str
    file: Path
    anchor: str
    replacement: str
    wants: tuple[str, ...]
    runner: str  # vitest-path | pytest


CASES = [
    Case(
        id="T6-M1-dirty-follows-latest",
        file=FE / "src/shell/formula/openFormulaManagerCommand.ts",
        anchor=(
            "  return {\n"
            "    ...session,\n"
            "    openedAtLocation: latest,\n"
            "    // pinnedLocation unchanged\n"
            "    banner: '底稿位置已变化，草稿仍固定在原位置。保存将写入固定位置并重新校验权限。',\n"
            "  }\n"
        ),
        replacement=(
            "  return {\n"
            "    ...session,\n"
            "    openedAtLocation: latest,\n"
            "    pinnedLocation: latest,\n"
            "    banner: null,\n"
            "  }\n"
        ),
        wants=("clean follows latest; dirty pins",),
        runner="vitest:src/shell/formula/__tests__/openFormulaManagerCommand.spec.ts",
    ),
    Case(
        id="T7-M1-collision-takes-first",
        file=FE / "src/shell/formula/formulaProviderRegistry.ts",
        anchor=(
            "    if (digests.length > 1) {\n"
            "      collisions.push({\n"
            "        formulaId,\n"
            "        providerIds: list.map((d) => d.provenance.providerId),\n"
            "        semanticDigests: digests,\n"
            "      })\n"
            "      continue\n"
            "    }\n"
        ),
        replacement=(
            "    if (digests.length > 1) {\n"
            "      // mutation: take first instead of blocking\n"
            "      descriptors.push(list[0])\n"
            "      continue\n"
            "    }\n"
        ),
        wants=("same id+digest merges; different digest",),
        runner="vitest:src/shell/formula/__tests__/formulaProviderRegistry.spec.ts",
    ),
    Case(
        id="T10-M1-fabricate-cell-scope",
        file=FE / "src/shell/formula/humanReviewProvider.ts",
        anchor=(
            "  const sheetScope = input.wholeWorkbook\n"
            "    ? 'whole-workbook'\n"
            "    : input.sheetUid?.trim() || 'page'\n"
        ),
        replacement=(
            "  const sheetScope = input.wholeWorkbook\n"
            "    ? 'whole-workbook'\n"
            "    : input.sheetUid?.trim() || 'cell:forged'\n"
        ),
        wants=("builds canonical key project/wp/sheetScope/anchorId",),
        runner="vitest:src/shell/formula/__tests__/humanReviewProvider.spec.ts",
    ),
    Case(
        id="T10-M2-backend-skip-collision",
        file=BE / "app/services/workpaper_capability/review_thread_keys.py",
        anchor=(
            "    for wire, legacies in target_to_legacies.items():\n"
            "        if len(legacies) > 1:\n"
            "            for row in rows:\n"
            "                if row.canonical_wire == wire:\n"
            "                    row.status = \"collision\"\n"
            "                    row.detail = f\"collision among {', '.join(legacies)}\"\n"
        ),
        replacement="    # mutation: collisions ignored\n",
        wants=("test_dry_run_collision_and_idempotent_apply",),
        runner="pytest:tests/test_review_thread_keys.py",
    ),
]


def run_case(case: Case) -> tuple[int, str]:
    if case.runner.startswith("vitest:"):
        path = case.runner.split(":", 1)[1]
        cmd = f"npx vitest run {path}"
        cwd = FE
    else:
        path = case.runner.split(":", 1)[1]
        cmd = f"python -m pytest {path} -q -p no:randomly --tb=line"
        cwd = BE
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, env=ENV, shell=True)
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
    # baselines
    for runner in sorted({c.runner for c in CASES}):
        dummy = Case("b", CASES[0].file, "x", "x", (), runner)
        rc, out = run_case(dummy)
        if rc != 0:
            print("baseline not green", runner)
            print(out[-1500:].encode("ascii", errors="replace").decode("ascii"))
            return 1
    print("OK baselines green")
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
            rc, out = run_case(case)
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
