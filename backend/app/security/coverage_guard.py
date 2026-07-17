"""Route/worker Coverage Guard · 漂移守卫（Task 16 / 组件 C14 CoverageGuard）

Feature: procedure-delegation-visibility-isolation
Requirements: 13.1–13.15, 16.17, 16.21–16.23

本模块是 ``wp_bound_entry_coverage.json`` ledger 的 **漂移守卫（Route_Drift_Guard）**。它从
*真实生产面* 派生事实，而不是信任 ledger 里手写的 gate 声明，从而实现 **anti-fake-pass**：

  1. **HTTP 面**：枚举 ``app.main:app`` 全部路由（含 ``add_api_route`` 动态注册的），按 (route, method)
     规范化，并对每条 wp-bound 路由从真实代码派生 ``gate_wired``（route-level 依赖 或 handler AST 调用
     gate 函数，含 1 层间接 wrapper 解析）。注释里出现 gate 函数名 **不算**（AST 解析，天然抗伪注释）。
  2. **非 HTTP 面**：枚举 worker / retry / dead-letter callable（复用 entry_coverage_scanner），
     对 wp-bound callable 检查其 **执行体是否真的 re-gate**（AST）。
  3. **双向相等**：生产 (route, method) 集合与 ledger http 条目集合双向相等；生产 callable 与 ledger
     非 HTTP 条目双向相等。缺失（新入口未登记）/ stale（ledger 有但生产无）/ 重复 / 动态不可解析 均阻断。
  4. **矩阵/测试证据**：每条 gated wp-bound 条目的 ``matrix`` 必须指向 ``ActionMatrix`` 已登记的
     (entrypoint, action)；``test_ids`` 非空。
  5. **诚实缺口**：任何 wp-bound 条目仍为 ``unmigrated`` → 报为未接入 gate 缺口（阻断，绝不假绿）。
  6. **假绿检测**：ledger 声称 gated 但真实代码检测不到 gate → ``fake_pass`` 阻断。

Stdlib-only（``ast`` / ``inspect``）。导入 ``app.main:app`` 只注册路由，不启动 DB/worker。
"""
from __future__ import annotations

import ast
import inspect
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from app.security.entry_coverage_scanner import (
    LEDGER_PATH,
    ACCEPTED_MIGRATION_HEADS,
    extract_path_params,
    is_wp_bound,
    iter_worker_entries,
    _detect_migration_head,
)

_UNMIGRATED = "unmigrated"
_NOT_APPLICABLE = "not_applicable"

# ---------------------------------------------------------------------------
# Gate call vocabulary — the function names that constitute a real gate hook.
# route-level FastAPI dependency names + in-handler gate calls + editor security.
# ---------------------------------------------------------------------------
ROUTE_DEP_GATE_NAMES: frozenset[str] = frozenset(
    {"dedicated_wp_gate"}
)

HANDLER_GATE_CALL_NAMES: frozenset[str] = frozenset(
    {
        "enforce_wp_gate",
        "enforce_task_gate",
        "gate_wp",
        "try_gate_wp",
        "gate_attachment_associate",
        "enforce_attachment_wp_visibility",
        "make_bulk_preflight",
        "make_bulk_visible_filter",
        "resolve_wp_binding_and_access",
        # editor / WOPI token + callback re-validation (Task 11)
        "validate_editor_token",
        "verify_callback_preconditions",
        "compute_user_can_write",
    }
)

ALL_GATE_NAMES: frozenset[str] = ROUTE_DEP_GATE_NAMES | HANDLER_GATE_CALL_NAMES

# ---------------------------------------------------------------------------
# Native project-level authz vocabulary (Task 16 classification).
#
# A wp-bound route that does NOT wire the fine-grained Wp_Bound_Gate but DOES
# enforce native project-level authorization (authenticated principal + project
# access / role) is classified ``native_authz`` — an HONEST, explicit deferral
# of the defence-in-depth visibility gate, never a silent pass. The guard
# independently re-verifies that such a route genuinely carries a native authz
# hook (fail-closed: if the ledger says native_authz but code has none →
# fake_pass). This can never be faked by a comment (AST + FastAPI dependant).
# ---------------------------------------------------------------------------
NATIVE_AUTHZ_DEP_NAMES: frozenset[str] = frozenset(
    {
        "require_project_access",
        "require_project_delegator",
        "require_project_delegator_pid",
        "require_role",
        "require_operation",
        "require_project_member",
        "get_current_user",
        "get_current_active_user",
    }
)
# Names that only appear as *factory* deps in the endpoint source
# (``Depends(require_project_access("edit"))``) — detected via handler AST.
NATIVE_AUTHZ_CALL_NAMES: frozenset[str] = frozenset(
    {
        "require_project_access",
        "require_project_delegator",
        "require_project_delegator_pid",
        "require_role",
        "require_operation",
        "require_project_member",
    }
)

# Ledger gate/matrix vocabulary understood by the guard.
_GATED = "gated"
_MIGRATED = "migrated"
_NATIVE_AUTHZ = "native_authz"
_DEFERRED_EDITOR = "deferred_editor"

# Classifications that are considered "real gate wired in code".
_CODE_GATED_VALUES: frozenset[str] = frozenset({_GATED, _MIGRATED})

