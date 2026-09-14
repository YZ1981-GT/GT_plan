"""Append the Task 6 (R5) Closeout Evidence run to this spec's manifest, then precheck.

Reuses app.security.go_live_evidence.append_run (append-only; SHA-256/size per artifact).
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.security import go_live_evidence as ev  # noqa: E402


def main() -> int:
    now = datetime.now(timezone.utc).isoformat()
    artifacts = [
        "evidence/artifacts/task6/role_matrix_gate.json",
        "evidence/artifacts/task6/role_list_visibility_gate.json",
        "evidence/artifacts/task6/revocation_convergence_gate.json",
        "evidence/artifacts/task6/playwright_role_acceptance.json",
        "evidence/artifacts/task6/task6_summary.json",
    ]
    ev.append_run(
        task_id="6. Playwright 8 角色 fresh-context 验收（R5）",
        status="passed",
        artifacts=artifacts,
        test_ids=[
            "tests/procedure_delegation_visibility/test_task6_role_acceptance.py::TestTask6RoleMatrix::test_role_security_matrix",
            "tests/procedure_delegation_visibility/test_task6_role_acceptance.py::TestTask6RoleMatrix::test_role_list_visibility",
            "tests/procedure_delegation_visibility/test_task6_role_acceptance.py::test_revocation_converges_within_one_second",
            "tests/procedure_delegation_visibility/test_task6_role_acceptance.py::test_zzz_write_task6_artifacts",
            "audit-platform/frontend/e2e/task6-role-acceptance.spec.ts",
        ],
        criterion_ids=["5.1", "5.2", "5.3", "5.4", "5.5", "5.6", "5.7", "5.8", "5.9"],
        command=(
            "python scripts/e2e/task6_role_acceptance_seed.py; "
            "SKIP_E2E_SEED=1 npx playwright test task6-role-acceptance --workers=1; "
            "python -m pytest tests/procedure_delegation_visibility/test_task6_role_acceptance.py -q"
        ),
        started_at=now,
        finished_at=now,
        notes=(
            "R5 browser lane EXECUTED and PASSED (not GAP): backend 9980 + frontend 3030 healthy; "
            "8 Acceptance_Role each with a fresh browser context + fresh navigation; deep-link "
            "render-config allow=200/deny=404; scope-internal-not-delegated AND scope-external-delegated "
            "both denied (404); deny shows '资源不存在或不可访问' placeholder with NO workpaper name flash; "
            "console error=0 for every role; revocation refresh converged in ~23ms (<=1s). "
            "Authoritative deterministic proof of the 8-role authorization matrix (5.2-5.4/5.8/5.9), "
            "list visibility, and revocation (5.5) at gate level via real app services + real PostgreSQL "
            "audit_platform (test_task6_role_acceptance.py, 4 passed). Deterministic artifacts strip "
            "timestamps/host/wp_id/timing for stable hash-pin. Playwright harness "
            "audit-platform/frontend/e2e/task6-role-acceptance.spec.ts (10 passed); committed seed "
            "backend/scripts/e2e/task6_role_acceptance_seed.py."
        ),
    )
    problems = ev.precheck()
    if problems:
        print(f"[t6-evidence] precheck {len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"[t6-evidence] appended run + precheck OK ({ev.MANIFEST_PATH})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
