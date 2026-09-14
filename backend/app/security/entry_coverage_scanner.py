"""Wp-bound entry coverage scanner (Task 1 baseline inventory).

Scans the *real* FastAPI application (``app.main:app``), the router registry
and the worker / retry / dead-letter registries to produce the initial
``wp_bound_entry_coverage.json`` ledger. Every produced entry records ``kind``,
a stable ``entrypoint`` / ``callable``, ``route``/``method``, ``family``,
``action``, ``binding`` (resource resolution hint), ``gate``, ``matrix`` and
stable ``test_ids``.

Baseline rules (do not fake-pass):
  * No unified ``Wp_Bound_Gate`` / ``Action_Matrix`` exists yet, so every
    wp-bound entry has ``gate="unmigrated"`` and ``matrix="unmigrated"``.
  * Non wp-bound entries are still recorded (so the future drift guard can
    reconcile the *complete* production surface) with ``family="non_wp_bound"``
    and ``gate="not_applicable"``.
  * The inventory is produced from the live app / registries, never from a
    hand-maintained document list.

Stdlib-only. Safe to import: building ``app.main:app`` only registers routers;
DB connections and workers start in the lifespan (app startup), not at import.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_THIS = Path(__file__).resolve()
# backend/app/security/entry_coverage_scanner.py -> repo root is parents[3]
_REPO_ROOT = _THIS.parents[3]
_MIGRATIONS_DIR = _REPO_ROOT / "backend" / "migrations"
LEDGER_PATH = _THIS.parent / "wp_bound_entry_coverage.json"

_UNMIGRATED = "unmigrated"
_NOT_APPLICABLE = "not_applicable"

# Migration head reconciliation (Task 2 legitimately applied this feature's own
# migration). ``V112`` is the pre-feature baseline snapshot frozen at Task 1;
# ``V115__wp_visibility_delegation_history_audit_epoch.sql`` is this feature's
# own migration applied by Task 2. The drift check accepts either the frozen
# baseline artifact (V112) or the feature-applied live head (V115). This does
# NOT weaken the anti-fake-pass intent, which is enforced solely by the
# gate/matrix/test_ids invariants below.
BASELINE_MIGRATION_HEAD = "V112"
FEATURE_APPLIED_MIGRATION = "V115"
ACCEPTED_MIGRATION_HEADS: frozenset[str] = frozenset(
    {BASELINE_MIGRATION_HEAD, FEATURE_APPLIED_MIGRATION}
)

# Entry families derived from Requirement 8.5-8.16.
ENTRY_FAMILIES: tuple[str, ...] = (
    "list",
    "detail",
    "render_config",
    "html",
    "checklist",
    "file",
    "download",
    "preview",
    "import",
    "export",
    "attachment",
    "onlyoffice_wopi",
    "read",
    "save",
    "callback",
    "convert",
    "review",
    "comment",
    "status",
    "ai",
    "procedure_task",
    "version",
    "history",
    "snapshot",
    "cross_ref",
    "bulk",
    "background",
    # not part of the wp-bound scope, but recorded for a complete surface:
    "non_wp_bound",
    "infra",
)

_PARAM_RE = re.compile(r"\{([^}:]+)")

# Workers that plausibly touch Wp_Bound_Resource at execution time and must be
# re-gated by later tasks (Task 10). Others are recorded but marked not wp-bound
# at baseline. This is a conservative, honest baseline; Task 10/16 re-scan and
# reclassify with the real gate wiring.
_WP_BOUND_WORKERS: dict[str, str] = {
    "procedure_dispatcher_worker": (
        "dispatches ProcedureRowTask notification/task events; must re-gate on "
        "execution after revocation (Task 10)"
    ),
}


# ---------------------------------------------------------------------------
# Classification helpers (pure functions — unit tested directly)
# ---------------------------------------------------------------------------
def extract_path_params(path: str) -> list[str]:
    """Return the ordered path parameter names in a route path template."""
    return _PARAM_RE.findall(path or "")


def is_wp_bound(path: str, params: Iterable[str], module: str) -> bool:
    """Heuristic: can this route be resolved to a concrete底稿 resource?

    Biased toward inclusion for anything with a concrete wp signal so that no
    real wp-bound gap is hidden. Project-level ledger/account-chart imports
    without a wp signal are intentionally excluded.
    """
    p = (path or "").lower()
    pset = set(params or ())

    # /wopi/files/{file_id} family (editor file protocol).
    if p.startswith("/wopi") or "/wopi/" in p:
        return True
    # Explicit wp identifiers in the path.
    if pset & {"wp_id", "wp_index_id"}:
        return True
    # Attachments are wp-bound resources (attachment -> links -> wp).
    if "attachment_id" in pset:
        return True
    # Workpaper path segments.
    if "/workpapers/" in p or "/working-papers/" in p or p.endswith("/workpaper") or "/workpaper/" in p:
        return True
    # Editor / render / content / checklist / procedure signals.
    if "onlyoffice" in p or "render-config" in p or "checklist-responses" in p:
        return True
    if "parsed-data" in p:
        return True
    if any(seg in p for seg in ("procedure-status", "procedure-categories", "sync-procedure", "procedure-tables")):
        return True
    # Bulk tab operates on a set of底稿.
    if "bulk-tab" in p:
        return True
    return False


def classify_family(path: str, method: str, params: Iterable[str], wp_bound: bool) -> str:
    """Assign the Entry_Family for a route. Non wp-bound -> non_wp_bound/infra."""
    p = (path or "").lower()
    if not wp_bound:
        if p in ("/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect", "/metrics", "/api/version"):
            return "infra"
        return "non_wp_bound"

    # Ordered, most-specific-first rules for wp-bound routes.
    if p.endswith("callback") or "-callback" in p or "/callback" in p:
        return "callback"
    if "onlyoffice" in p or p.startswith("/wopi") or "/wopi/" in p:
        return "onlyoffice_wopi"
    if "convert" in p or "sync-from-onlyoffice" in p:
        return "convert"
    if "bulk-tab" in p:
        return "bulk"
    if "download" in p:
        return "download"
    if "preview" in p:
        return "preview"
    if "export" in p:
        return "export"
    if "import" in p:
        return "import"
    if "attachment" in p:
        return "attachment"
    if "render-config" in p:
        return "render_config"
    if "checklist" in p:
        return "checklist"
    if "parsed-data" in p:
        return "html"
    if p.endswith("/status") or "/procedure-status" in p:
        # procedure-status is a procedure page; plain status is file/index status
        if "procedure" in p:
            return "procedure_task"
        return "status"
    if any(seg in p for seg in ("/ai/", "/ai-generate", "ai/generate", "generate-notes", "summarize", "/ocr", "-ocr")):
        return "ai"
    if any(seg in p for seg in ("procedure-categories", "sync-procedure", "procedure-tables", "/procedure")):
        return "procedure_task"
    if "compare" in p or "snapshot" in p or "time-machine" in p:
        return "snapshot"
    if "restore" in p or "/versions" in p or p.endswith("/version"):
        return "version"
    if "history" in p:
        return "history"
    if any(seg in p for seg in ("cross-ref", "references", "cross-wp", "ref-index")):
        return "cross_ref"
    if any(seg in p for seg in ("review", "conclusion", "sign", "opinion")):
        return "review"
    if "comment" in p or "annotation" in p or "批注" in p:
        return "comment"
    # Fallbacks by method.
    m = (method or "").upper()
    if m in ("GET", "HEAD"):
        return "detail"
    return "save"


def classify_action(method: str, family: str) -> str:
    """Coarse action category for the baseline ledger."""
    if family in ("download", "preview", "export", "import", "convert", "callback", "bulk"):
        return family
    if family == "onlyoffice_wopi":
        return "editor"
    if family == "ai":
        return "ai"
    if family == "review":
        return "review"
    if family == "comment":
        return "comment"
    m = (method or "").upper()
    if m in ("GET", "HEAD"):
        return "read"
    if m == "POST":
        return "create"
    if m in ("PUT", "PATCH"):
        return "update"
    if m == "DELETE":
        return "delete"
    return m.lower() or "unknown"


def binding_hint(path: str, params: Iterable[str], wp_bound: bool) -> str:
    """Resource resolution hint (Req 13.2 '资源解析方式')."""
    if not wp_bound:
        return "n/a"
    p = (path or "").lower()
    pset = set(params or ())
    if p.startswith("/wopi") or "/wopi/" in p:
        return "wopi_file_id"
    if "attachment_id" in pset:
        return "attachment_id"
    if "wp_id" in pset:
        return "wp_id"
    if "wp_index_id" in pset:
        return "wp_index_id"
    if "bulk-tab" in p:
        return "bulk_manifest"
    if "table_code" in pset or "procedure" in p:
        return "server_resolved_procedure"
    return "server_resolved"


# ---------------------------------------------------------------------------
# Route + worker enumeration
# ---------------------------------------------------------------------------
def _stable_entrypoint(endpoint: Any) -> tuple[str, str]:
    """Return (entrypoint, callable_name) for an endpoint function."""
    if endpoint is None:
        return ("unknown", "unknown")
    module = getattr(endpoint, "__module__", "unknown")
    name = getattr(endpoint, "__qualname__", None) or getattr(endpoint, "__name__", "unknown")
    return (f"{module}:{name}", name)


def iter_http_entries(app: Any) -> list[dict[str, Any]]:
    """Enumerate a unique record per (route, method) from the live FastAPI app.

    Req 13.1 requires a unique ledger record per route+method. Production has a
    handful of genuine duplicate registrations (distinct endpoints on the same
    route+method); these are recorded honestly on the single record via
    ``duplicate_registration`` + ``duplicate_entrypoints`` instead of being
    silently dropped.
    """
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for route in app.routes:
        methods = getattr(route, "methods", None)
        if not methods:
            continue  # mounts / websockets without methods
        path = getattr(route, "path", "") or ""
        endpoint = getattr(route, "endpoint", None)
        entrypoint, callable_name = _stable_entrypoint(endpoint)
        module = getattr(endpoint, "__module__", "unknown") if endpoint else "unknown"
        params = extract_path_params(path)
        wp_bound = is_wp_bound(path, params, module)
        family = classify_family(path, sorted(methods)[0], params, wp_bound)
        for method in sorted(methods):
            key = (path, method)
            existing = by_key.get(key)
            if existing is not None:
                # Genuine duplicate registration — record collision, keep unique row.
                if entrypoint not in existing["duplicate_entrypoints"]:
                    existing["duplicate_entrypoints"].append(entrypoint)
                existing["duplicate_registration"] = (
                    len(existing["duplicate_entrypoints"]) > 1
                )
                continue
            by_key[key] = {
                "kind": "http",
                "entrypoint": entrypoint,
                "callable": callable_name,
                "route": path,
                "method": method,
                "family": family,
                "action": classify_action(method, family),
                "wp_bound": wp_bound,
                "binding": binding_hint(path, params, wp_bound),
                "gate": _UNMIGRATED if wp_bound else _NOT_APPLICABLE,
                "matrix": _UNMIGRATED if wp_bound else _NOT_APPLICABLE,
                "test_ids": [],
                "duplicate_entrypoints": [entrypoint],
                "duplicate_registration": False,
            }
    # Collapse single-entrypoint duplicate metadata to keep rows lean.
    entries: list[dict[str, Any]] = []
    for e in by_key.values():
        if not e["duplicate_registration"]:
            e.pop("duplicate_entrypoints", None)
            e.pop("duplicate_registration", None)
        entries.append(e)
    return entries


def iter_worker_entries() -> list[dict[str, Any]]:
    """Enumerate non-HTTP executors: worker run loops + retry/dead-letter callables.

    Discovered from ``app.workers`` package (worker ``run`` loops) plus the known
    retry / dead-letter callables. Kept import-light: only reads the workers
    package, no worker is started.
    """
    import importlib
    import inspect
    import pkgutil

    entries: list[dict[str, Any]] = []
    workers_pkg = importlib.import_module("app.workers")
    for info in pkgutil.iter_modules(workers_pkg.__path__, prefix="app.workers."):
        leaf = info.name.rsplit(".", 1)[-1]
        if leaf.startswith("_") or leaf in ("worker_helpers",):
            continue
        try:
            mod = importlib.import_module(info.name)
        except Exception:  # noqa: BLE001 — record as unresolved rather than skip
            entries.append(
                {
                    "kind": "worker",
                    "entrypoint": f"{info.name}:run",
                    "callable": "run",
                    "route": None,
                    "method": None,
                    "family": "background",
                    "action": "worker_loop",
                    "wp_bound": False,
                    "binding": "import_failed",
                    "gate": _NOT_APPLICABLE,
                    "matrix": _NOT_APPLICABLE,
                    "test_ids": [],
                    "notes": "module import failed at scan time",
                }
            )
            continue
        run_fn = getattr(mod, "run", None)
        if run_fn is None or not (inspect.iscoroutinefunction(run_fn) or callable(run_fn)):
            continue
        wp_note = _WP_BOUND_WORKERS.get(leaf)
        wp_bound = wp_note is not None
        entry = {
            "kind": "worker",
            "entrypoint": f"{info.name}:run",
            "callable": "run",
            "route": None,
            "method": None,
            "family": "background",
            "action": "worker_loop",
            "wp_bound": wp_bound,
            "binding": "persistent_binding" if wp_bound else "n/a",
            "gate": _UNMIGRATED if wp_bound else _NOT_APPLICABLE,
            "matrix": _UNMIGRATED if wp_bound else _NOT_APPLICABLE,
            "test_ids": [],
        }
        if wp_note:
            entry["notes"] = wp_note
        entries.append(entry)

    # Known retry / dead-letter callables (recorded for Req 13.13/13.14 baseline).
    entries.append(
        {
            "kind": "retry",
            "entrypoint": "app.workers.audit_log_writer_worker:_consume_retry_queue",
            "callable": "_consume_retry_queue",
            "route": None,
            "method": None,
            "family": "background",
            "action": "retry",
            "wp_bound": False,
            "binding": "n/a",
            "gate": _NOT_APPLICABLE,
            "matrix": _NOT_APPLICABLE,
            "test_ids": [],
            "notes": "audit-log write retry queue consumer (not wp content)",
        }
    )
    entries.append(
        {
            "kind": "dead_letter",
            "entrypoint": "app.services.import_event_outbox_service:ImportEventOutboxService.replay_pending",
            "callable": "replay_pending",
            "route": None,
            "method": None,
            "family": "background",
            "action": "dead_letter",
            "wp_bound": False,
            "binding": "n/a",
            "gate": _NOT_APPLICABLE,
            "matrix": _NOT_APPLICABLE,
            "test_ids": [],
            "notes": "ledger import outbox DLQ mover (event_outbox_dlq); not wp content",
        }
    )
    return entries


def _detect_migration_head() -> str:
    """Scan backend/migrations for the highest V###.sql file (real, not static)."""
    best = 0
    if _MIGRATIONS_DIR.is_dir():
        for f in _MIGRATIONS_DIR.glob("V*.sql"):
            m = re.match(r"V(\d+)", f.stem)
            if m:
                best = max(best, int(m.group(1)))
    return f"V{best:03d}" if best else "unknown"