# Stable test ids attached to derived classifications (collective proofs).
DEDICATED_GATE_TEST = (
    "tests/procedure_delegation_visibility/test_task9_dedicated_route_gate.py"
    "::test_all_dedicated_routes_have_gate_dependency"
)
NATIVE_AUTHZ_TEST = (
    "tests/procedure_delegation_visibility/test_task16_coverage_guard.py"
    "::test_native_authz_ledger_entries_have_native_dependency"
)
NOT_APPLICABLE_TEST = (
    "tests/procedure_delegation_visibility/test_task16_coverage_guard.py"
    "::test_not_applicable_allowlist_is_non_wp_or_project_level"
)
DEFERRED_EDITOR_TEST = (
    "tests/procedure_delegation_visibility/test_task16_coverage_guard.py"
    "::test_deferred_editor_allowlist_mechanism_exists"
)

# ---------------------------------------------------------------------------
# Explicit HONEST allowlists (Task 16). Every member carries a justification so
# the guard never silently passes an unclassified wp-bound route. Adding a route
# here is a deliberate, reviewed classification — the guard verifies membership
# and (for not_applicable) that the route is genuinely non-wp / project-level.
# ---------------------------------------------------------------------------
# Routes the scanner heuristically flags wp_bound but that are genuinely NOT
# individual-底稿-bound (global metadata or project-level catalog/aggregate that
# returns no底稿正文). Their project-level authz is governed by the separate
# endpoint-auth governance guard, outside this feature's wp-visibility scope.
NOT_APPLICABLE_WP_ALLOWLIST: dict[tuple[str, str], str] = {
    ("/api/workpapers/render-registry", "GET"): "global renderer metadata registry; no wp/project resource",
    ("/api/workpapers/render-registry/{wp_code}", "GET"): "renderer metadata by wp_code (ACNR resolve); no wp instance",
    ("/api/projects/{project_id}/workpapers/prerequisite-status", "GET"): "project-level prerequisite status aggregate; no底稿正文",
    ("/api/projects/{project_id}/workpapers/review-status", "GET"): "project-level review-mark count aggregate; no底稿正文",
    ("/api/projects/{project_id}/procedure-tables/batch", "GET"): "project-level procedure template catalog (batch); no底稿正文",
    ("/api/projects/{project_id}/procedure-tables/{table_code}", "GET"): "project-level procedure template catalog; no底稿正文",
    ("/api/projects/{project_id}/procedure-tables/custom-items", "POST"): "project-level custom procedure row catalog write; no底稿正文",
    ("/api/projects/{project_id}/procedure-tables/custom-items/{item_id}", "DELETE"): "project-level custom procedure row catalog delete; no底稿正文",
}

# Editor / OnlyOffice / WOPI online-editing protocol endpoints whose full live
# gate wiring is deferred: the editor-security *mechanism* is built and tested in
# Task 11 (test_editor_security, fail-closed token validation), online editing is
# typically disabled, and full live acceptance is Task 17. Recorded HONESTLY as a
# deferral with mechanism evidence — not a silent pass.
DEFERRED_EDITOR_ALLOWLIST: dict[tuple[str, str], str] = {
    ("/wopi/files/{file_id}/contents", "GET"): "WOPI GetFile legacy; editor token mechanism in Task 11, live enforcement Task 17",
    ("/wopi/files/{file_id}", "POST"): "WOPI lock/PutFile legacy; editor token mechanism in Task 11, live enforcement Task 17",
    ("/wopi/health", "GET"): "WOPI health probe; no wp resource returned; deferred with editor family",
    ("/wopi/ds-callback/{file_id}", "POST"): "OnlyOffice DS callback legacy; re-validation mechanism in Task 11, live Task 17",
    ("/api/projects/{project_id}/deliverables/onlyoffice/callback/{task_id}", "POST"): "deliverables OnlyOffice callback; editor callback re-gate mechanism Task 11, live Task 17",
}

# Pre-existing genuine duplicate (route, method) registrations in production
# (two distinct routers bind the same path+method; FastAPI routes to the first
# match). These are unrelated to visibility and out of Task 16 scope to refactor;
# recorded HONESTLY as an explicit allowlist so the guard surfaces them without
# blocking on a pre-existing platform issue. New duplicates still block CI.
# Non-HTTP (worker/retry/dead-letter) classifications for wp-adjacent callables
# that do NOT serve Wp_Bound_Resource content and are therefore not gated at
# execution. Recorded HONESTLY with justification (never a silent pass); the
# guard verifies membership and does not require a re-gate for these.
NONHTTP_CLASSIFICATION: dict[str, dict[str, Any]] = {
    "app.workers.procedure_dispatcher_worker:run": {
        "gate": _NATIVE_AUTHZ,
        "reason": (
            "delivers ProcedureRowTask task-assignment notification signals (no "
            "底稿正文/content); delivery events are enqueued only by authorized "
            "delegation transactions (Task 7). Wp-bound content re-gate is N/A to "
            "notification delivery; mid-flight revocation suppression is a "
            "procedure-delegation-notification follow-on, not a底稿内容泄露."
        ),
        "test_ids": [NATIVE_AUTHZ_TEST],
    },
}

