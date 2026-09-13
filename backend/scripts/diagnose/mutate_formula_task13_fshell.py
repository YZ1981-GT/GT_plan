"""Task 13 — directed suite + required mutations + F-SHELL evidence publish.

Required mutation matrix (tasks.md T13):
  CSS-class-as-slot, fallback steal, location missing, dirty follows,
  mixed dimensions, collision takes first, old dict, audit warning commit,
  duplicate AI, legacy thread key, invisible occupies slot.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FE = ROOT / "audit-platform/frontend"
BE = ROOT / "backend"
SPEC = ROOT / ".kiro/specs/workpaper-page-formula-toolbar-closure"
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


@dataclass(frozen=True)
class Case:
    id: str
    file: Path
    anchor: str
    replacement: str
    wants: tuple[str, ...]
    runner: str


CASES: list[Case] = [
    Case(
        id="T13-M01-css-class-as-slot",
        file=FE / "src/shell/formula/toolbarOutletArbiter.ts",
        anchor=(
            "    if (input.outletElement.classList?.contains('gt-wp-toolbar__right')\n"
            "      && !input.outletElement.hasAttribute('data-toolbar-outlet')) {\n"
            "      return { ok: false, reasonCode: 'css_class_not_outlet' }\n"
            "    }\n"
        ),
        replacement="    // mutation: CSS class accepted as outlet\n",
        wants=("rejects duplicate kind, cross-epoch, and CSS-class-only outlet",),
        runner="vitest:src/shell/formula/__tests__/toolbarOutletArbiter.spec.ts",
    ),
    Case(
        id="T13-M02-fallback-steals",
        file=FE / "src/shell/formula/toolbarOutletArbiter.ts",
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
        runner="vitest:src/shell/formula/__tests__/toolbarOutletArbiter.spec.ts",
    ),
    Case(
        id="T13-M03-location-missing",
        file=FE / "src/shell/formula/openFormulaManagerCommand.ts",
        anchor=(
            "  const identity = assertLocationIdentity(input.location)\n"
            "  if (!identity) {\n"
            "    return {\n"
            "      ok: false,\n"
            "      reasonCode: 'gc0_location_rejected',\n"
            "      detail: 'CanonicalWorkpaperLocation failed G-C0 version gate',\n"
            "    }\n"
            "  }\n"
        ),
        replacement="  // mutation: missing/invalid location accepted\n",
        wants=("location missing/invalid major is rejected",),
        runner="vitest:src/shell/formula/__tests__/fShellConformance.spec.ts",
    ),
    Case(
        id="T13-M04-dirty-follows-latest",
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
        wants=("dirty draft pins",),
        runner="vitest:src/shell/formula/__tests__/fShellConformance.spec.ts",
    ),
    Case(
        id="T13-M05-mixed-dimensions",
        file=FE / "src/shell/formula/userFormulaV2.ts",
        anchor=(
            "  if (\n"
            "    cmd.formulaFunction &&\n"
            "    cmd.formulaFunction === cmd.ruleCategory &&\n"
            "    ['auto_calc', 'logic_check', 'reasonability'].includes(cmd.formulaFunction)\n"
            "  ) {\n"
            "    return { ok: false, reasonCode: 'function_category_collapsed' }\n"
            "  }\n"
        ),
        replacement="  // mutation: allow collapsed function/category dimensions\n",
        wants=("rejects collapsed formulaFunction/ruleCategory",),
        runner="vitest:src/shell/formula/__tests__/userFormulaV2.spec.ts",
    ),
    Case(
        id="T13-M06-collision-takes-first",
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
        wants=("collision with different digests is blocked",),
        runner="vitest:src/shell/formula/__tests__/fShellConformance.spec.ts",
    ),
    Case(
        id="T13-M07-old-dict-formula-type",
        file=FE / "src/shell/formula/userFormulaV2.ts",
        anchor=(
            "  if ('formula_type' in cmd && cmd.formula_type !== undefined) {\n"
            "    return { ok: false, reasonCode: 'formula_type_dual_sense_forbidden' }\n"
            "  }\n"
        ),
        replacement="  // mutation: legacy formula_type accepted on v2 path\n",
        wants=("formula_type dual-sense forbidden",),
        runner="vitest:src/shell/formula/__tests__/fShellConformance.spec.ts",
    ),
    Case(
        id="T13-M08-audit-warning-commit",
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
        id="T13-M09-assist-borrows-review",
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
        wants=("assist is DSH-only",),
        runner="vitest:src/shell/formula/__tests__/fShellConformance.spec.ts",
    ),
    Case(
        id="T13-M10-legacy-thread-forge-cell",
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
        wants=("no forged cell scope",),
        runner="vitest:src/shell/formula/__tests__/fShellConformance.spec.ts",
    ),
    Case(
        id="T13-M11-invisible-occupies-slot",
        file=FE / "src/shell/formula/rightRailArbiter.ts",
        anchor=(
            "  listTriggerSlots(): RightRailLayoutSlot[] {\n"
            "    return this.listOrdered().map((rail) => {\n"
            "      if (!rail.visible) {\n"
            "        return { id: rail.id, occupiesSlot: false, reasonCode: 'invisible' }\n"
            "      }\n"
        ),
        replacement=(
            "  listTriggerSlots(): RightRailLayoutSlot[] {\n"
            "    return this.listOrdered().map((rail) => {\n"
            "      if (!rail.visible) {\n"
            "        return { id: rail.id, occupiesSlot: true, reasonCode: 'invisible' }\n"
            "      }\n"
        ),
        wants=("invisible never occupies slot",),
        runner="vitest:src/shell/formula/__tests__/fShellConformance.spec.ts",
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


def run_directed() -> tuple[int, str]:
    return run_case(
        Case(
            id="directed",
            file=FE / "src/shell/formula/fShellContract.ts",
            anchor="x",
            replacement="x",
            wants=(),
            runner="vitest:src/shell/formula/__tests__/fShellConformance.spec.ts",
        )
    )


def publish_evidence(report: dict) -> None:
    evidence_dir = SPEC / "evidence" / "F-SHELL"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    basis = SPEC / "basis"
    basis.mkdir(parents=True, exist_ok=True)

    report_path = basis / "T13-mutation-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    digest = hashlib.sha256(report_path.read_bytes()).hexdigest()

    contract = {
        "contractId": "F-SHELL",
        "contractVersion": "1.0",
        "producerSpec": "workpaper-page-formula-toolbar-closure",
        "producerTask": 13,
        "consumers": [
            "workpaper-guidance-content-closure:G20",
            "custom-workpaper-template-ingestion-and-sync-closure:X12",
            "custom-workpaper-template-ingestion-and-sync-closure:X18",
        ],
        "dependsOn": {"G-C0": "1.0", "G-ID": "1.0", "G-RAIL": "1.0"},
        "module": "audit-platform/frontend/src/shell/formula/fShellContract.ts",
        "mutationReportDigest": digest,
        "recordedAt": report["recordedAt"],
        "verdict": report["verdict"],
    }
    (evidence_dir / "contract.json").write_text(
        json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    envelope = {
        "contractVersion": "1.0",
        "evidenceId": "evidence-fshell-milestone-1",
        "runId": report["runId"],
        "subject": {"kind": "contract", "contractId": "F-SHELL"},
        "contractVersions": {
            "G-C0": "1.0",
            "G-ID": "1.0",
            "G-RAIL": "1.0",
            "F-SHELL": "1.0",
        },
        "inventoryDigest": None,
        "sourceDigests": {"mutationReport": digest},
        "operationIds": {"publish": "op-publish-fshell-2026-09-08"},
        "artifacts": [
            {"kind": "contract_snapshot", "path": "evidence/F-SHELL/contract.json"},
            {"kind": "mutation_report", "path": "basis/T13-mutation-report.json"},
        ],
        "verdict": report["verdict"],
        "recordedAt": report["recordedAt"],
        "producerTask": 13,
        "consumers": contract["consumers"],
    }
    (evidence_dir / "envelope.json").write_text(
        json.dumps(envelope, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"published evidence -> {evidence_dir}")
    print(f"mutation digest={digest[:16]}... verdict={report['verdict']}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-anchors", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--publish", action="store_true", help="write F-SHELL evidence after green directed+RED mutations")
    args = ap.parse_args()

    if args.check_anchors:
        bad = 0
        for c in CASES:
            n = c.file.read_text(encoding="utf-8").count(c.anchor)
            print(f"  [{'OK' if n == 1 else 'ANCHOR-MISS'}] {c.id} (n={n})")
            if n != 1:
                bad += 1
        return 1 if bad else 0

    if not args.apply and not args.publish:
        print(__doc__)
        return 0

    recorded_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    run_id = f"run-fshell-{recorded_at[:10]}"

    print("== directed suite ==")
    drc, dout = run_directed()
    directed = {
        "status": "GREEN" if drc == 0 else "FAIL",
        "returncode": drc,
        "tail": dout[-1200:],
    }
    print(f"  directed: {directed['status']}")
    if drc != 0:
        print(dout[-2000:].encode("ascii", errors="replace").decode("ascii"))
        if args.publish:
            publish_evidence(
                {
                    "runId": run_id,
                    "recordedAt": recorded_at,
                    "verdict": "FAIL",
                    "directed": directed,
                    "mutations": [],
                }
            )
        return 1

    print("== mutations ==")
    rows = []
    bad = 0
    for case in CASES:
        text = case.file.read_text(encoding="utf-8")
        n = text.count(case.anchor)
        if n != 1:
            rows.append({"id": case.id, "result": "ANCHOR-MISS", "anchorCount": n})
            print(f"  {case.id}: ANCHOR-MISS")
            bad += 1
            continue
        bak = case.file.with_suffix(case.file.suffix + ".bak")
        shutil.copy2(case.file, bak)
        try:
            case.file.write_text(text.replace(case.anchor, case.replacement, 1), encoding="utf-8")
            rc, out = run_case(case)
            if rc == 0:
                rows.append({"id": case.id, "result": "GREEN"})
                print(f"  {case.id}: GREEN FAIL")
                bad += 1
            elif not all(w in out for w in case.wants):
                rows.append({"id": case.id, "result": "WRONG-TEST", "wants": list(case.wants)})
                print(f"  {case.id}: WRONG-TEST")
                bad += 1
            else:
                rows.append({"id": case.id, "result": "RED"})
                print(f"  {case.id}: RED OK")
        finally:
            shutil.copy2(bak, case.file)
            bak.unlink(missing_ok=True)

    verdict = "PASS" if bad == 0 else "FAIL"
    report = {
        "runId": run_id,
        "recordedAt": recorded_at,
        "verdict": verdict,
        "directed": directed,
        "mutations": rows,
        "requiredCount": len(CASES),
        "redOk": sum(1 for r in rows if r["result"] == "RED"),
        "bad": bad,
    }
    print(f"bad={bad}/{len(CASES)} verdict={verdict}")

    if args.publish:
        publish_evidence(report)
    else:
        # still write report for apply-only debugging
        (SPEC / "basis").mkdir(parents=True, exist_ok=True)
        (SPEC / "basis" / "T13-mutation-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
