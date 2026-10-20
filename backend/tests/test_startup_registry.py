"""platform-architecture-convergence Tasks 10–12: startup registry / report / probes.

Validates Requirements 5.1–5.7, 6.1–6.6 and Properties 9–12.
"""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core import startup_registry as sr
from app.core.startup_registry import (
    FROZEN_CRITICAL_SEQUENCE_NAMES,
    FROZEN_STARTUP_SEQUENCE_NAMES,
    STARTUP_TASKS,
    WORKER_TASK_NAMES,
    StartupContext,
    StartupTaskResult,
    StartupTaskSpec,
    assert_criticality_matches_frozen,
    assert_sequence_matches_frozen,
    desensitize_detail,
    get_startup_report,
    reset_startup_report,
    run_startup_tasks,
    startup_report_as_dict,
)


# ---------------------------------------------------------------------------
# Task 10 — freeze sequence / criticality / workers
# ---------------------------------------------------------------------------

def test_frozen_sequence_names_match_registry():
    """Sequence lock: registry names equal the frozen tuple."""
    assert tuple(t.name for t in STARTUP_TASKS) == FROZEN_STARTUP_SEQUENCE_NAMES
    assert_sequence_matches_frozen()


def test_frozen_sequence_includes_legacy_lifespan_milestones():
    """Milestones from T01 lifespan baseline appear in order."""
    names = list(FROZEN_STARTUP_SEQUENCE_NAMES)
    milestones = [
        "setup_logging",
        "run_migrations",
        "migration_mark_complete",
        "acnr_redis_inject",
        "register_event_handlers",
        "register_a13_event_handlers",
        "register_phase_handlers",
        "replay_startup_events",
        "validate_grammar_on_startup",
        "check_gin_index_status",
        "check_libreoffice_health",
        "validate_procedure_rollout_config",
        "validate_template_manifest",
        "run_schema_drift_check",
        "warm_render_caches",
        "check_attachment_security_gates",
        "start_epoch_subscriber",
        "acnr_invalidation_outbox_start",
        "recover_ai_chat_runs",
        "run_ai_chat_health_check",
        "acnr_catalog_snapshot_gc",
        "sla_worker",
        "ImportJobRunner.run_forever",
        "warm_workpaper_sync_registry",
        "install_sigterm_handler",
        "print_ready",
    ]
    positions = [names.index(m) for m in milestones]
    assert positions == sorted(positions)


def test_all_worker_names_present_in_registry():
    """The 12+1 workers appear in STARTUP_TASKS' worker phase, by name, in pinned order."""
    worker_phase = [t.name for t in STARTUP_TASKS if t.phase == "workers"]
    assert worker_phase == list(WORKER_TASK_NAMES)
    assert [name for name, _mod in sr._WORKER_BINDINGS] == list(WORKER_TASK_NAMES[:-1])
    assert WORKER_TASK_NAMES[-1] == "ImportJobRunner.run_forever"


def test_mutation_swap_adjacent_critical_fails_sequence_lock():
    """Swapping two adjacent critical steps must fail the sequence-lock guard."""
    critical_idxs = [
        i for i, t in enumerate(STARTUP_TASKS) if t.criticality == "critical"
    ]
    assert len(critical_idxs) >= 2
    # Find two adjacent critical specs in the tuple (not necessarily consecutive indices
    # if a best_effort sits between — prefer consecutive registry neighbors that are both critical).
    swap_i = None
    for i in range(len(STARTUP_TASKS) - 1):
        a, b = STARTUP_TASKS[i], STARTUP_TASKS[i + 1]
        if a.criticality == "critical" and b.criticality == "critical":
            swap_i = i
            break
    assert swap_i is not None, "need adjacent critical pair for mutation"

    mutated = list(STARTUP_TASKS)
    mutated[swap_i], mutated[swap_i + 1] = mutated[swap_i + 1], mutated[swap_i]
    with pytest.raises(AssertionError, match="startup sequence drift"):
        assert_sequence_matches_frozen(mutated)


def test_mutation_change_criticality_fails_lock():
    """Changing a task's criticality must fail the criticality lock."""
    target = next(t for t in STARTUP_TASKS if t.criticality == "critical")
    flipped = "best_effort"
    mutated_spec = StartupTaskSpec(
        name=target.name,
        phase=target.phase,
        criticality=flipped,  # type: ignore[arg-type]
        run=target.run,
        timeout_seconds=target.timeout_seconds,
        skip_condition=target.skip_condition,
    )
    mutated = tuple(
        mutated_spec if t.name == target.name else t for t in STARTUP_TASKS
    )
    with pytest.raises(AssertionError, match="criticality drift"):
        assert_criticality_matches_frozen(mutated)


