"""Task 16 self-tests: Route/worker Coverage Guard (Route_Drift_Guard).

Feature: procedure-delegation-visibility-isolation
Requirements: 13.1–13.15, 16.17, 16.21–16.23

Two layers:
  1. Pure AST/registry self-tests (no DB, no full-app import) proving the guard
     detects gates from real code — dynamic ``add_api_route`` routes, 1-level
     indirect wrapper hooks, and (crucially) is NOT fooled by fake comments or
     string literals mentioning gate function names.
  2. Live-app invariants: production HTTP (route, method) and non-HTTP callables
     are bidirectionally equal to the committed ledger with no fake-pass, and
     every derived classification (gated / native_authz / not_applicable /
     deferred_editor) is verified against real code / explicit allowlist.

The classification tests here are the stable test-evidence the ledger points to
for the routes it resolves (native_authz / not_applicable / deferred_editor).
"""
from __future__ import annotations

import types

import pytest

from app.security import coverage_guard as cg
from app.security.entry_coverage_scanner import LEDGER_PATH


# ---------------------------------------------------------------------------
# Layer 1 — pure AST / registry self-tests (fake-comment resistant)
# ---------------------------------------------------------------------------
def test_ast_gate_detection_ignores_comments_and_strings():
    """A comment or string mentioning a gate name is NOT a call (anti-fake)."""
    fake = (
        "async def handler(wp_id):\n"
        "    # enforce_wp_gate(db, user)  <- decoy comment, not a real call\n"
        '    note = "enforce_wp_gate"  # decoy string literal\n'
        "    return note\n"
    )
    assert cg.source_calls_gate(fake) is False
    assert "enforce_wp_gate" not in cg.ast_called_names(fake)

    real = (
        "async def handler(wp_id):\n"
        "    ctx = await enforce_wp_gate(db, user, wp_id=wp_id)\n"
        "    return ctx\n"
    )
    assert cg.source_calls_gate(real) is True
    assert "enforce_wp_gate" in cg.ast_called_names(real)


def _gate_handler(wp_id):  # module-level so inspect.getsource works
    return enforce_wp_gate(None, None, wp_id=wp_id)  # noqa: F821 — AST-only


def _wrapper_inner(wp_id):
    return enforce_task_gate(None, None, task_id=wp_id)  # noqa: F821 — AST-only


def _wrapper_handler(wp_id):
    # calls a local module-level function that itself gates (1-level indirect)
    return _wrapper_inner(wp_id)


def _bare_handler(wp_id):
    return {"wp_id": wp_id}


def test_dynamic_add_api_route_gate_detected():
    """Dynamically registered routes (add_api_route) are enumerated + gate-detected."""
    from fastapi import FastAPI

    app = FastAPI()
    app.add_api_route("/api/workpapers/{wp_id}/dyn-gated", _gate_handler, methods=["GET"])
    app.add_api_route("/api/workpapers/{wp_id}/dyn-bare", _bare_handler, methods=["GET"])

    live = cg.scan_live_http(app)
    gated = live[("/api/workpapers/{wp_id}/dyn-gated", "GET")]
    bare = live[("/api/workpapers/{wp_id}/dyn-bare", "GET")]
    assert gated.wp_bound and gated.gate_wired, "dynamic gated route must be detected"
    assert bare.wp_bound and not bare.gate_wired, "dynamic bare route must not be gate-wired"


def test_indirect_wrapper_gate_detected():
    """A handler that delegates to a local wrapper which gates is detected (1-level)."""
    wired, detail = cg.detect_handler_gate(_wrapper_handler)
    assert wired, f"indirect wrapper gate should be detected, got {detail}"
    assert "indirect" in detail


def test_bare_handler_not_gated():
    wired, _ = cg.detect_handler_gate(_bare_handler)
    assert wired is False


# ---------------------------------------------------------------------------
# Layer 1 — synthetic drift detection (missing / stale / duplicate / worker)
# ---------------------------------------------------------------------------
def _empty_app():
    return types.SimpleNamespace(routes=[])


def _committed_ledger():
    import json

    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


def test_missing_live_route_blocks():
    """A live wp route absent from the ledger is reported missing_in_ledger."""
    from fastapi import FastAPI

    app = FastAPI()
    app.add_api_route("/api/workpapers/{wp_id}/brand-new", _gate_handler, methods=["GET"])
    # ledger with no entries for this route
    ledger = {"entries": [], "migration_head": "V112"}
    f = cg.check_drift(app=app, ledger=ledger)
    assert any("brand-new" in m for m in f.missing_in_ledger)