# ---------------------------------------------------------------------------
# Ledger assembly
# ---------------------------------------------------------------------------
def build_ledger(app: Any | None = None) -> dict[str, Any]:
    """Build the full ledger dict from the live app + worker registries."""
    if app is None:
        from app.main import app as fastapi_app  # heavy import; only on demand

        app = fastapi_app

    http_entries = iter_http_entries(app)
    worker_entries = iter_worker_entries()
    entries = http_entries + worker_entries

    by_family: dict[str, int] = {}
    by_action: dict[str, int] = {}
    by_gate: dict[str, int] = {}
    wp_bound_http = 0
    duplicate_registrations: list[dict[str, Any]] = []
    for e in entries:
        by_family[e["family"]] = by_family.get(e["family"], 0) + 1
        by_action[e["action"]] = by_action.get(e["action"], 0) + 1
        by_gate[e["gate"]] = by_gate.get(e["gate"], 0) + 1
        if e["kind"] == "http" and e["wp_bound"]:
            wp_bound_http += 1
        if e.get("duplicate_registration"):
            duplicate_registrations.append(
                {
                    "route": e["route"],
                    "method": e["method"],
                    "wp_bound": e["wp_bound"],
                    "entrypoints": e["duplicate_entrypoints"],
                }
            )

    return {
        "spec": "procedure-delegation-visibility-isolation",
        "artifact": "wp_bound_entry_coverage.json",
        "generated_by": "app.security.entry_coverage_scanner",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "app_import": "app.main:app",
        "migration_head": _detect_migration_head(),
        "baseline_note": (
            "Inventory-only baseline. No unified Wp_Bound_Gate/Action_Matrix "
            "exists yet, so every wp-bound entry is 'unmigrated'. Do not treat "
            "'unmigrated' as implemented. Regenerate via "
            "`python -m app.security.entry_coverage_scanner`."
        ),
        "families": list(ENTRY_FAMILIES),
        "known_baseline_gaps": {
            "duplicate_route_registrations": len(duplicate_registrations),
            "note": (
                "Duplicate (route,method) registrations bind distinct endpoints; "
                "surfaced for the Route_Drift_Guard (Task 16) to resolve. Recorded "
                "as unmigrated where wp-bound, not implemented."
            ),
            "detail": duplicate_registrations,
        },
        "summary": {
            "entry_total": len(entries),
            "http_total": len(http_entries),
            "http_wp_bound": wp_bound_http,
            "http_non_wp_bound": len(http_entries) - wp_bound_http,
            "worker_total": len(worker_entries),
            "duplicate_route_registrations": len(duplicate_registrations),
            "by_family": dict(sorted(by_family.items())),
            "by_action": dict(sorted(by_action.items())),
            "by_gate": dict(sorted(by_gate.items())),
        },
        "entries": sorted(
            entries,
            key=lambda e: (
                e["kind"],
                e["route"] or e["entrypoint"],
                e["method"] or "",
            ),
        ),
    }


