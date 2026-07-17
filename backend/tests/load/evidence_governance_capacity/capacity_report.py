"""Machine-readable capacity report schema + generator + threshold assertions.

Spec: attachment-ocr-ai-evidence-governance-hardening — Task 8.2
Requirements: R12, R15
Design: §9.1 SLO table + global thresholds, §9.2 backpressure, §10.2 layer 6.

The report generator is a *pure* function over an observation payload
(``CapacityObservations``). It does not run load itself — the Locust harness
(or any capacity runner) collects observations and hands them here. This keeps
the pass/fail logic deterministic, unit-testable, and independent of whether an
actual 6000 VU environment was available.

A report is PASS only when every one of the following holds (design §9.1):
  * every measured SLO op P95 <= its §9.1 budget (warmup excluded);
  * error rate < 1%;
  * cross-project canary leakage == 0;
  * duplicate side-effects == 0;
  * no forbidden terminal state under chaos (confirmed/written_back/archived);
  * no persisted job lost under backpressure;
  * the PG/PgBouncer connection budget invariant holds.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
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
    p95_ms: float
    p50_ms: float
    num_requests: int
    num_failures: int


@dataclass(frozen=True)
class ChaosObservation:
    """What happened while a dependency fault was active."""

    dependency: str
    mode: str
    degraded_status_surfaced: bool
    forbidden_terminal_states: int  # confirmed/written_back/archived produced despite fault
    business_data_mutations: int    # unexpected mutations to existing business data
    unaffected_ops_within_slo: bool


@dataclass(frozen=True)
class CapacityObservations:
    """Everything a run must report for the generator to render a verdict."""

    peak_virtual_users: int
    steady_seconds: int
    burst_seconds: int
    total_requests: int
    total_failures: int
    op_latencies: tuple[OpLatency, ...]
    cross_project_leakage: int
    duplicate_side_effects: int
    lost_persisted_jobs: int
    backpressure_429_count: int
    chaos: tuple[ChaosObservation, ...] = ()
    # Whether measurements exclude warmup (they must, per §9.1 "steady + burst").
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
    p95_ms: float
    budget_ms: int
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
    cross_project_leakage: int
    duplicate_side_effects: int
    lost_persisted_jobs: int
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

    # --- SLO P95 gates (design §9.1) ---
    slo_results: list[SloResult] = []
    for lat in obs.op_latencies:
        target = SLO_BY_OP.get(lat.op)
        if target is None:
            failures.append(f"observed unknown SLO op {lat.op!r} (not in §9.1 table)")
            continue
        ok = lat.p95_ms <= target.p95_ms
        slo_results.append(
            SloResult(
                op=lat.op,
                p95_ms=lat.p95_ms,
                budget_ms=target.p95_ms,
                num_requests=lat.num_requests,
                ok=ok,
            )
        )
        if not ok:
            failures.append(
                f"SLO breach {lat.op}: P95 {lat.p95_ms:.0f}ms > budget {target.p95_ms}ms"
            )

    # --- warmup must be excluded from the measurement window ---
    if not obs.warmup_excluded:
        failures.append("measurement window includes warmup; §9.1 requires steady+burst only")

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

    # --- global thresholds (R15.1) ---
    if obs.error_rate_pct >= thresholds.max_error_rate_pct:
        failures.append(
            f"error rate {obs.error_rate_pct:.3f}% >= max {thresholds.max_error_rate_pct}%"
        )
    if obs.cross_project_leakage > thresholds.max_cross_project_leakage:
        failures.append(
            f"cross-project leakage {obs.cross_project_leakage} > "
            f"{thresholds.max_cross_project_leakage}"
        )
    if obs.duplicate_side_effects > thresholds.max_duplicate_side_effects:
        failures.append(
            f"duplicate side-effects {obs.duplicate_side_effects} > "
            f"{thresholds.max_duplicate_side_effects}"
        )
    if obs.lost_persisted_jobs > thresholds.max_lost_persisted_jobs:
        failures.append(
            f"lost persisted jobs {obs.lost_persisted_jobs} > "
            f"{thresholds.max_lost_persisted_jobs} (design §9.2: 已持久 job 不丢失)"
        )

    # --- chaos / degradation (R15.3) ---
    chaos_results: list[dict] = []
    for c in obs.chaos:
        c_failures: list[str] = []
        if not c.degraded_status_surfaced:
            c_failures.append("degraded status not surfaced")
        if c.forbidden_terminal_states > thresholds.max_forbidden_terminal_states:
            c_failures.append(
                f"{c.forbidden_terminal_states} forbidden terminal state(s) produced "
                f"during {c.dependency} outage (must be fail-closed)"
            )
        if c.business_data_mutations > 0:
            c_failures.append(
                f"{c.business_data_mutations} business-data mutation(s) during "
                f"{c.dependency} outage (existing data must be preserved)"
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

    # --- connection budget invariant (design §9.2) ---
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
        cross_project_leakage=obs.cross_project_leakage,
        duplicate_side_effects=obs.duplicate_side_effects,
        lost_persisted_jobs=obs.lost_persisted_jobs,
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
    environment: str = "capacity",
) -> CapacityObservations:
    """Adapt a Locust ``environment.runner.stats.serialize_stats()``-shaped dict.

    ``stats`` is expected to carry, per named request entry, the fields Locust
    exposes: ``name``, ``num_requests``, ``num_failures``, and a
    ``response_time_percentiles`` mapping (or ``get_response_time_percentile``).
    The Locust harness annotates request ``name`` with the SLO op so this adapter
    maps cleanly. Custom counters (leakage/duplicate/lost/429/chaos) are read
    from the ``custom`` sub-dict the harness populates via events.
    """
    custom = stats.get("custom", {})
    op_latencies: list[OpLatency] = []
    total_requests = 0
    total_failures = 0

    for entry in stats.get("entries", []):
        op = entry.get("slo_op") or entry.get("name")
        if op not in SLO_BY_OP:
            # non-SLO helper request (e.g. login) — still counts toward totals
            total_requests += int(entry.get("num_requests", 0))
            total_failures += int(entry.get("num_failures", 0))
            continue
        nreq = int(entry.get("num_requests", 0))
        nfail = int(entry.get("num_failures", 0))
        total_requests += nreq
        total_failures += nfail
        op_latencies.append(
            OpLatency(
                op=op,
                p95_ms=float(entry.get("p95_ms", entry.get("p95", 0.0))),
                p50_ms=float(entry.get("p50_ms", entry.get("p50", 0.0))),
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
        op_latencies=tuple(op_latencies),
        cross_project_leakage=int(custom.get("cross_project_leakage", 0)),
        duplicate_side_effects=int(custom.get("duplicate_side_effects", 0)),
        lost_persisted_jobs=int(custom.get("lost_persisted_jobs", 0)),
        backpressure_429_count=int(custom.get("backpressure_429_count", 0)),
        chaos=chaos,
        warmup_excluded=True,
        environment=environment,
    )
