"""Mutations for formula Task 8/9."""
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
    runner: str


CASES = [
    Case(
        id="T8-M1-audit-warn-then-commit",
        file=BE / "app/services/user_formula_v2.py",
        anchor=(
            "    try:\n"
            "        audit.append(\n"
            "            operation_id=operation_id,\n"
            "            payload={\n"
            "                \"kind\": \"user_formula_v2.batchMutate\",\n"
            "                \"overallStatus\": overall,\n"
            "                \"itemCount\": len(results),\n"
            "                \"successCount\": success_n,\n"
            "            },\n"
            "        )\n"
            "    except AuditCommitError:\n"
        ),
        replacement=(
            "    try:\n"
            "        audit.append(\n"
            "            operation_id=operation_id,\n"
            "            payload={\n"
            "                \"kind\": \"user_formula_v2.batchMutate\",\n"
            "                \"overallStatus\": overall,\n"
            "                \"itemCount\": len(results),\n"
            "                \"successCount\": success_n,\n"
            "            },\n"
            "        )\n"
            "    except AuditCommitError:\n"
            "        pass  # mutation: warn-then-commit\n"
            "    if False:\n"
        ),
        wants=("test_audit_failure_blocks_commit_and_retains_draft",),
        runner="pytest:tests/test_user_formula_v2.py",
    ),
    Case(
        id="T9-M1-assist-borrows-review",
        file=FE / "src/shell/formula/aiActionTaxonomy.ts",
        anchor=(
            "  if (input.usingAiReviewPermission) {\n"
            "    return {\n"
            "      ok: false,\n"
            "      reasonCode: 'assist_must_not_borrow_review',\n"
            "      detail: 'AI 助手不得借用 AI 复核权限',\n"
            "    }\n"
            "  }\n"
        ),
        replacement="  // mutation: assist may borrow review permission\n",
        wants=("assist must use DSH carrier",),
        runner="vitest:src/shell/formula/__tests__/aiActionTaxonomy.spec.ts",
    ),
]


def run_case(case: Case) -> tuple[int, str]:
    kind, path = case.runner.split(":", 1)
    if kind == "vitest":
        cmd = f"npx vitest run {path}"
        cwd = FE
    else:
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
    for runner in sorted({c.runner for c in CASES}):
        dummy = Case("b", CASES[0].file, "x", "x", (), runner)
        rc, out = run_case(dummy)
        if rc != 0:
            print("baseline not green", runner)
            print(out[-1500:].encode("ascii", errors="replace").decode("ascii"))
            return 1
    print("OK baselines")
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
