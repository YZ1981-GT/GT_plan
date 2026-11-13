"""Machine-readable capacity report schema + generator + threshold assertions.

Spec: consolidation-run-and-workpaper-lifecycle-closure — Task 8.4
Requirements: R10 (performance/capacity/observability), R11 (验收).
Design: §6 (性能与观测), §7 (降级).

The report generator is a *pure* function over an observation payload
(``CapacityObservations``). It does not run load itself — the Locust harness
(or any capacity runner) collects observations and hands them here. This keeps
the pass/fail logic deterministic, unit-testable, and independent of whether an
actual 6000 VU environment was available. This is what makes Task 8.4 a
verifiable DELIVERABLE even though the 6000 VU run is not authorized here.

A report is PASS only when every one of the following holds:
  * every measured SLO op p50/p95/p99 <= its budget (warmup excluded);
  * aggregate error rate < 1%;
  * sustained throughput >= the floor (a stalled system fails even if the few
    completed requests look fast);
  * cross-project canary leakage == 0;
  * duplicate operation side-effects == 0 (same idempotency key -> one op);
  * no lost persisted operation under backpressure (design R4.3/R4.5);
  * no forbidden terminal state under chaos (fake "succeeded" / version-less
    recompute);
  * the PG/PgBouncer connection budget invariant holds.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from .connection_budget import BudgetCheck, ConnectionBudget, check_budget
from .scenario import ACCEPTANCE, SCENARIO, SLO_BY_OP, AcceptanceThresholds


# ---------------------------------------------------------------------------
# Observation inputs (populated by the capacity runner)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OpLatency:
    """Measured latency for one logical SLO op over the measurement window."""

    op: str
    p50_ms: float
    p95_ms: float
    p99_ms: float
    num_requests: int
    num_failures: int


@dataclass(frozen=True)
class ChaosObservation:
    """What happened while a dependency fault was active."""

    dependency: str
    mode: str
    degraded_status_surfaced: bool
    forbidden_terminal_states: int   # fake succeeded / version-less recompute produced despite fault
    business_data_mutations: int     # unexpected mutations to existing published results
    unaffected_ops_within_slo: bool


@dataclass(frozen=True)
class CapacityObservations:
    """Everything a run must report for the generator to render a verdict."""

    peak_virtual_users: int
    steady_seconds: int
    burst_seconds: int
    total_requests: int
    total_failures: int
    throughput_rps: float
    op_latencies: tuple[OpLatency, ...]
    cross_project_leakage: int
    duplicate_operation_effects: int
    lost_persisted_operations: int
    backpressure_429_count: int
    chaos: tuple[ChaosObservation, ...] = ()
    # Whether measurements exclude warmup (they must, per §6 "steady + burst").
    warmup_excluded: bool = True
    environment: str = "unspecified"

    @property
    def error_rate_pct(self) -> float:
        if self.total_requests <= 0:
            return 0.0
        return 100.0 * self.total_failures / self.total_requests


# ---------------------------------------------------------------------------
# Report schema
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SloResult:
    op: str
    p50_ms: float
    p95_ms: float
    p99_ms: float
    p50_budget_ms: int
    p95_budget_ms: int
    p99_budget_ms: int
    num_requests: int
    ok: bool


@dataclass
class CapacityReport:
    generated_at: str
    spec: str
    task: str
    requirements: list[str]
    environment: str
    passed: bool
    failures: list[str]
    # verdict detail
    peak_virtual_users: int
    target_virtual_users: int
    steady_seconds: int
    burst_seconds: int
    error_rate_pct: float
    max_error_rate_pct: float
    throughput_rps: float
    min_throughput_rps: float
    cross_project_leakage: int
    duplicate_operation_effects: int
    lost_persisted_operations: int
    backpressure_429_count: int
    slo_results: list[dict]
    chaos_results: list[dict]
    connection_budget: dict

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

def generate_report(
    obs: CapacityObservations,
    *,
    thresholds: AcceptanceThresholds = ACCEPTANCE,
    budget: ConnectionBudget | None = None,
) -> CapacityReport:
    """Render a machine-readable capacity report + verdict from observations."""
    failures: list[str] = []

    # --- SLO p50/p95/p99 gates ---
    slo_results: list[SloResult] = []
    for lat in obs.op_latencies:
        target = SLO_BY_OP.get(lat.op)
        if target is None:
            failures.append(f"observed unknown SLO op {lat.op!r} (not in SLO table)")
            continue
        breaches: list[str] = []
        if lat.p50_ms > target.p50_ms:
            breaches.append(f"p50 {lat.p50_ms:.0f}ms > {target.p50_ms}ms")
        if lat.p95_ms > target.p95_ms:
            breaches.append(f"p95 {lat.p95_ms:.0f}ms > {target.p95_ms}ms")
        if lat.p99_ms > target.p99_ms:
            breaches.append(f"p99 {lat.p99_ms:.0f}ms > {target.p99_ms}ms")
        ok = not breaches
        slo_results.append(
            SloResult(
                op=lat.op,
                p50_ms=lat.p50_ms,
                p95_ms=lat.p95_ms,
                p99_ms=lat.p99_ms,
                p50_budget_ms=target.p50_ms,
                p95_budget_ms=target.p95_ms,
                p99_budget_ms=target.p99_ms,
                num_requests=lat.num_requests,
                ok=ok,
            )
        )
        if not ok:
            failures.append(f"SLO breach {lat.op}: " + "; ".join(breaches))

    # --- warmup must be excluded from the measurement window ---
    if not obs.warmup_excluded:
        failures.append("measurement window includes warmup; §6 requires steady+burst only")

    # --- steady/burst duration must satisfy the design contract ---
    if obs.steady_seconds < SCENARIO.steady_state_seconds:
        failures.append(
            f"steady window {obs.steady_seconds}s < required {SCENARIO.steady_state_seconds}s"
        )
    if obs.burst_seconds < SCENARIO.burst_seconds:
        failures.append(
            f"burst window {obs.burst_seconds}s < required {SCENARIO.burst_seconds}s"
        )

    # --- peak VU must reach the target ---
    if obs.peak_virtual_users < SCENARIO.target_virtual_users:
        failures.append(
            f"peak {obs.peak_virtual_users} VU < target {SCENARIO.target_virtual_users} VU"
        )

    # --- global thresholds ---
    if obs.error_rate_pct >= thresholds.max_error_rate_pct:
        failures.append(
            f"error rate {obs.error_rate_pct:.3f}% >= max {thresholds.max_error_rate_pct}%"
        )
    if obs.throughput_rps < thresholds.min_throughput_rps:
        failures.append(
            f"throughput {obs.throughput_rps:.0f} rps < floor {thresholds.min_throughput_rps:.0f} rps "
            f"(system effectively stalled at target VU)"
        )
    if obs.cross_project_leakage > thresholds.max_cross_project_leakage:
        failures.append(
            f"cross-project leakage {obs.cross_project_leakage} > "
            f"{thresholds.max_cross_project_leakage}"
        )
    if obs.duplicate_operation_effects > thresholds.max_duplicate_operation_effects:
        failures.append(
            f"duplicate operation side-effects {obs.duplicate_operation_effects} > "
            f"{thresholds.max_duplicate_operation_effects} (idempotency key must yield one op)"
        )
    if obs.lost_persisted_operations > thresholds.max_lost_persisted_operations:
        failures.append(
            f"lost persisted operations {obs.lost_persisted_operations} > "
            f"{thresholds.max_lost_persisted_operations} (design R4.3/R4.5: 不得永久 running / 伪装成功)"
        )

    # --- chaos / degradation (§7 / R4.3, R4.5) ---
    chaos_results: list[dict] = []
    for c in obs.chaos:
        c_failures: list[str] = []
        if not c.degraded_status_surfaced:
            c_failures.append("degraded status not surfaced ('等待工作进程')")
        if c.forbidden_terminal_states > thresholds.max_forbidden_terminal_states:
            c_failures.append(
                f"{c.forbidden_terminal_states} forbidden terminal state(s) during "
                f"{c.dependency} outage (fake succeeded / version-less recompute)"
            )
        if c.business_data_mutations > 0:
            c_failures.append(
                f"{c.business_data_mutations} mutation(s) to existing published results during "
                f"{c.dependency} outage (must be preserved)"
            )
        if not c.unaffected_ops_within_slo:
            c_failures.append(
                f"unaffected paths breached SLO during {c.dependency} outage (no isolation)"
            )
        chaos_results.append(
            {
                "dependency": c.dependency,
                "mode": c.mode,
                "ok": not c_failures,
                "reasons": c_failures,
            }
        )
        for cf in c_failures:
            failures.append(f"chaos[{c.dependency}]: {cf}")

    # --- connection budget invariant (design §6/§7) ---
    budget_check: BudgetCheck = check_budget(budget)
    if not budget_check.ok:
        for r in budget_check.reasons:
            failures.append(f"connection budget: {r}")

    return CapacityReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        spec=SCENARIO.spec,
        task=SCENARIO.task,
        requirements=list(SCENARIO.requirements),
        environment=obs.environment,
        passed=not failures,
        failures=failures,
        peak_virtual_users=obs.peak_virtual_users,
        target_virtual_users=SCENARIO.target_virtual_users,
        steady_seconds=obs.steady_seconds,
        burst_seconds=obs.burst_seconds,
        error_rate_pct=round(obs.error_rate_pct, 4),
        max_error_rate_pct=thresholds.max_error_rate_pct,
        throughput_rps=round(obs.throughput_rps, 2),
        min_throughput_rps=thresholds.min_throughput_rps,
        cross_project_leakage=obs.cross_project_leakage,
        duplicate_operation_effects=obs.duplicate_operation_effects,
        lost_persisted_operations=obs.lost_persisted_operations,
        backpressure_429_count=obs.backpressure_429_count,
        slo_results=[dataclasses.asdict(s) for s in slo_results],
        chaos_results=chaos_results,
        connection_budget=budget_check.to_dict(),
    )


def observations_from_locust_stats(
    stats: dict,
    *,
    peak_virtual_users: int,
    steady_seconds: int,
    burst_seconds: int,
    throughput_rps: float,
    environment: str = "capacity",
) -> CapacityObservations:
    """Adapt a Locust-stats-shaped dict into ``CapacityObservations``.

    ``stats`` carries, per named request entry: ``name``/``slo_op``,
    ``num_requests``, ``num_failures`` and ``p50_ms``/``p95_ms``/``p99_ms``.
    Custom counters (leakage / duplicate / lost / 429 / chaos) are read from the
    ``custom`` sub-dict the harness populates via events. Non-SLO helper
    requests (e.g. login) still count toward totals.
    """
    custom = stats.get("custom", {})
    op_latencies: list[OpLatency] = []
    total_requests = 0
    total_failures = 0

    for entry in stats.get("entries", []):
        op = entry.get("slo_op") or entry.get("name")
        nreq = int(entry.get("num_requests", 0))
        nfail = int(entry.get("num_failures", 0))
        total_requests += nreq
        total_failures += nfail
        if op not in SLO_BY_OP:
            continue
        op_latencies.append(
            OpLatency(
                op=op,
                p50_ms=float(entry.get("p50_ms", entry.get("p50", 0.0))),
                p95_ms=float(entry.get("p95_ms", entry.get("p95", 0.0))),
                p99_ms=float(entry.get("p99_ms", entry.get("p99", 0.0))),
                num_requests=nreq,
                num_failures=nfail,
            )
        )

    chaos = tuple(
        ChaosObservation(
            dependency=c["dependency"],
            mode=c.get("mode", ""),
            degraded_status_surfaced=bool(c.get("degraded_status_surfaced", False)),
            forbidden_terminal_states=int(c.get("forbidden_terminal_states", 0)),
            business_data_mutations=int(c.get("business_data_mutations", 0)),
            unaffected_ops_within_slo=bool(c.get("unaffected_ops_within_slo", True)),
        )
        for c in custom.get("chaos", [])
    )

    return CapacityObservations(
        peak_virtual_users=peak_virtual_users,
        steady_seconds=steady_seconds,
        burst_seconds=burst_seconds,
        total_requests=total_requests,
        total_failures=total_failures,
        throughput_rps=throughput_rps,
        op_latencies=tuple(op_latencies),
        cross_project_leakage=int(custom.get("cross_project_leakage", 0)),
        duplicate_operation_effects=int(custom.get("duplicate_operation_effects", 0)),
        lost_persisted_operations=int(custom.get("lost_persisted_operations", 0)),
        backpressure_429_count=int(custom.get("backpressure_429_count", 0)),
        chaos=chaos,
        warmup_excluded=True,
        environment=environment,
    )