def test_stale_ledger_route_blocks():
    """A ledger http route absent from the live app is reported stale_in_ledger."""
    ledger = {
        "entries": [
            {
                "kind": "http",
                "entrypoint": "app.routers.ghost:gone",
                "route": "/api/workpapers/{wp_id}/ghost",
                "method": "GET",
                "family": "detail",
                "action": "read",
                "wp_bound": True,
                "gate": "gated",
                "matrix": "workpaper.dedicated_subroute/dedicated_read",
                "test_ids": ["x"],
            }
        ],
        "migration_head": "V112",
    }
    f = cg.check_drift(app=_empty_app(), ledger=ledger)
    assert any("ghost" in m for m in f.stale_in_ledger)


def test_fake_pass_when_ledger_claims_gated_but_code_bare():
    """Ledger says gated but the live handler has no gate → fake_pass."""
    from fastapi import FastAPI

    app = FastAPI()
    app.add_api_route("/api/workpapers/{wp_id}/claims", _bare_handler, methods=["GET"])
    ledger = {
        "entries": [
            {
                "kind": "http",
                "entrypoint": "x:y",
                "route": "/api/workpapers/{wp_id}/claims",
                "method": "GET",
                "family": "detail",
                "action": "read",
                "wp_bound": True,
                "gate": "gated",
                "matrix": "workpaper.dedicated_subroute/dedicated_read",
                "test_ids": ["x"],
            }
        ],
        "migration_head": "V112",
    }
    f = cg.check_drift(app=app, ledger=ledger)
    assert any("claims" in m for m in f.fake_pass)


def test_fake_native_authz_without_native_hook_blocks():
    """Ledger says native_authz but the live route has no native authz → fake_pass."""
    from fastapi import FastAPI

    app = FastAPI()
    app.add_api_route("/api/workpapers/{wp_id}/faux-native", _bare_handler, methods=["GET"])
    ledger = {
        "entries": [
            {
                "kind": "http",
                "entrypoint": "x:y",
                "route": "/api/workpapers/{wp_id}/faux-native",
                "method": "GET",
                "family": "detail",
                "action": "read",
                "wp_bound": True,
                "gate": "native_authz",
                "matrix": "native_authz",
                "test_ids": ["x"],
            }
        ],
        "migration_head": "V112",
    }
    f = cg.check_drift(app=app, ledger=ledger)
    assert any("faux-native" in m for m in f.fake_pass)


def test_new_nonhttp_callable_absent_from_ledger_blocks():
    """A live worker/retry/dead-letter callable missing from the ledger blocks (re-gate req)."""
    # Ledger with NO worker entries at all -> every live worker is missing.
    ledger = {"entries": [], "migration_head": "V112"}
    f = cg.check_drift(app=_empty_app(), ledger=ledger)
    assert f.nonhttp_missing_in_ledger, "new/unregistered non-HTTP callables must block"
    assert any("procedure_dispatcher_worker" in m for m in f.nonhttp_missing_in_ledger)


def test_wp_bound_worker_fake_gated_without_regate_blocks():
    """A wp-bound worker marked 'gated' that does not actually re-gate → nonhttp_regate_missing."""
    live_workers = cg.scan_live_nonhttp()
    entries = []
    for w in live_workers:
        e = dict(w)
        if "procedure_dispatcher_worker" in e["entrypoint"]:
            e["gate"] = "gated"  # false claim of code-gated re-gate
            e["matrix"] = "worker.regate"
            e["test_ids"] = ["x"]
            e["wp_bound"] = True
        entries.append(e)
    ledger = {"entries": entries, "migration_head": "V112"}
    f = cg.check_drift(app=_empty_app(), ledger=ledger)
    assert any("procedure_dispatcher_worker" in m for m in f.nonhttp_regate_missing)


def test_new_duplicate_registration_blocks_but_known_allowlisted():
    """A NEW duplicate (route, method) blocks; a known pre-existing one is allowlisted."""
    from fastapi import FastAPI

    app = FastAPI()
    # two distinct endpoints on the same wp route+method = duplicate
    app.add_api_route("/api/workpapers/{wp_id}/dup-new", _gate_handler, methods=["GET"])
    app.add_api_route("/api/workpapers/{wp_id}/dup-new", _bare_handler, methods=["GET"])
    ledger = {
        "entries": [
            {
                "kind": "http",
                "entrypoint": "x:y",
                "route": "/api/workpapers/{wp_id}/dup-new",
                "method": "GET",
                "family": "detail",
                "action": "read",
                "wp_bound": True,
                "gate": "gated",
                "matrix": "workpaper.dedicated_subroute/dedicated_read",
                "test_ids": ["x"],
            }
        ],
        "migration_head": "V112",
    }
    f = cg.check_drift(app=app, ledger=ledger)
    assert any("dup-new" in m for m in f.duplicate_unresolved)


