"""User formula API v2 — Task 8 guards."""

from __future__ import annotations

from app.services.user_formula_v2 import (
    InMemoryAuditGate,
    UserFormulaV2Store,
    apply_batch_mutate,
    history_for,
    validate_command,
)


def _create_item(**kwargs):
    base = {
        "commandVersion": "2.0",
        "clientItemId": "c1",
        "action": "create",
        "formulaId": None,
        "location": {"wpId": "wp1"},
        "target": {"a1": "A1"},
        "formulaFunction": "TB",
        "ruleCategory": "auto_calc",
        "expression": "=TB(1001)",
        "refs": [],
        "baseVersion": None,
        "reason": "test create",
    }
    base.update(kwargs)
    return base


def test_formula_function_and_category_must_not_collapse() -> None:
    assert validate_command(_create_item(formula_type="TB")) == "formula_type_dual_sense_forbidden"
    assert (
        validate_command(_create_item(formulaFunction="auto_calc", ruleCategory="auto_calc"))
        == "function_category_collapsed"
    )
    assert validate_command(_create_item()) is None


def test_batch_create_update_conflict_and_partial() -> None:
    store = UserFormulaV2Store()
    audit = InMemoryAuditGate()
    created = apply_batch_mutate(
        store=store,
        operation_id="op1",
        items=[_create_item()],
        audit=audit,
    )
    assert created["overallStatus"] == "success"
    assert created["committed"] is True
    fid = created["items"][0]["formulaId"]
    ver = created["items"][0]["serverVersion"]

    mixed = apply_batch_mutate(
        store=store,
        operation_id="op2",
        items=[
            {
                **_create_item(clientItemId="ok", action="update", formulaId=fid, baseVersion=ver, expression="=2"),
            },
            {
                **_create_item(
                    clientItemId="stale",
                    action="update",
                    formulaId=fid,
                    baseVersion="wrong",
                    expression="=3",
                ),
            },
        ],
        audit=audit,
    )
    # Second item conflicts; first may succeed — overall partial
    assert mixed["overallStatus"] == "partial"
    assert any(i["status"] == "success" for i in mixed["items"])
    assert any(i["status"] == "conflict" and i["draftRetained"] for i in mixed["items"])


def test_audit_failure_blocks_commit_and_retains_draft() -> None:
    store = UserFormulaV2Store()
    audit = InMemoryAuditGate(fail=True)
    result = apply_batch_mutate(
        store=store,
        operation_id="op-fail",
        items=[_create_item()],
        audit=audit,
    )
    assert result["committed"] is False
    assert result["overallStatus"] == "failed"
    assert result["items"][0]["errorCode"] == "audit_commit_failed"
    assert result["items"][0]["draftRetained"] is True
    assert store.list_for_location(None) == []


def test_restore_creates_new_version_and_history() -> None:
    store = UserFormulaV2Store()
    audit = InMemoryAuditGate()
    created = apply_batch_mutate(
        store=store, operation_id="op-c", items=[_create_item()], audit=audit,
    )
    fid = created["items"][0]["formulaId"]
    ver = created["items"][0]["serverVersion"]
    apply_batch_mutate(
        store=store,
        operation_id="op-d",
        items=[{
            **_create_item(action="delete", formulaId=fid, baseVersion=ver, clientItemId="d"),
        }],
        audit=audit,
    )
    deleted = store.get(fid)
    assert deleted and deleted.deleted
    restored = apply_batch_mutate(
        store=store,
        operation_id="op-r",
        items=[{
            **_create_item(
                action="restore",
                formulaId=fid,
                baseVersion=deleted.version,
                clientItemId="r",
            ),
        }],
        audit=audit,
    )
    assert restored["items"][0]["status"] == "success"
    rec = store.get(fid)
    assert rec and not rec.deleted
    assert rec.version != ver
    hist = history_for(store, fid)
    assert any(h["action"] == "restore" for h in hist["versions"])


def test_forbidden_when_not_allowed() -> None:
    store = UserFormulaV2Store()
    result = apply_batch_mutate(
        store=store,
        operation_id="op-f",
        items=[_create_item()],
        audit=InMemoryAuditGate(),
        allowed=False,
    )
    assert result["items"][0]["status"] == "forbidden"
    assert result["items"][0]["draftRetained"] is True