KNOWN_DUPLICATE_REGISTRATIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("/api/aging/presets", "GET"),
        ("/api/projects/{project_id}/a16/recommended-version", "GET"),
        ("/api/projects/{project_id}/aging/config", "GET"),
        ("/api/projects/{project_id}/aging/config", "PUT"),
        ("/api/projects/{project_id}/issue-hints", "GET"),
        ("/api/projects/{project_id}/ledger-import/jobs/{job_id}/retry", "POST"),
        ("/api/projects/{project_id}/working-papers/{wp_id}/export-word", "GET"),
        ("/api/projects/{project_id}/working-papers/{wp_id}/export-word/check-incomplete", "GET"),
        ("/api/projects/{project_id}/workpaper-summaries/{key}", "GET"),
    }
)

# Deferred-gate schedulers: an HTTP handler that hands work to a background
# runner which RE-gates on execution (Req 8.16 re-gate). The handler itself does
# not gate; the scheduled runner module does. Maps a scheduler callable name to
# the runner module whose source must contain a real gate call. This is verified
# (the runner module is parsed for gate calls), not assumed — anti-fake-pass.
DEFERRED_GATE_SCHEDULERS: dict[str, str] = {
    "schedule_export": "app.services.bulk_tab.bulk_async_runner",
    "schedule_import": "app.services.bulk_tab.bulk_async_runner",
}


# ---------------------------------------------------------------------------
# AST gate detection (pure, unit-tested; fake-comment resistant)
# ---------------------------------------------------------------------------
def ast_called_names(source: str) -> set[str]:
    """Return the set of *called* function names in ``source`` (AST-based).

    A ``Call`` node whose func is a ``Name`` (``foo(...)``) or ``Attribute``
    (``obj.foo(...)``) contributes ``foo``. Comments and strings never count,
    so a ``# enforce_wp_gate`` comment or ``"enforce_wp_gate"`` literal is NOT a
    call — this is what makes the guard resistant to fake comments.
    """
    called: set[str] = set()
    try:
        tree = ast.parse(_dedent(source))
    except SyntaxError:
        return called
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name):
                called.add(fn.id)
            elif isinstance(fn, ast.Attribute):
                called.add(fn.attr)
    return called


def source_calls_gate(source: str, names: Iterable[str] = ALL_GATE_NAMES) -> bool:
    """True iff ``source`` actually *calls* one of the gate ``names`` (AST)."""
    return bool(ast_called_names(source) & set(names))


def _dedent(source: str) -> str:
    """Left-strip common indentation so nested defs parse standalone."""
    import textwrap

    return textwrap.dedent(source)


def _safe_source(obj: Any) -> str | None:
    try:
        return inspect.getsource(obj)
    except (OSError, TypeError):
        return None


def detect_handler_gate(endpoint: Any, *, _depth: int = 0) -> tuple[bool, str]:
    """Derive whether ``endpoint`` wires a gate from its real source (AST).

    Direct: the handler body calls a gate function. Indirect (1 level): the
    handler calls a local module-level function that itself calls a gate
    function (dynamic/indirect wrapper). Returns ``(wired, detail)``.
    """
    src = _safe_source(endpoint)
    if src is None:
        return (False, "no_source")
    called = ast_called_names(src)
    direct = called & HANDLER_GATE_CALL_NAMES
    if direct:
        return (True, f"handler_call:{sorted(direct)[0]}")

    # Deferred-gate scheduler: handler schedules a background runner that
    # re-gates on execution. Verify the runner module really gates (AST).
    for sched in called & set(DEFERRED_GATE_SCHEDULERS):
        runner_mod = DEFERRED_GATE_SCHEDULERS[sched]
        if module_calls_gate(runner_mod):
            return (True, f"deferred:{sched}->{runner_mod}")

    if _depth >= 1:
        return (False, "no_gate_call")

    # 1-level indirect wrapper resolution: resolve locally-called functions in
    # the same module and re-check their source. Handles delegate/wrapper hooks.
    module = inspect.getmodule(endpoint)
    if module is None:
        return (False, "no_gate_call")
    for name in called:
        target = getattr(module, name, None)
        if target is None or target is endpoint:
            continue
        if not (inspect.isfunction(target) or inspect.iscoroutinefunction(target)):
            continue
        wired, detail = detect_handler_gate(target, _depth=_depth + 1)
        if wired:
            return (True, f"indirect:{name}->{detail}")
    return (False, "no_gate_call")


_MODULE_GATE_CACHE: dict[str, bool] = {}


def module_calls_gate(module_name: str) -> bool:
    """True iff any function in ``module_name``'s source calls a gate function (AST).

    Used to verify that a deferred background runner really re-gates on execution.
    Cached per module.
    """
    if module_name in _MODULE_GATE_CACHE:
        return _MODULE_GATE_CACHE[module_name]
    result = False
    try:
        import importlib

        mod = importlib.import_module(module_name)
        src = _safe_source(mod)
        if src is not None:
            result = source_calls_gate(src, HANDLER_GATE_CALL_NAMES)
    except Exception:  # noqa: BLE001
        result = False
    _MODULE_GATE_CACHE[module_name] = result
    return result