# ---------------------------------------------------------------------------
# Layer 2 — live-app invariants against the committed ledger
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def _real_app():
    from app.main import app

    return app


def test_no_drift_on_committed_ledger(_real_app):
    """Production surface ⇔ committed ledger: bidirectionally equal, no fake-pass."""
    f = cg.check_drift(app=_real_app, ledger=_committed_ledger())
    assert f.is_clean(), f"coverage drift: {f.summary()}"


def test_no_unmigrated_wp_bound_entries_remain():
    """Task 16 finalisation: no wp-bound ledger entry may remain 'unmigrated'."""
    ledger = _committed_ledger()
    leftover = [
        e for e in ledger["entries"] if e.get("wp_bound") and e.get("gate") == "unmigrated"
    ]
    assert leftover == [], f"unmigrated wp-bound entries remain: {[e['entrypoint'] for e in leftover]}"


def test_native_authz_ledger_entries_have_native_dependency(_real_app):
    """Every ledger entry classified native_authz genuinely enforces native authz."""
    ledger = _committed_ledger()
    live = cg.scan_live_http(_real_app)
    http_native = [
        e for e in ledger["entries"]
        if e.get("kind") == "http" and e.get("gate") == "native_authz"
    ]
    assert http_native, "expected native_authz http entries in the finalised ledger"
    for e in http_native:
        le = live.get((e["route"], e["method"]))
        assert le is not None, f"native_authz entry not live: {e['route']} {e['method']}"
        assert le.native_authz, f"native_authz claim without native hook: {e['route']} {e['method']}"
        assert e.get("test_ids"), f"native_authz entry missing test_ids: {e['route']}"
    # worker native_authz entries must be in the explicit NONHTTP allowlist.
    worker_native = [
        e for e in ledger["entries"]
        if e.get("kind") in ("worker", "retry", "dead_letter") and e.get("gate") == "native_authz"
    ]
    for e in worker_native:
        assert e["entrypoint"] in cg.NONHTTP_CLASSIFICATION
        assert e.get("classification_reason")


def test_not_applicable_allowlist_is_non_wp_or_project_level(_real_app):
    """wp-bound entries marked not_applicable must be in the explicit allowlist and un-gated."""
    ledger = _committed_ledger()
    live = cg.scan_live_http(_real_app)
    wp_na = [
        e for e in ledger["entries"]
        if e.get("kind") == "http" and e.get("wp_bound") and e.get("gate") == "not_applicable"
    ]
    assert wp_na, "expected explicitly-allowlisted not_applicable wp routes"
    for e in wp_na:
        key = (e["route"], e["method"])
        assert key in cg.NOT_APPLICABLE_WP_ALLOWLIST, f"not_applicable not allowlisted: {key}"
        le = live.get(key)
        assert le is not None and not le.gate_wired, f"not_applicable but code gates: {key}"


def test_deferred_editor_allowlist_mechanism_exists():
    """deferred_editor entries are allowlisted + the editor-security mechanism exists."""
    ledger = _committed_ledger()
    deferred = [
        e for e in ledger["entries"]
        if e.get("kind") == "http" and e.get("gate") == "deferred_editor"
    ]
    assert deferred, "expected deferred_editor entries"
    for e in deferred:
        key = (e["route"], e["method"])
        assert key in cg.DEFERRED_EDITOR_ALLOWLIST, f"deferred_editor not allowlisted: {key}"
        assert e.get("test_ids"), f"deferred_editor missing test_ids: {key}"
    # Editor-security mechanism (Task 11) must be importable and expose token validation.
    from app.services.wp_visibility import editor_security

    assert hasattr(editor_security, "validate_editor_token")


def test_reconcile_is_idempotent(_real_app):
    """Reconciling the committed ledger again yields the same classification set."""
    ledger = _committed_ledger()
    re = cg.reconcile_ledger(app=_real_app, ledger=ledger)
    f = cg.check_drift(app=_real_app, ledger=re)
    assert f.is_clean(), f"reconcile not idempotent / clean: {f.summary()}"