def validate_ledger(ledger: dict[str, Any]) -> list[str]:
    """Return a list of baseline invariant violations (empty == valid)."""
    problems: list[str] = []
    entries = ledger.get("entries")
    if not isinstance(entries, list) or not entries:
        problems.append("ledger has no entries")
        return problems

    seen: set[tuple[str, str, str]] = set()
    for e in entries:
        for key in ("kind", "entrypoint", "family", "action", "gate", "matrix"):
            if key not in e:
                problems.append(f"entry missing '{key}': {e.get('entrypoint')}")
        if e.get("kind") == "http":
            key = ("http", e.get("route") or "", e.get("method") or "")
            if key in seen:
                problems.append(f"duplicate http route+method: {key}")
            seen.add(key)
        # Anti-fake-pass (migration-aware). A wp-bound entry is valid iff it is
        # either still at baseline (gate AND matrix both ``unmigrated``) or fully
        # migrated (gate AND matrix both non-``unmigrated`` AND carrying non-empty
        # stable test_ids). Half-migrated or migrated-without-evidence is rejected.
        # Tasks 9/10/11 migrate their own entries incrementally; Task 16 finalises.
        if e.get("wp_bound"):
            gate = e.get("gate")
            matrix = e.get("matrix")
            gate_base = gate == _UNMIGRATED
            matrix_base = matrix == _UNMIGRATED
            if gate_base or matrix_base:
                if not (gate_base and matrix_base):
                    problems.append(
                        "wp_bound entry half-migrated (gate/matrix must both be "
                        f"unmigrated or both migrated): {e.get('entrypoint')}"
                    )
            else:
                if not e.get("test_ids"):
                    problems.append(
                        "migrated wp_bound entry missing stable test_ids "
                        f"(fake-pass): {e.get('entrypoint')}"
                    )
    head = ledger.get("migration_head")
    if head not in ACCEPTED_MIGRATION_HEADS:
        problems.append(
            "migration_head expected one of "
            f"{sorted(ACCEPTED_MIGRATION_HEADS)} (V112 baseline / V115 feature-applied), "
            f"got {head}"
        )
    return problems


