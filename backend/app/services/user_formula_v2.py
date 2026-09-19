"""User formula API v2 — batch mutate with per-item conflict + audit commit gate.

Spec: workpaper-page-formula-toolbar-closure Task 8
Requirements: 8.1–8.7

Legacy ``dict[cell_key, formula]`` stays on ``wp_user_formulas.py`` for migration
only. New capability path MUST use this module and MUST NOT warn-then-commit
when audit/outbox fails.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Literal, Protocol
from uuid import uuid4

COMMAND_VERSION = "2.0"

Action = Literal["create", "update", "delete", "restore"]
ItemStatus = Literal["success", "conflict", "forbidden", "invalid", "error"]
OverallStatus = Literal["success", "partial", "failed"]


class AuditCommitError(Exception):
    """Raised when durable audit/outbox cannot be written — blocks commit."""


class AuditGate(Protocol):
    def append(self, *, operation_id: str, payload: dict[str, Any]) -> None: ...


class InMemoryAuditGate:
    """Test double that records entries; set ``fail=True`` to simulate outbox failure."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.entries: list[dict[str, Any]] = []

    def append(self, *, operation_id: str, payload: dict[str, Any]) -> None:
        if self.fail:
            raise AuditCommitError("audit/outbox write failed")
        self.entries.append({"operationId": operation_id, **payload})


@dataclass
class FieldConflict:
    field: str
    base: Any
    current: Any
    incoming: Any

    def to_wire(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "base": self.base,
            "current": self.current,
            "incoming": self.incoming,
        }


