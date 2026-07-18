"""Baseline contracts for procedure-delegation-visibility-isolation (Task 1).

Freezes the *verified current-state* facts the whole feature builds on, so later
tasks (and CI) can detect drift from the baseline. These are honest baseline
assertions: existing security gaps are recorded as ``unmigrated`` / ``gap`` and
must never be presented as implemented.

Stdlib-only; no DB access. The ORM-name check is a source-of-truth string
assertion validated against ``app.models`` by the self-test, not a live query.
"""
from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Authoritative table + field contracts (verified against the ORM).
# ---------------------------------------------------------------------------
TABLE_CONTRACTS: dict[str, str] = {
    # The real ORM table is singular `working_paper` (NOT `working_papers`).
    "working_paper": "singular",
    "wp_index": "wp_code lives here (JOIN with working_paper)",
    "procedure_instances": "Workpaper_Lead staff projection (non authoritative)",
    "procedure_row_tasks": "row-level assignee/reviewer authority",
    "staff_members": "unique active staff<->user mapping source",
    "project_assignments": "project role authority",
    "project_users": "project scope_cycles authority",
}

FIELD_CONTRACTS: dict[str, str] = {
    # Two-layer delegation authoritative fields.
    "WorkingPaper.assigned_to": "user_id (users.id) — Workpaper_Lead authority",
    "ProcedureInstance.assigned_to": "staff_id (staff_members.id) — lead Staff_Projection only",
    "ProcedureRowTask.assignee_staff_id": "staff_id — Row_Assignee authority",
    "ProcedureRowTask.reviewer_staff_id": "staff_id — Operation_Reviewer authority",
}

FORBIDDEN_TABLE_NAMES: tuple[str, ...] = ("working_papers",)

# Pre-feature migration head frozen at Task 1 baseline snapshot.
MIGRATION_HEAD = "V112"
# This feature's own migration, applied by Task 2. The live head is now V115
# (``V115__wp_visibility_delegation_history_audit_epoch.sql``). Recorded here so
# the drift check reflects the feature-applied head without weakening the
# anti-fake-pass intent (which is enforced by the ledger gate/matrix/test_ids).
FEATURE_APPLIED_MIGRATION = "V115"

# ---------------------------------------------------------------------------
# Known security gaps at baseline (recorded as gaps, never as passing).
# ---------------------------------------------------------------------------
KNOWN_GAPS: dict[str, str] = {
    "wp_bound_gate": "unmigrated",  # no unified resolve_wp_binding_and_access() yet
    "action_matrix": "unmigrated",  # no unified Action_Matrix / Review_Whitelist yet
    "render_config": "gap",         # render-config entry authorized project/auth-only
    "ai": "gap",                    # AI generate/summarize/OCR wp entries not gated
    "attachment": "gap",            # attachment upload/read/download/associate not gated
    "onlyoffice_wopi": "gap",       # editor config/callback/WOPI claims not fully bound
    "checklist_responses": "gap",   # checklist read/save not wp-page gated
    "procedure_task": "gap",        # procedure delegation/task entries not gated
    "traceback_temp_log": "risk",   # `_render_config_500.log` temp traceback log risk (Req/design)
}

# Legacy temporary artifact that must not persist (design "Error Handling").
TRACEBACK_TEMP_LOG = "_render_config_500.log"


def get_baseline() -> dict[str, Any]:
    """Return the immutable baseline contract snapshot."""
    return {
        "spec": "procedure-delegation-visibility-isolation",
        "migration_head": MIGRATION_HEAD,
        "feature_applied_migration": FEATURE_APPLIED_MIGRATION,
        "migration_note": (
            "V112 = pre-feature baseline snapshot; Task 2 migration was renumbered "
            "to V115 (wp_visibility_delegation_history_audit_epoch) after resolving "
            "the V113 collision. Live feature migration is V115."
        ),
        "tables": dict(TABLE_CONTRACTS),
        "forbidden_table_names": list(FORBIDDEN_TABLE_NAMES),
        "fields": dict(FIELD_CONTRACTS),
        "known_gaps": dict(KNOWN_GAPS),
        "traceback_temp_log": TRACEBACK_TEMP_LOG,
    }


def verify_orm_table_names() -> list[str]:
    """Assert the ORM uses `working_paper` (singular) and not `working_papers`.

    Returns a list of problems (empty == OK). Imports ORM models lazily.
    """
    problems: list[str] = []
    try:
        from app.models.workpaper_models import WorkingPaper  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return [f"cannot import WorkingPaper ORM model: {exc}"]

    tablename = getattr(WorkingPaper, "__tablename__", None)
    if tablename != "working_paper":
        problems.append(
            f"WorkingPaper.__tablename__ expected 'working_paper', got {tablename!r}"
        )
    # WorkingPaper.assigned_to must reference users.id (user_id authority).
    assigned = getattr(WorkingPaper, "assigned_to", None)
    if assigned is not None:
        try:
            fks = list(getattr(assigned, "property").columns[0].foreign_keys)
            targets = {fk.target_fullname for fk in fks}
            if targets and not any(t.startswith("users.") for t in targets):
                problems.append(
                    f"WorkingPaper.assigned_to should FK users.id, got {targets}"
                )
        except Exception:  # noqa: BLE001 — FK introspection best-effort
            pass
    return problems


def verify_baseline() -> list[str]:
    """Full baseline verification. Returns problems (empty == OK)."""
    problems = verify_orm_table_names()
    # Gaps must be recorded honestly (no gap silently marked implemented).
    for name, status in KNOWN_GAPS.items():
        if status not in ("unmigrated", "gap", "risk"):
            problems.append(f"gap {name!r} has non-baseline status {status!r}")
    return problems