def write_ledger(app: Any | None = None, path: Path | None = None) -> dict[str, Any]:
    """Build and persist the ledger JSON. Returns the ledger dict."""
    ledger = build_ledger(app)
    out = path or LEDGER_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return ledger


def _main() -> int:
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows GBK console guard
    except Exception:  # noqa: BLE001
        pass

    ledger = write_ledger()
    problems = validate_ledger(ledger)
    s = ledger["summary"]
    print(f"[entry-coverage] wrote {LEDGER_PATH}")
    print(f"  migration_head : {ledger['migration_head']}")
    print(f"  entry_total    : {s['entry_total']}")
    print(f"  http_total     : {s['http_total']} (wp_bound={s['http_wp_bound']}, non={s['http_non_wp_bound']})")
    print(f"  worker_total   : {s['worker_total']}")
    print(f"  by_gate        : {s['by_gate']}")
    print("  wp_bound by family:")
    fam: dict[str, int] = {}
    for e in ledger["entries"]:
        if e.get("wp_bound"):
            fam[e["family"]] = fam.get(e["family"], 0) + 1
    for k, v in sorted(fam.items()):
        print(f"    {k:16s}: {v}")
    if problems:
        print(f"[entry-coverage] VALIDATION PROBLEMS ({len(problems)}):")
        for p in problems[:20]:
            print(f"  - {p}")
        return 1
    print("[entry-coverage] baseline invariants OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