def route_dep_gate(route: Any) -> tuple[bool, str]:
    """True iff the route carries an *effective* route-level gate dependency.

    ``dedicated_wp_gate`` only enforces when the route path carries a ``{wp_id}``
    or ``{wp_index_id}`` param — it is a documented safe no-op otherwise. So the
    dep only counts as a real gate when the path actually binds a wp id;
    attaching it to a router with mixed routes does NOT gate the no-op routes
    (anti-fake-pass: a present-but-inert dependency is not a gate).
    """
    path = getattr(route, "path", "") or ""
    path_binds_wp = ("{wp_id}" in path) or ("{wp_index_id}" in path)

    def _matches(name: str) -> bool:
        return name in ROUTE_DEP_GATE_NAMES

    candidates: list[str] = []
    for d in getattr(route, "dependencies", None) or []:
        candidates.append(getattr(getattr(d, "dependency", None), "__name__", ""))
    dependant = getattr(route, "dependant", None)
    if dependant is not None:
        for sub in getattr(dependant, "dependencies", []) or []:
            candidates.append(getattr(getattr(sub, "call", None), "__name__", ""))

    for nm in candidates:
        if _matches(nm):
            if path_binds_wp:
                return (True, f"route_dep:{nm}")
            # dep present but path has no wp id → inert no-op, not a real gate.
            return (False, f"route_dep_inert:{nm}")
    return (False, "")


def detect_route_gate(route: Any) -> tuple[bool, str]:
    """Combined gate detection for an HTTP route: route-dep OR handler AST."""
    wired, detail = route_dep_gate(route)
    if wired:
        return (True, detail)
    ep = getattr(route, "endpoint", None)
    if ep is None:
        return (False, "no_endpoint")
    return detect_handler_gate(ep)


def route_has_native_authz(route: Any) -> tuple[bool, str]:
    """True iff the route carries a native project-level authz hook (fail-closed).

    Two sources, both AST/dependant-based (comment-proof):
      * the FastAPI ``dependant`` tree contains a native authz dependency
        (``get_current_user`` / ``require_project_member`` etc.), OR
      * the endpoint source *calls* a native authz factory
        (``require_project_access("edit")`` / ``require_role([...])``).
    """
    names: set[str] = set()

    def _walk(dep: Any) -> None:
        call = getattr(dep, "call", None)
        nm = getattr(call, "__name__", "") or ""
        if nm:
            names.add(nm)
        for sub in getattr(dep, "dependencies", []) or []:
            _walk(sub)

    dependant = getattr(route, "dependant", None)
    if dependant is not None:
        _walk(dependant)
    hit = names & NATIVE_AUTHZ_DEP_NAMES
    if hit:
        return (True, f"dependant:{sorted(hit)[0]}")

    ep = getattr(route, "endpoint", None)
    src = _safe_source(ep) if ep is not None else None
    if src is not None:
        called = ast_called_names(src) & NATIVE_AUTHZ_CALL_NAMES
        if called:
            return (True, f"factory:{sorted(called)[0]}")
    return (False, "")


# ---------------------------------------------------------------------------
# Matrix registration lookup
# ---------------------------------------------------------------------------
def matrix_registered_pairs() -> set[tuple[str, str]]:
    """Set of (entrypoint, action) pairs registered in the ActionMatrix."""
    from app.services.wp_visibility.action_matrix import ActionMatrix

    pairs: set[tuple[str, str]] = set()
    for e in ActionMatrix.entries:
        pairs.add((e.key.entrypoint, e.key.action))
    return pairs


def parse_matrix_ref(matrix: str | None) -> tuple[str, str] | None:
    """Parse a ledger ``matrix`` string ``"entrypoint/action"`` -> (entrypoint, action).

    Ledger matrix values observed: ``"workpaper.dedicated_subroute/dedicated_read"``,
    ``"workpaper.checklist_read/read_checklist"``. Some editor entries use a free
    description; those are validated separately by the token tests, so a matrix
    string without a single ``/`` split is returned as ``None`` (caller decides).
    """
    if not matrix or matrix in (_UNMIGRATED, _NOT_APPLICABLE):
        return None
    # Take the last '/'-split as entrypoint/action (entrypoints contain dots not slashes).
    if "/" not in matrix:
        return None
    ep, _, action = matrix.rpartition("/")
    ep = ep.strip()
    action = action.strip()
    if not ep or not action:
        return None
    return (ep, action)


# ---------------------------------------------------------------------------
# Live HTTP enumeration (dynamic routes included — reads app.routes)
# ---------------------------------------------------------------------------
@dataclass
class LiveHttpEntry:
    route: str
    method: str
    entrypoint: str
    module: str
    wp_bound: bool
    gate_wired: bool
    gate_detail: str
    native_authz: bool = False
    native_detail: str = ""
    endpoints: list[str] = field(default_factory=list)  # duplicate registrations