def test_frozen_critical_names_nonempty():
    assert len(FROZEN_CRITICAL_SEQUENCE_NAMES) >= 5
    assert "migration_mark_complete" in FROZEN_CRITICAL_SEQUENCE_NAMES
    assert "validate_grammar_on_startup" in FROZEN_CRITICAL_SEQUENCE_NAMES


# ---------------------------------------------------------------------------
# Task 11 — serial executor with injectable callables
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_executor_critical_failure_reraises_and_stops():
    reset_startup_report()
    ran: list[str] = []

    async def boom(_ctx: StartupContext) -> None:
        ran.append("boom")
        raise RuntimeError("critical-boom")

    async def after(_ctx: StartupContext) -> None:
        ran.append("after")

    tasks = (
        StartupTaskSpec(
            name="a_ok", phase="t", criticality="critical", run=lambda c: ran.append("a") or None
        ),
        StartupTaskSpec(name="b_fail", phase="t", criticality="critical", run=boom),
        StartupTaskSpec(name="c_after", phase="t", criticality="critical", run=after),
    )
    with pytest.raises(RuntimeError, match="critical-boom"):
        await run_startup_tasks(tasks)
    assert "after" not in ran
    report = get_startup_report()
    assert report is not None
    assert [r.name for r in report] == ["a_ok", "b_fail"]
    assert report[-1].status == "failed"


@pytest.mark.asyncio
async def test_executor_best_effort_failure_continues():
    reset_startup_report()
    ran: list[str] = []

    async def soft_fail(_ctx: StartupContext) -> None:
        raise ValueError("soft")

    async def later(_ctx: StartupContext) -> None:
        ran.append("later")

    tasks = (
        StartupTaskSpec(
            name="soft", phase="t", criticality="best_effort", run=soft_fail
        ),
        StartupTaskSpec(name="later", phase="t", criticality="critical", run=later),
    )
    results = await run_startup_tasks(tasks)
    assert ran == ["later"]
    assert results[0].status == "failed"
    assert results[1].status == "ok"
    assert "ValueError" in (results[0].detail or "")


@pytest.mark.asyncio
async def test_executor_skip_condition():
    reset_startup_report()
    ran = {"count": 0}

    async def body(_ctx: StartupContext) -> None:
        ran["count"] += 1

    tasks = (
        StartupTaskSpec(
            name="skipped_one",
            phase="t",
            criticality="critical",
            run=body,
            skip_condition=lambda _c: "because-test",
        ),
        StartupTaskSpec(
            name="runs",
            phase="t",
            criticality="critical",
            run=body,
        ),
    )
    results = await run_startup_tasks(tasks)
    assert ran["count"] == 1
    assert results[0].status == "skipped"
    assert results[0].detail == "because-test"
    assert results[1].status == "ok"


@pytest.mark.asyncio
async def test_executor_records_worker_names_in_report():
    """Injected worker-named tasks appear individually in the report."""
    reset_startup_report()
    ctx = StartupContext()
    ctx.stop_event.set()

    async def noop(_ctx: StartupContext) -> None:
        return None

    worker_tasks = tuple(
        StartupTaskSpec(
            name=name,
            phase="workers",
            criticality="best_effort",
            run=noop,
        )
        for name in WORKER_TASK_NAMES
    )
    results = await run_startup_tasks(worker_tasks, context=ctx)
    assert [r.name for r in results] == list(WORKER_TASK_NAMES)
    assert all(r.status == "ok" for r in results)


@pytest.mark.asyncio
async def test_executor_serial_order():
    order: list[str] = []

    def make(name: str):
        async def _run(_ctx: StartupContext) -> None:
            order.append(name)

        return StartupTaskSpec(
            name=name, phase="t", criticality="critical", run=_run
        )

    await run_startup_tasks((make("x"), make("y"), make("z")))
    assert order == ["x", "y", "z"]


# ---------------------------------------------------------------------------
# Task 12 — health report + livez/readyz preserved
# ---------------------------------------------------------------------------

