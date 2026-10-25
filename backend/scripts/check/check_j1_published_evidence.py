"""Fail-closed gate for J1 published-representation / real-OO evidence.

The manifest may claim ``published_representation_verified`` only when the evidence is
fresh for the current J1 source digest, resolves the current four definition digests,
uses an explicit project/wp target, and records a real OnlyOffice build.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

DEFAULT_EVIDENCE = (
    REPO / ".kiro/specs/j1-post-publish-semantic-and-evidence-closure/evidence/oo94.json"
)
ENTRY_ID = "xlsx/j1/gt-j1-employee-compensation"


def current_facts() -> dict[str, Any]:
    from app.services.workpaper_sync import phase5_j1_employee_compensation as J1
    from app.services.workpaper_sync.definitions import canonical_digest
    from scripts.e2e.verify_j1_oo94_roundtrip import _source_digest

    contract = J1.assert_contract_file_matches_source()
    manifest = json.loads((BACKEND / "data/workpaper_sync_entry_manifest.json").read_text(encoding="utf-8"))
    entry = next((e for e in manifest["entries"] if e["entry_id"] == ENTRY_ID), None)
    return {
        "source_digest": _source_digest(),
        "digests": {
            "authority_model": canonical_digest(J1.authority_model_payload()),
            "template": contract.template_definition_sha256,
            "instrumentation": contract.instrumentation_definition_sha256,
            "contract": contract.canonical_sha256,
        },
        "template_sha256": J1.TEMPLATE_SHA256,
        "manifest": entry,
    }


def _is_ancestor(commit: str) -> bool:
    if not commit:
        return False
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
        cwd=REPO,
        capture_output=True,
    ).returncode == 0


def evaluate(evidence: Mapping[str, Any], facts: Mapping[str, Any], *, check_commit: bool = True) -> list[str]:
    errors: list[str] = []
    if evidence.get("schema_version") != "j1-oo94-evidence:v1" or evidence.get("status") != "passed":
        errors.append("evidence schema/status 非 passed v1")
    if evidence.get("entry_id") != ENTRY_ID or evidence.get("wp_code") != "J1":
        errors.append("entry_id/wp_code 不符")
    if not evidence.get("project_id") or not evidence.get("wp_id"):
        errors.append("缺显式 project_id/wp_id")
    if evidence.get("source_digest") != facts.get("source_digest"):
        errors.append("source_digest stale")
    if check_commit and not _is_ancestor(str(evidence.get("source_commit") or "")):
        errors.append("source_commit 不是当前 HEAD 祖先")
    active = evidence.get("active") or {}
    if active.get("digests") != facts.get("digests"):
        errors.append("active 四 definition digest 与当前 provider 不符")
    if active.get("active_template_sha256") != facts.get("template_sha256"):
        errors.append("active frozen template 不是当前净化模板")
    if active.get("external_links") != []:
        errors.append("active/authority template 仍有外链")
    if int(active.get("generation") or 0) < 1 or not active.get("bundle_id"):
        errors.append("缺 current representation generation/bundle")
    oo = evidence.get("onlyoffice") or {}
    if not oo.get("version") or not oo.get("source"):
        errors.append("缺真实 OnlyOffice 版本")
    if evidence.get("rounds") != [
        "frontend_skeleton_19_rows",
        "frontend_payload_with_amounts_19_rows",
    ]:
        errors.append("两轮场景不完整")
    if (evidence.get("store_snapshot") or {}).get("unchanged") is not True:
        errors.append("未证明 store 快照不变")
    if evidence.get("legacy_identity_mutation_enabled") is not False:
        errors.append("成功 evidence 不能来自 legacy identity 变异模式")
    entry = facts.get("manifest") or {}
    expected_manifest = {
        "capability": "bidirectional",
        "migration_state": "adapter_registered",
        "adapter_id": "j1.accrual_check_short_term",
        "canonical_resolver": "workpaper_sync_published_representation",
    }
    for key, value in expected_manifest.items():
        if entry.get(key) != value:
            errors.append(f"manifest {key}={entry.get(key)!r} != {value!r}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    args = parser.parse_args()
    if not args.evidence.is_file():
        print(f"[FAIL] 缺 J1 真栈 evidence: {args.evidence}")
        return 1
    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    errors = evaluate(evidence, current_facts())
    if errors:
        print("[FAIL] J1 published evidence stale/invalid:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(
        "[OK] J1 published evidence fresh: "
        f"wp={str(evidence['wp_id'])[:8]} generation={evidence['active']['generation']} "
        f"OO={evidence['onlyoffice']['version']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