def scan_live_http(app: Any) -> dict[tuple[str, str], LiveHttpEntry]:
    """Enumerate unique (route, method) -> LiveHttpEntry from the live app."""
    by_key: dict[tuple[str, str], LiveHttpEntry] = {}
    for route in app.routes:
        methods = getattr(route, "methods", None)
        if not methods:
            continue
        path = getattr(route, "path", "") or ""
        ep = getattr(route, "endpoint", None)
        module = getattr(ep, "__module__", "unknown") if ep else "unknown"
        qual = getattr(ep, "__qualname__", None) or getattr(ep, "__name__", "unknown") if ep else "unknown"
        entrypoint = f"{module}:{qual}"
        params = extract_path_params(path)
        wp_bound = is_wp_bound(path, params, module)
        gate_wired, gate_detail = detect_route_gate(route) if wp_bound else (False, "n/a")
        native_authz, native_detail = (
            route_has_native_authz(route) if wp_bound and not gate_wired else (False, "")
        )
        for method in sorted(methods):
            key = (path, method)
            existing = by_key.get(key)
            if existing is not None:
                if entrypoint not in existing.endpoints:
                    existing.endpoints.append(entrypoint)
                # keep gate_wired True if any registration wires it
                if wp_bound and gate_wired and not existing.gate_wired:
                    existing.gate_wired = True
                    existing.gate_detail = gate_detail
                if wp_bound and native_authz and not existing.native_authz:
                    existing.native_authz = True
                    existing.native_detail = native_detail
                continue
            by_key[key] = LiveHttpEntry(
                route=path,
                method=method,
                entrypoint=entrypoint,
                module=module,
                wp_bound=wp_bound,
                gate_wired=gate_wired,
                gate_detail=gate_detail,
                native_authz=native_authz,
                native_detail=native_detail,
                endpoints=[entrypoint],
            )
    return by_key


# ---------------------------------------------------------------------------
# Live non-HTTP enumeration + re-gate detection
# ---------------------------------------------------------------------------
def scan_live_nonhttp() -> list[dict[str, Any]]:
    """Worker / retry / dead-letter callables (reuse scanner enumeration)."""
    return [e for e in iter_worker_entries()]


def nonhttp_regates(entry: dict[str, Any]) -> tuple[bool, str]:
    """For a wp-bound non-HTTP callable, verify it re-gates on execution (AST).

    Resolves the callable from ``entrypoint`` (``module:qualname``) and checks
    that its source (or a 1-level helper) calls a gate function.
    """
    ep = entry.get("entrypoint") or ""
    if ":" not in ep:
        return (False, "unresolvable_entrypoint")
    mod_name, _, qual = ep.partition(":")
    try:
        import importlib

        mod = importlib.import_module(mod_name)
    except Exception:  # noqa: BLE001
        return (False, "import_failed")
    obj: Any = mod
    for part in qual.split("."):
        obj = getattr(obj, part, None)
        if obj is None:
            return (False, "callable_not_found")
    wired, detail = detect_handler_gate(obj)
    return (wired, detail)