def test_desensitize_strips_credentials():
    raw = (
        "failed password=s3cret token=abc DATABASE_URL=postgresql://u:p@h/db "
        "Bearer eyJhbGciOiJIUzI1NiJ9.xx"
    )
    cleaned = desensitize_detail(raw)
    assert cleaned is not None
    assert "s3cret" not in cleaned
    assert "postgresql://u:p@h/db" not in cleaned
    assert "eyJhbGciOiJIUzI1NiJ9" not in cleaned
    assert "[REDACTED]" in cleaned


def test_startup_report_as_dict_isomorphic_to_injected_results():
    results = (
        StartupTaskResult("a", "p", "ok", 1, None),
        StartupTaskResult("b", "p", "failed", 2, "password=leak"),
        StartupTaskResult("c", "p", "skipped", 0, "skip-me"),
    )
    payload = startup_report_as_dict(results)
    assert payload["task_count"] == 3
    assert [t["name"] for t in payload["tasks"]] == ["a", "b", "c"]
    assert payload["failed"] == ["b"]
    assert payload["skipped"] == ["c"]
    assert "leak" not in (payload["tasks"][1]["detail"] or "")


@pytest.mark.asyncio
async def test_health_includes_startup_report():
    from app.api.health import router
    from app.core.database import get_db
    from app.core.redis import get_redis

    reset_startup_report()
    # Seed a fake report snapshot
    from app.core import startup_registry as sr

    sr._set_runtime_report(
        (
            StartupTaskResult("setup_logging", "bootstrap", "ok", 1, None),
            StartupTaskResult("sla_worker", "workers", "ok", 0, None),
        )
    )

    app = FastAPI()
    app.include_router(router, prefix="/api")

    async def _mock_db():
        session = AsyncMock()
        session.execute = AsyncMock(return_value=None)
        yield session

    async def _mock_redis():
        client = AsyncMock()
        client.ping = AsyncMock(return_value=True)
        yield client

    app.dependency_overrides[get_db] = _mock_db
    app.dependency_overrides[get_redis] = _mock_redis

    clean_mig = AsyncMock(return_value={"applied_count": 0, "failures": []})
    clean_drift = AsyncMock(
        return_value={"count": 0, "critical_count": 0, "items": []}
    )

    transport = ASGITransport(app=app)
    with patch("app.api.health._query_migration_status", new=clean_mig), patch(
        "app.api.health._query_schema_drift", new=clean_drift
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert "startup" in body
    assert body["startup"]["task_count"] == 2
    assert body["startup"]["tasks"][0]["name"] == "setup_logging"
    assert body["startup"]["tasks"][1]["name"] == "sla_worker"
    # Report must not flip health status
    assert body["status"] == "healthy"


@pytest.mark.asyncio
async def test_livez_always_200_ignores_startup_failures():
    from app.api.probes import router as probes_router
    from app.core import startup_registry as sr

    sr._set_runtime_report(
        (StartupTaskResult("x", "t", "failed", 1, "boom"),)
    )
    app = FastAPI()
    app.include_router(probes_router)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/livez")
    assert resp.status_code == 200
    assert resp.json()["status"] == "alive"


@pytest.mark.asyncio
async def test_readyz_priority_draining_then_migration_then_health():
    """readyz priority unchanged: draining → migration → PG/Redis; report ignored."""
    from app.api.probes import router as probes_router
    from app.core.runtime_state import migration_state, shutdown_state
    from app.core import startup_registry as sr

    sr._set_runtime_report(
        (StartupTaskResult("soft", "t", "failed", 1, "best_effort fail"),)
    )

    app = FastAPI()
    app.include_router(probes_router)
    transport = ASGITransport(app=app)

    # Save / restore process flags
    was_draining = shutdown_state.is_draining()
    was_complete = migration_state.is_complete()
    try:
        # 1) draining wins
        shutdown_state.start_draining()
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/readyz")
        assert resp.status_code == 503
        assert resp.json()["status"] == "draining"

        # Reset draining via direct attribute (test-only)
        shutdown_state._draining = False  # noqa: SLF001

        # 2) migration incomplete
        migration_state._complete = False  # noqa: SLF001
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/readyz")
        assert resp.status_code == 503
        assert resp.json()["migration_complete"] is False

        # 3) migration complete + healthy deps → ready (startup failed must NOT block)
        migration_state.mark_complete()
        with patch(
            "app.api.probes._get_health_snapshot_cached",
            new=AsyncMock(return_value={"status": "healthy"}),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/readyz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"
    finally:
        shutdown_state._draining = was_draining  # noqa: SLF001
        migration_state._complete = was_complete  # noqa: SLF001


@pytest.mark.asyncio
async def test_readyz_unhealthy_still_503_with_startup_ok():
    from app.api.probes import router as probes_router
    from app.core.runtime_state import migration_state, shutdown_state

    was_draining = shutdown_state.is_draining()
    was_complete = migration_state.is_complete()
    app = FastAPI()
    app.include_router(probes_router)
    try:
        shutdown_state._draining = False  # noqa: SLF001
        migration_state.mark_complete()
        with patch(
            "app.api.probes._get_health_snapshot_cached",
            new=AsyncMock(return_value={"status": "unhealthy"}),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/readyz")
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "not_ready"
        assert body["health"] == "unhealthy"
    finally:
        shutdown_state._draining = was_draining  # noqa: SLF001
        migration_state._complete = was_complete  # noqa: SLF001


def test_main_reexports_start_workers():
    from app.main import _start_workers
    from app.core.startup_registry import start_all_workers

    assert _start_workers is start_all_workers


# ---------------------------------------------------------------------------
# preexisting-test-failures-closure G11 — lifespan executes the registry (one source)
#
# The lifespan wiring of platform-architecture-convergence never landed: main.lifespan
# kept its own copy of every step while STARTUP_TASKS was only read by the tests above,
# and the two drifted (registry lost 6 EventBus subscriptions + the sync prewarm).
# ---------------------------------------------------------------------------

_MAIN_PY = Path(__file__).resolve().parents[1] / "app" / "main.py"

#: Startup helpers main.py used to inline — each duplicated a registry task body.
_FORMER_MAIN_STARTUP_HELPERS = frozenset({
    "_run_ai_chat_health_check", "_recover_ai_chat_runs", "_check_attachment_security_gates",
    "_warm_render_caches", "_warm_workpaper_sync_registry", "_run_schema_drift_check",
    "_run_migrations", "_register_phase_handlers", "_check_gin_index_status",
    "_validate_template_manifest", "_check_libreoffice_health",
    "_validate_procedure_rollout_config", "_replay_startup_events", "_start_workers",
})


def _lifespan_calls_before_yield() -> list[str]:
    """Names called by ``main.lifespan`` before its ``yield`` (AST: comments never count)."""
    tree = ast.parse(_MAIN_PY.read_text(encoding="utf-8"))
    fn = next(
        n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "lifespan"
    )
    calls: list[str] = []
    for stmt in fn.body:
        if any(isinstance(n, ast.Yield) for n in ast.walk(stmt)):
            break
        for node in ast.walk(stmt):
            if isinstance(node, ast.Call):
                func = node.func
                calls.append(func.id if isinstance(func, ast.Name) else getattr(func, "attr", "?"))
    return calls


def test_lifespan_startup_is_only_the_registry():
    """Before ``yield`` lifespan only builds the context and runs STARTUP_TASKS."""
    assert _lifespan_calls_before_yield() == ["StartupContext", "run_startup_tasks"]


def test_main_defines_no_startup_step_bodies():
    """main.py must not carry its own copy of a startup step (that copy drifted once)."""
    tree = ast.parse(_MAIN_PY.read_text(encoding="utf-8"))
    defined = {
        n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert defined & _FORMER_MAIN_STARTUP_HELPERS == set()


@pytest.mark.asyncio
async def test_lifespan_runs_registry_and_stops_its_tasks(monkeypatch):
    """lifespan awaits run_startup_tasks(context=ctx); shutdown sets ctx.stop_event and
    cancels every task the registry put into ctx.worker_tasks."""
    import app.main as main_mod
    from app.core import database, graceful_shutdown
    from app.core import sse_registry as sse_mod
    from app.services.acnr import cache_epoch, invalidation_outbox

    seen: dict[str, object] = {}

    async def fake_run(tasks=None, *, context=None):
        seen["tasks"] = tasks
        seen["ctx"] = context
        context.worker_tasks.append(asyncio.create_task(asyncio.Event().wait()))
        return []

    dispatcher = MagicMock()
    dispatcher.stop = AsyncMock()
    monkeypatch.setattr(sr, "run_startup_tasks", fake_run)
    monkeypatch.setattr(graceful_shutdown, "PRE_DRAIN_DELAY", 0)
    monkeypatch.setattr(graceful_shutdown, "drain_http_requests", AsyncMock())
    monkeypatch.setattr(sse_mod.sse_registry, "close_all", AsyncMock())
    monkeypatch.setattr(cache_epoch, "stop_epoch_subscriber", AsyncMock())
    monkeypatch.setattr(invalidation_outbox, "get_dispatcher", lambda: dispatcher)
    monkeypatch.setattr(database, "dispose_engine", AsyncMock())

    async with main_mod.lifespan(FastAPI()):
        ctx = seen["ctx"]
        assert isinstance(ctx, StartupContext)
        assert seen["tasks"] is None  # None = the full STARTUP_TASKS
        worker = ctx.worker_tasks[0]
        assert not worker.done() and not ctx.stop_event.is_set()
    assert ctx.stop_event.is_set()
    assert worker.cancelled()
    dispatcher.stop.assert_awaited_once()


#: (module, registration function, takes the EventBus) — everything main used to register.
_PHASE_HANDLER_REGISTRATIONS = (
    ("app.services.gate_rules_phase14", "register_phase14_rules", False),
    ("app.services.gate_rules_eqcr", "register_eqcr_gate_rules", False),
    ("app.services.gate_rules_cross_check", "register_cross_check_rules", False),
    ("app.services.task_event_handlers", "register_event_handlers", False),
    ("app.services.consol_note_stale_handler", "register_stale_handler", True),
    ("app.services.consol_trial_stale_handler", "register_consol_trial_stale_handler", True),
    ("app.services.consol_elimination_recalc_handler",
     "register_consol_elimination_recalc_handler", True),
    ("app.services.consol_note_formula_refresh_handler",
     "register_consol_note_formula_refresh_handler", True),
    ("app.services.adjustment_approved_recalc_handler",
     "register_adjustment_approved_recalc_handler", True),
    ("app.services.formula_push.triggers", "register_formula_push_handlers", True),
)


def test_phase_handlers_task_registers_every_handler(monkeypatch):
    """The last three were missing from the registry copy (6 EventBus subscriptions:
    adjustment approved / revoked recalc, formula push ×2, consol note formula refresh ×2)."""
    import importlib

    from app.services.event_bus import event_bus

    mocks = {}
    for module, func, _takes_bus in _PHASE_HANDLER_REGISTRATIONS:
        mocks[func] = MagicMock(name=func)
        monkeypatch.setattr(importlib.import_module(module), func, mocks[func])

    sr._task_register_phase_handlers(StartupContext())

    for _module, func, takes_bus in _PHASE_HANDLER_REGISTRATIONS:
        if takes_bus:
            mocks[func].assert_called_once_with(event_bus)
        else:
            mocks[func].assert_called_once_with()


@pytest.mark.asyncio
async def test_workpaper_sync_prewarm_is_scheduled_not_awaited(monkeypatch):
    """25~30s prewarm must not delay Ready, and its task must be kept for shutdown."""
    from app.services.workpaper_sync import startup_prewarm

    started, release = asyncio.Event(), asyncio.Event()

    async def slow_prewarm() -> None:
        started.set()
        await release.wait()

    monkeypatch.setattr(startup_prewarm, "warm_workpaper_sync_registry", slow_prewarm)
    spec = next(t for t in STARTUP_TASKS if t.name == "warm_workpaper_sync_registry")
    assert (spec.phase, spec.criticality) == ("caches", "best_effort")

    ctx = StartupContext()
    results = await run_startup_tasks((spec,), context=ctx)
    assert [r.status for r in results] == ["ok"]
    assert len(ctx.worker_tasks) == 1
    task = ctx.worker_tasks[0]
    await asyncio.wait_for(started.wait(), timeout=1)
    assert not task.done()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    reset_startup_report()


def test_start_all_workers_runs_the_registry_worker_specs(monkeypatch):
    """The compat entry starts exactly the registry worker bindings (no second list)."""
    from app.core.config import settings

    started: list[str] = []
    monkeypatch.setattr(
        sr, "_make_worker_starter", lambda mod, attr="run": (lambda _ctx: started.append(mod))
    )
    monkeypatch.setattr(sr, "_start_import_job_runner", lambda _ctx: started.append("runner"))
    for enabled in (False, True):
        started.clear()
        monkeypatch.setattr(settings, "LEDGER_IMPORT_IN_PROCESS_RUNNER_ENABLED", enabled)
        assert sr.start_all_workers(asyncio.Event()) == []
        expected = [mod for _name, mod in sr._WORKER_BINDINGS] + (["runner"] if enabled else [])
        assert started == expected