@dataclass
class UserFormulaRecord:
    formula_id: str
    version: str
    expression: str | None
    formula_function: str | None
    rule_category: str
    refs: list[str]
    target: dict[str, Any]
    location_digest: str
    deleted: bool = False
    history: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class BatchItemResult:
    client_item_id: str
    status: ItemStatus
    formula_id: str | None
    server_version: str | None
    field_conflicts: list[FieldConflict]
    error_code: str | None
    draft_retained: bool = False

    def to_wire(self) -> dict[str, Any]:
        return {
            "clientItemId": self.client_item_id,
            "status": self.status,
            "formulaId": self.formula_id,
            "serverVersion": self.server_version,
            "fieldConflicts": [c.to_wire() for c in self.field_conflicts],
            "errorCode": self.error_code,
            "draftRetained": self.draft_retained,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_version() -> str:
    return hashlib.sha256(f"{uuid4()}:{_now()}".encode()).hexdigest()[:16]


def location_digest(location: dict[str, Any] | None) -> str:
    raw = json.dumps(location or {}, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def validate_command(cmd: dict[str, Any]) -> str | None:
    """Return error code or None if valid."""
    if cmd.get("commandVersion") != COMMAND_VERSION:
        return "invalid_command_version"
    if cmd.get("action") not in {"create", "update", "delete", "restore"}:
        return "invalid_action"
    # formulaFunction and ruleCategory must never share the same field.
    if "formula_type" in cmd:
        return "formula_type_dual_sense_forbidden"
    ff = cmd.get("formulaFunction")
    rc = cmd.get("ruleCategory")
    if ff is not None and rc is not None and ff == rc and ff in {
        "auto_calc", "logic_check", "reasonability",
    }:
        return "function_category_collapsed"
    if not isinstance(cmd.get("reason"), str) or not str(cmd.get("reason")).strip():
        return "reason_required"
    return None


class UserFormulaV2Store:
    """In-process authoritative store for v2 formulas (tests + early wiring)."""

    def __init__(self) -> None:
        self._by_id: dict[str, UserFormulaRecord] = {}

    def get(self, formula_id: str) -> UserFormulaRecord | None:
        return self._by_id.get(formula_id)

    def list_for_location(self, location: dict[str, Any] | None) -> list[UserFormulaRecord]:
        digest = location_digest(location) if location else None
        out = []
        for rec in self._by_id.values():
            if rec.deleted:
                continue
            if digest is None or rec.location_digest == digest:
                out.append(rec)
        return out

    def upsert(self, rec: UserFormulaRecord) -> None:
        self._by_id[rec.formula_id] = rec


def apply_batch_mutate(
    *,
    store: UserFormulaV2Store,
    operation_id: str,
    items: list[dict[str, Any]],
    audit: AuditGate,
    allowed: bool = True,
    clock: Callable[[], str] = _now,
) -> dict[str, Any]:
    """Apply per-item commands. Audit failure rolls back the whole batch."""

    # Stage mutations; only commit to store after audit succeeds.
    staged: list[tuple[UserFormulaRecord | None, str | None, BatchItemResult]] = []
    # (new_or_updated_record_or_None_if_delete_marker, previous_snapshot_json, result)

    for raw in items:
        client_id = str(raw.get("clientItemId") or uuid4())
        err = validate_command(raw)
        if err:
            staged.append((
                None,
                None,
                BatchItemResult(
                    client_item_id=client_id,
                    status="invalid",
                    formula_id=raw.get("formulaId"),
                    server_version=None,
                    field_conflicts=[],
                    error_code=err,
                    draft_retained=True,
                ),
            ))
            continue

        if not allowed:
            staged.append((
                None,
                None,
                BatchItemResult(
                    client_item_id=client_id,
                    status="forbidden",
                    formula_id=raw.get("formulaId"),
                    server_version=None,
                    field_conflicts=[],
                    error_code="capability_denied",
                    draft_retained=True,
                ),
            ))
            continue

        action: Action = raw["action"]
        formula_id = raw.get("formulaId")
        base_version = raw.get("baseVersion")

        if action == "create":
            new_id = str(uuid4())
            ver = _new_version()
            rec = UserFormulaRecord(
                formula_id=new_id,
                version=ver,
                expression=raw.get("expression"),
                formula_function=raw.get("formulaFunction"),
                rule_category=str(raw.get("ruleCategory") or "auto_calc"),
                refs=list(raw.get("refs") or []),
                target=dict(raw.get("target") or {}),
                location_digest=location_digest(raw.get("location")),
                history=[{
                    "version": ver,
                    "action": "create",
                    "at": clock(),
                    "reason": raw.get("reason"),
                    "expression": raw.get("expression"),
                }],
            )
            staged.append((
                rec,
                None,
                BatchItemResult(
                    client_item_id=client_id,
                    status="success",
                    formula_id=new_id,
                    server_version=ver,
                    field_conflicts=[],
                    error_code=None,
                ),
            ))
            continue

        if not formula_id or not isinstance(formula_id, str):
            staged.append((
                None,
                None,
                BatchItemResult(
                    client_item_id=client_id,
                    status="invalid",
                    formula_id=None,
                    server_version=None,
                    field_conflicts=[],
                    error_code="formula_id_required",
                    draft_retained=True,
                ),
            ))
            continue

        current = store.get(formula_id)
        if current is None or (current.deleted and action != "restore"):
            staged.append((
                None,
                None,
                BatchItemResult(
                    client_item_id=client_id,
                    status="invalid",
                    formula_id=formula_id,
                    server_version=None,
                    field_conflicts=[],
                    error_code="formula_not_found",
                    draft_retained=True,
                ),
            ))
            continue

        if base_version is not None and base_version != current.version:
            staged.append((
                None,
                None,
                BatchItemResult(
                    client_item_id=client_id,
                    status="conflict",
                    formula_id=formula_id,
                    server_version=current.version,
                    field_conflicts=[
                        FieldConflict(
                            field="baseVersion",
                            base=base_version,
                            current=current.version,
                            incoming=base_version,
                        ),
                    ],
                    error_code="version_conflict",
                    draft_retained=True,
                ),
            ))
            continue

        prev_snap = json.dumps({
            "formulaId": current.formula_id,
            "version": current.version,
            "expression": current.expression,
            "deleted": current.deleted,
            "history": current.history,
        }, ensure_ascii=True)

        if action == "update":
            ver = _new_version()
            updated = UserFormulaRecord(
                formula_id=current.formula_id,
                version=ver,
                expression=raw.get("expression", current.expression),
                formula_function=raw.get("formulaFunction", current.formula_function),
                rule_category=str(raw.get("ruleCategory") or current.rule_category),
                refs=list(raw.get("refs") or current.refs),
                target=dict(raw.get("target") or current.target),
                location_digest=location_digest(raw.get("location")) or current.location_digest,
                deleted=False,
                history=[
                    *current.history,
                    {
                        "version": ver,
                        "action": "update",
                        "at": clock(),
                        "reason": raw.get("reason"),
                        "expression": raw.get("expression", current.expression),
                    },
                ],
            )
            staged.append((
                updated,
                prev_snap,
                BatchItemResult(
                    client_item_id=client_id,
                    status="success",
                    formula_id=updated.formula_id,
                    server_version=ver,
                    field_conflicts=[],
                    error_code=None,
                ),
            ))
        elif action == "delete":
            ver = _new_version()
            deleted = UserFormulaRecord(
                formula_id=current.formula_id,
                version=ver,
                expression=current.expression,
                formula_function=current.formula_function,
                rule_category=current.rule_category,
                refs=current.refs,
                target=current.target,
                location_digest=current.location_digest,
                deleted=True,
                history=[
                    *current.history,
                    {
                        "version": ver,
                        "action": "delete",
                        "at": clock(),
                        "reason": raw.get("reason"),
                    },
                ],
            )
            staged.append((
                deleted,
                prev_snap,
                BatchItemResult(
                    client_item_id=client_id,
                    status="success",
                    formula_id=deleted.formula_id,
                    server_version=ver,
                    field_conflicts=[],
                    error_code=None,
                ),
            ))
        elif action == "restore":
            # Restore creates a NEW immutable version (never resurrect old version id).
            ver = _new_version()
            restored_expr = None
            if current.history:
                for h in reversed(current.history):
                    if h.get("action") in {"create", "update"} and h.get("expression") is not None:
                        restored_expr = h.get("expression")
                        break
            restored = UserFormulaRecord(
                formula_id=current.formula_id,
                version=ver,
                expression=restored_expr if restored_expr is not None else current.expression,
                formula_function=current.formula_function,
                rule_category=current.rule_category,
                refs=current.refs,
                target=current.target,
                location_digest=current.location_digest,
                deleted=False,
                history=[
                    *current.history,
                    {
                        "version": ver,
                        "action": "restore",
                        "at": clock(),
                        "reason": raw.get("reason"),
                        "expression": restored_expr,
                    },
                ],
            )
            staged.append((
                restored,
                prev_snap,
                BatchItemResult(
                    client_item_id=client_id,
                    status="success",
                    formula_id=restored.formula_id,
                    server_version=ver,
                    field_conflicts=[],
                    error_code=None,
                ),
            ))

    results = [t[2] for t in staged]
    success_n = sum(1 for r in results if r.status == "success")
    if success_n == 0:
        overall: OverallStatus = "failed"
    elif success_n == len(results):
        overall = "success"
    else:
        overall = "partial"

    # Commit gate: audit first; on failure do not mutate store.
    try:
        audit.append(
            operation_id=operation_id,
            payload={
                "kind": "user_formula_v2.batchMutate",
                "overallStatus": overall,
                "itemCount": len(results),
                "successCount": success_n,
            },
        )
    except AuditCommitError:
        return {
            "overallStatus": "failed",
            "operationId": operation_id,
            "items": [
                BatchItemResult(
                    client_item_id=r.client_item_id,
                    status="error",
                    formula_id=r.formula_id,
                    server_version=None,
                    field_conflicts=[],
                    error_code="audit_commit_failed",
                    draft_retained=True,
                ).to_wire()
                for r in results
            ],
            "committed": False,
        }

    for rec, _prev, result in staged:
        if result.status == "success" and rec is not None:
            store.upsert(rec)

    return {
        "overallStatus": overall,
        "operationId": operation_id,
        "items": [r.to_wire() for r in results],
        "committed": True,
    }


def history_for(store: UserFormulaV2Store, formula_id: str) -> dict[str, Any]:
    rec = store.get(formula_id)
    if rec is None:
        return {"formulaId": formula_id, "versions": []}
    return {"formulaId": formula_id, "versions": list(rec.history)}


# Process-local default store for early router wiring / unit tests.
DEFAULT_V2_STORE = UserFormulaV2Store()