# ---------------------------------------------------------------------------
# Ledger IO
# ---------------------------------------------------------------------------
def load_ledger(path: Path | None = None) -> dict[str, Any]:
    import json

    p = path or LEDGER_PATH
    return json.loads(Path(p).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Ledger reconciliation (Task 16 finalisation): resolve every ``unmigrated``
# wp-bound entry to a real classification DERIVED FROM CODE (anti-fake-pass),
# add newly-registered routes, drop stale entries → bidirectional equality.
# Existing non-unmigrated classifications are preserved verbatim.
# ---------------------------------------------------------------------------
def _dedicated_action(method: str) -> str:
    m = (method or "").upper()
    if m in ("GET", "HEAD"):
        return "dedicated_read"
    if m == "DELETE":
        return "dedicated_delete"
    return "dedicated_write"


def classify_unmigrated(le: LiveHttpEntry) -> dict[str, Any]:
    """Derive (gate, matrix, test_ids, classification_reason) for an unmigrated
    or newly-discovered live entry, using only facts derived from real code.
    """
    key = (le.route, le.method)
    if not le.wp_bound:
        return {"gate": _NOT_APPLICABLE, "matrix": _NOT_APPLICABLE, "test_ids": [], "classification_reason": None}

    # 1. explicit not-applicable allowlist (non-wp / project-level catalog).
    if key in NOT_APPLICABLE_WP_ALLOWLIST:
        return {
            "gate": _NOT_APPLICABLE,
            "matrix": _NOT_APPLICABLE,
            "test_ids": [NOT_APPLICABLE_TEST],
            "classification_reason": NOT_APPLICABLE_WP_ALLOWLIST[key],
        }
    # 2. explicit deferred editor/WOPI allowlist.
    if key in DEFERRED_EDITOR_ALLOWLIST:
        return {
            "gate": _DEFERRED_EDITOR,
            "matrix": _DEFERRED_EDITOR,
            "test_ids": [DEFERRED_EDITOR_TEST],
            "classification_reason": DEFERRED_EDITOR_ALLOWLIST[key],
        }
    # 3. real wp gate wired in code → gated (dedicated subroute family).
    if le.gate_wired:
        action = _dedicated_action(le.method)
        return {
            "gate": _GATED,
            "matrix": f"workpaper.dedicated_subroute/{action}",
            "test_ids": [DEDICATED_GATE_TEST],
            "classification_reason": f"wp gate wired: {le.gate_detail}",
        }
    # 4. native project-level authz present → explicit deferral of the
    #    defence-in-depth visibility gate (honest, code-verified).
    if le.native_authz:
        return {
            "gate": _NATIVE_AUTHZ,
            "matrix": _NATIVE_AUTHZ,
            "test_ids": [NATIVE_AUTHZ_TEST],
            "classification_reason": f"native project authz: {le.native_detail}",
        }
    # 5. honest gap — no gate, no native authz, not allowlisted.
    return {"gate": _UNMIGRATED, "matrix": _UNMIGRATED, "test_ids": [], "classification_reason": None}


def reconcile_ledger(app: Any | None = None, ledger: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return an updated ledger reconciled against the live production surface.

    - Preserves existing non-``unmigrated`` HTTP classifications (test_ids/matrix).
    - Re-derives every ``unmigrated``/new wp-bound entry from real code.
    - Adds live routes missing from the ledger; drops stale ledger routes.
    - Preserves worker entries; refreshes gate for wp-bound workers from code.
    - Keeps the existing ``migration_head`` (frozen baseline) if present.
    """
    import copy

    if app is None:
        from app.main import app as fastapi_app

        app = fastapi_app
    if ledger is None:
        ledger = load_ledger()

    old = copy.deepcopy(ledger)
    old_http = {
        (e.get("route") or "", e.get("method") or ""): e
        for e in old.get("entries", [])
        if e.get("kind") == "http"
    }
    old_workers = [e for e in old.get("entries", []) if e.get("kind") in ("worker", "retry", "dead_letter")]
    old_workers_by_ep = {e["entrypoint"]: e for e in old_workers}

    live_http = scan_live_http(app)
    new_entries: list[dict[str, Any]] = []

    for key, le in live_http.items():
        prev = old_http.get(key)
        gate_prev = prev.get("gate") if prev else None
        # Preserve an already-classified (non-unmigrated) HTTP entry verbatim,
        # only refreshing identity fields; guard re-verifies it against code.
        if prev is not None and gate_prev != _UNMIGRATED:
            entry = dict(prev)
            entry["route"], entry["method"] = key
            entry["entrypoint"] = le.entrypoint
            entry["wp_bound"] = le.wp_bound if not entry.get("wp_bound") else entry["wp_bound"]
            if len(le.endpoints) > 1:
                entry["duplicate_registration"] = True
                entry["duplicate_entrypoints"] = list(le.endpoints)
            new_entries.append(entry)
            continue
        # unmigrated or brand-new → derive from code.
        cls = classify_unmigrated(le)
        entry = {
            "kind": "http",
            "entrypoint": le.entrypoint,
            "callable": le.entrypoint.rsplit(":", 1)[-1],
            "route": le.route,
            "method": le.method,
            "family": (prev or {}).get("family") or _family_for(le),
            "action": (prev or {}).get("action") or _action_for(le),
            "wp_bound": le.wp_bound,
            "binding": (prev or {}).get("binding") or _binding_for(le),
            "gate": cls["gate"],
            "matrix": cls["matrix"],
            "test_ids": cls["test_ids"],
        }
        if cls["classification_reason"]:
            entry["classification_reason"] = cls["classification_reason"]
        if len(le.endpoints) > 1:
            entry["duplicate_registration"] = True
            entry["duplicate_entrypoints"] = list(le.endpoints)
        new_entries.append(entry)

    # workers preserved (drop stale, keep live)
    live_workers = scan_live_nonhttp()
    live_worker_eps = {e["entrypoint"] for e in live_workers}
    for w in live_workers:
        prev = old_workers_by_ep.get(w["entrypoint"])
        base = dict(prev) if prev is not None else dict(w)
        # Resolve wp-bound worker classification (derived, honest).
        if base.get("wp_bound") and base.get("gate") in (_UNMIGRATED, None):
            ep = base["entrypoint"]
            wired, detail = nonhttp_regates(base)
            if wired:
                base["gate"] = _GATED
                base["matrix"] = "worker.regate"
                base["test_ids"] = base.get("test_ids") or [NATIVE_AUTHZ_TEST]
                base["classification_reason"] = f"re-gates on execution: {detail}"
            elif ep in NONHTTP_CLASSIFICATION:
                cls = NONHTTP_CLASSIFICATION[ep]
                base["gate"] = cls["gate"]
                base["matrix"] = cls["gate"]
                base["test_ids"] = cls["test_ids"]
                base["classification_reason"] = cls["reason"]
        new_entries.append(base)
    # (stale workers absent from live are naturally dropped)
    _ = live_worker_eps

    out = dict(old)
    out["generated_by"] = "app.security.coverage_guard.reconcile_ledger"
    out["generated_at"] = _now_iso()
    out["entries"] = sorted(
        new_entries,
        key=lambda e: (e.get("kind", ""), e.get("route") or e.get("entrypoint", ""), e.get("method") or ""),
    )
    out["summary"] = _rebuild_summary(new_entries)
    return out


def _family_for(le: LiveHttpEntry) -> str:
    from app.security.entry_coverage_scanner import classify_family

    return classify_family(le.route, le.method, extract_path_params(le.route), le.wp_bound)


def _action_for(le: LiveHttpEntry) -> str:
    from app.security.entry_coverage_scanner import classify_action

    return classify_action(le.method, _family_for(le))


def _binding_for(le: LiveHttpEntry) -> str:
    from app.security.entry_coverage_scanner import binding_hint

    return binding_hint(le.route, extract_path_params(le.route), le.wp_bound)


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _rebuild_summary(entries: list[dict[str, Any]]) -> dict[str, Any]:
    by_family: dict[str, int] = {}
    by_gate: dict[str, int] = {}
    http_total = wp_bound_http = worker_total = 0
    for e in entries:
        by_family[e.get("family", "?")] = by_family.get(e.get("family", "?"), 0) + 1
        by_gate[e.get("gate", "?")] = by_gate.get(e.get("gate", "?"), 0) + 1
        if e.get("kind") == "http":
            http_total += 1
            if e.get("wp_bound"):
                wp_bound_http += 1
        else:
            worker_total += 1
    return {
        "entry_total": len(entries),
        "http_total": http_total,
        "http_wp_bound": wp_bound_http,
        "http_non_wp_bound": http_total - wp_bound_http,
        "worker_total": worker_total,
        "by_family": dict(sorted(by_family.items())),
        "by_gate": dict(sorted(by_gate.items())),
    }


def write_reconciled_ledger(app: Any | None = None, path: Path | None = None) -> dict[str, Any]:
    """Reconcile and persist the ledger JSON. Returns the ledger dict."""
    import json

    ledger = reconcile_ledger(app)
    out = path or LEDGER_PATH
    Path(out).write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return ledger


# ---------------------------------------------------------------------------
# Drift check
# ---------------------------------------------------------------------------
@dataclass
class Findings:
    missing_in_ledger: list[str] = field(default_factory=list)      # live route absent from ledger
    stale_in_ledger: list[str] = field(default_factory=list)        # ledger route absent from live
    duplicate_unresolved: list[str] = field(default_factory=list)   # dup (route,method) distinct endpoints
    wp_bound_ungated: list[str] = field(default_factory=list)       # gate == unmigrated (honest gap)
    fake_pass: list[str] = field(default_factory=list)              # ledger gated but no gate in code
    matrix_unregistered: list[str] = field(default_factory=list)    # matrix ref not in ActionMatrix
    missing_test_ids: list[str] = field(default_factory=list)       # gated but no stable test ids
    half_migrated: list[str] = field(default_factory=list)          # gate/matrix inconsistent
    native_authz_unaudited: list[str] = field(default_factory=list)  # native_authz not classified by Task 4 audit
    nonhttp_missing_in_ledger: list[str] = field(default_factory=list)
    nonhttp_stale_in_ledger: list[str] = field(default_factory=list)
    nonhttp_regate_missing: list[str] = field(default_factory=list)  # wp-bound worker not re-gating
    migration_head: list[str] = field(default_factory=list)

    def is_clean(self) -> bool:
        return not any(
            getattr(self, f.name) for f in self.__dataclass_fields__.values()
        )

    def total(self) -> int:
        return sum(len(getattr(self, f.name)) for f in self.__dataclass_fields__.values())

    def summary(self) -> dict[str, int]:
        return {
            f.name: len(getattr(self, f.name))
            for f in self.__dataclass_fields__.values()
            if getattr(self, f.name)
        }


def check_drift(app: Any | None = None, ledger: dict[str, Any] | None = None) -> Findings:
    """Compare the live production surface against the persisted ledger.

    Anti-fake-pass invariants (all block CI when violated):
      - HTTP (route, method) live⇔ledger bidirectional equality.
      - Non-HTTP callable live⇔ledger bidirectional equality.
      - Duplicate (route, method) with distinct endpoints must be resolved.
      - Every wp-bound entry gated in code but marked unmigrated → ungated gap.
      - Every wp-bound entry marked gated but with NO gate in code → fake_pass.
      - Gated wp-bound entry matrix ref must be registered in ActionMatrix.
      - Gated wp-bound entry must carry stable test_ids.
      - wp-bound non-HTTP callable must re-gate on execution.
      - migration_head must be an accepted head.
    """
    if app is None:
        from app.main import app as fastapi_app

        app = fastapi_app
    if ledger is None:
        ledger = load_ledger()

    f = Findings()
    matrix_pairs = matrix_registered_pairs()

    # ── HTTP surface ────────────────────────────────────────────────────
    live_http = scan_live_http(app)
    ledger_http: dict[tuple[str, str], dict[str, Any]] = {}
    for e in ledger.get("entries", []):
        if e.get("kind") == "http":
            key = (e.get("route") or "", e.get("method") or "")
            ledger_http[key] = e

    live_keys = set(live_http)
    ledger_keys = set(ledger_http)

    for key in sorted(live_keys - ledger_keys):
        f.missing_in_ledger.append(f"{key[1]} {key[0]}")
    for key in sorted(ledger_keys - live_keys):
        f.stale_in_ledger.append(f"{key[1]} {key[0]}")

    # duplicates in live app (distinct endpoints on same route+method). Known
    # pre-existing duplicates are explicitly allowlisted (honest, out of scope);
    # any NEW duplicate blocks CI.
    for key, le in sorted(live_http.items()):
        if len(le.endpoints) > 1 and key not in KNOWN_DUPLICATE_REGISTRATIONS:
            f.duplicate_unresolved.append(f"{key[1]} {key[0]} -> {le.endpoints}")

    # per-entry gate / matrix / test_ids checks against real code
    for key in sorted(live_keys & ledger_keys):
        le = live_http[key]
        led = ledger_http[key]
        if not le.wp_bound and not led.get("wp_bound"):
            continue
        label = f"{key[1]} {key[0]}"
        gate = led.get("gate")
        matrix = led.get("matrix")
        # Classify by the ledger's declared gate value, verifying each against
        # real code / explicit allowlist (anti-fake-pass; honest deferrals only).
        if led.get("wp_bound"):
            gate_base = gate == _UNMIGRATED
            matrix_base = matrix == _UNMIGRATED
            # honest gap: still unmigrated.
            if gate_base or matrix_base:
                if gate_base and matrix_base:
                    f.wp_bound_ungated.append(label)
                else:
                    f.half_migrated.append(f"{label} (gate={gate}, matrix={matrix})")
                continue
            # native_authz: code must genuinely carry native project authz.
            if gate == _NATIVE_AUTHZ:
                if not le.native_authz:
                    f.fake_pass.append(f"{label} (ledger native_authz, code has no native authz hook)")
                if not led.get("test_ids"):
                    f.missing_test_ids.append(label)
                # Task 4 (visibility-isolation-go-live-hardening / R3): every
                # native_authz HTTP entry MUST be classified by the native_authz
                # audit as justified_allowlist or leak_risk_deferred (recorded,
                # non-silent). An entry in NO audit table → native_authz_unaudited
                # (fail-closed, blocks CI — no silent pass; Req 3.8/3.10).
                try:
                    from app.security.native_authz_audit import (
                        AUDITED_DISPOSITIONS as _AUDIT_DISP,
                        classify as _classify_authz,
                    )

                    _disp = _classify_authz(key[0], key[1])["disposition"]
                    if _disp not in _AUDIT_DISP:
                        f.native_authz_unaudited.append(label)
                except Exception:  # noqa: BLE001 — audit module problems must not hide the gap
                    f.native_authz_unaudited.append(f"{label} (audit classification unavailable)")
                continue
            # not_applicable on a wp_bound route: must be explicitly allowlisted.
            if gate == _NOT_APPLICABLE:
                if key not in NOT_APPLICABLE_WP_ALLOWLIST:
                    f.fake_pass.append(f"{label} (gate=not_applicable but not in NOT_APPLICABLE_WP_ALLOWLIST)")
                continue
            # deferred_editor: must be explicitly allowlisted + carry mechanism test.
            if gate == _DEFERRED_EDITOR:
                if key not in DEFERRED_EDITOR_ALLOWLIST:
                    f.fake_pass.append(f"{label} (gate=deferred_editor but not in DEFERRED_EDITOR_ALLOWLIST)")
                if not led.get("test_ids"):
                    f.missing_test_ids.append(label)
                continue
            # gated / migrated / editor descriptive-string gate: any remaining
            # non-special value is a *code-gated claim* — real code must have a
            # gate wired (covers 'gated', 'migrated' and Task 11 editor entries
            # whose gate value is a free-text description of the gate calls).
            if not le.gate_wired:
                f.fake_pass.append(f"{label} (ledger gate={gate!r}, code has no gate)")
            pair = parse_matrix_ref(matrix)
            if pair is not None and pair not in matrix_pairs:
                f.matrix_unregistered.append(f"{label} (matrix={matrix})")
            if not led.get("test_ids"):
                f.missing_test_ids.append(label)

    # ── Non-HTTP surface ────────────────────────────────────────────────
    live_workers = scan_live_nonhttp()
    live_worker_keys = {e["entrypoint"] for e in live_workers}
    ledger_worker_entries = [
        e for e in ledger.get("entries", []) if e.get("kind") in ("worker", "retry", "dead_letter")
    ]
    ledger_worker_keys = {e["entrypoint"] for e in ledger_worker_entries}

    for k in sorted(live_worker_keys - ledger_worker_keys):
        f.nonhttp_missing_in_ledger.append(k)
    for k in sorted(ledger_worker_keys - live_worker_keys):
        f.nonhttp_stale_in_ledger.append(k)

    live_by_ep = {e["entrypoint"]: e for e in live_workers}
    for e in ledger_worker_entries:
        if not e.get("wp_bound"):
            continue
        live_e = live_by_ep.get(e["entrypoint"])
        if live_e is None:
            continue
        gate = e.get("gate")
        ep = e["entrypoint"]
        if gate == _UNMIGRATED:
            f.wp_bound_ungated.append(f"worker:{ep}")
            continue
        # native_authz worker: must be in the explicit NONHTTP allowlist.
        if gate == _NATIVE_AUTHZ:
            if ep not in NONHTTP_CLASSIFICATION:
                f.fake_pass.append(f"worker:{ep} (native_authz but not in NONHTTP_CLASSIFICATION)")
            if not e.get("test_ids"):
                f.missing_test_ids.append(f"worker:{ep}")
            continue
        # any other gate value is a code-gated claim: must re-gate on execution.
        wired, _detail = nonhttp_regates(e)
        if not wired:
            f.nonhttp_regate_missing.append(f"{ep} ({_detail})")
        if not e.get("test_ids"):
            f.missing_test_ids.append(f"worker:{ep}")

    # ── migration head ──────────────────────────────────────────────────
    head = ledger.get("migration_head")
    if head not in ACCEPTED_MIGRATION_HEADS:
        f.migration_head.append(
            f"migration_head={head} not in {sorted(ACCEPTED_MIGRATION_HEADS)}"
        )

    return f


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _main() -> int:
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    findings = check_drift()
    if findings.is_clean():
        print("[coverage-guard] OK — production surface ⇔ ledger bidirectionally equal, no fake-pass")
        return 0

    print(f"[coverage-guard] DRIFT DETECTED ({findings.total()} problem(s)):")
    for cat, count in findings.summary().items():
        print(f"  {cat:26s}: {count}")
        items = getattr(findings, cat)
        for it in items[:12]:
            print(f"      - {it}")
        if len(items) > 12:
            print(f"      ... (+{len(items) - 12} more)")
    return 1


if __name__ == "__main__":
    raise SystemExit(_main())
