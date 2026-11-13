"""Self-tests for the consolidation lifecycle capacity/chaos tooling (Task 8.4).

These verify the *tooling* is coherent and its threshold logic is correct — they
do NOT run 6000 VU and do NOT fake a capacity result. They exercise:
  * scenario integrity (traffic weights, SLO coverage, p50<=p95<=p99,
    steady/burst contract);
  * connection budget invariant (design §6/§7);
  * capacity report generator pass/fail logic (p50/p95/p99 SLO, error rate,
    throughput floor, leakage, duplicate operation, lost persisted operation);
  * chaos fail-closed degradation evaluation (§7 / R4.5).

This module MUST NOT ``import locust`` (importing locust triggers
gevent.monkey.patch_all() which deadlocks pytest — see backend/tests/conftest.py).
It imports only the pure deliverable modules.

Run: python -m pytest tests/load/consolidation_lifecycle_capacity/test_capacity_tooling.py -p no:playwright
(cwd = backend)
"""

from __future__ import annotations

import pytest

from .capacity_report import (
    CapacityObservations,
    ChaosObservation,
    OpLatency,
    generate_report,
    observations_from_locust_stats,
)
from .chaos import (
    FORBIDDEN_TERMINAL_STATES,
    build_default_fault_plan,
    evaluate_degradation,
    is_forbidden_terminal_state,
)
from .connection_budget import ConnectionBudget, ServicePoolBudget, check_budget
from .scenario import SCENARIO, SLO_BY_OP


# ---------------------------------------------------------------------------
# Scenario integrity
# ---------------------------------------------------------------------------

def test_scenario_validates():
    SCENARIO.validate()  # must not raise


def test_traffic_weights_sum_to_100():
    assert sum(c.weight_pct for c in SCENARIO.traffic_model) == 100


def test_traffic_model_is_consol_lifecycle():
    got = {c.name: c.weight_pct for c in SCENARIO.traffic_model}
    assert got == {
        "open_workbench": 45,
        "role_views_and_post_elim": 25,
        "operation_poll": 18,
        "operation_trigger": 9,
        "manual_snapshot": 3,
    }


def test_steady_and_burst_contract():
    assert SCENARIO.steady_state_seconds == 30 * 60
    assert SCENARIO.burst_seconds == 10 * 60
    steady_peak = max(p.users for p in SCENARIO.load_profile if p.kind == "steady")
    assert steady_peak == 6000


def test_slo_table_has_p50_p95_p99_ordered():
    for t in SCENARIO.slo_table:
        assert t.p50_ms <= t.p95_ms <= t.p99_ms, t.op


def test_slo_table_covers_every_traffic_op():
    ops = {op for c in SCENARIO.traffic_model for op in c.slo_ops}
    for op in ops:
        assert op in SLO_BY_OP


def test_slo_budgets_spot_check():
    assert (SLO_BY_OP["operation_status"].p50_ms,
            SLO_BY_OP["operation_status"].p95_ms,
            SLO_BY_OP["operation_status"].p99_ms) == (80, 200, 500)
    assert SLO_BY_OP["operation_create"].p95_ms == 1000
    assert SLO_BY_OP["manual_snapshot"].p99_ms == 5000


def test_scenario_json_roundtrip():
    import json

    data = SCENARIO.to_dict()
    assert data["target_virtual_users"] == 6000
    assert tuple(data["requirements"]) == ("R10", "R11")
    loaded = json.loads(SCENARIO.to_json())
    assert loaded["requirements"] == ["R10", "R11"]
    assert loaded["traffic_model"][0]["weight_pct"] == 45


def test_scenario_validate_rejects_bad_weights():
    import dataclasses

    from . import scenario as scen

    bad = dataclasses.replace(
        SCENARIO,
        traffic_model=(scen.TrafficClass("x", 50, "", ("readiness",)),),
    )
    with pytest.raises(ValueError):
        bad.validate()


def test_scenario_validate_rejects_bad_percentile_order():
    import dataclasses

    from . import scenario as scen

    bad = dataclasses.replace(
        SCENARIO,
        slo_table=(scen.SloTarget("readiness", p50_ms=500, p95_ms=300, p99_ms=1000, basis=""),),
    )
    with pytest.raises(ValueError):
        bad.validate()


# ---------------------------------------------------------------------------
# Connection budget invariant (design §6/§7)
# ---------------------------------------------------------------------------

def test_default_budget_ok():
    chk = check_budget()
    assert chk.ok, chk.reasons
    assert chk.pgbouncer_pool_mode == "transaction"
    assert chk.total_committed < chk.pg_max_connections
    assert chk.admin_reserve_pct >= 20.0
    assert chk.pgbouncer_max_client_conn >= 6000


def test_budget_over_committed_fails():
    b = ConnectionBudget(
        pg_max_connections=200,
        ops_reserve=10,
        pools=(ServicePoolBudget("api", 120, ""), ServicePoolBudget("worker", 120, "")),
    )
    chk = check_budget(b)
    assert not chk.ok
    assert any("< max_connections" in r for r in chk.reasons)


def test_budget_insufficient_admin_reserve_fails():
    b = ConnectionBudget(
        pg_max_connections=200,
        ops_reserve=10,
        pools=(ServicePoolBudget("api", 100, ""), ServicePoolBudget("worker", 65, "")),
    )
    chk = check_budget(b)
    # 165 committed -> reserve 35 = 17.5% < 20%
    assert not chk.ok
    assert any("reserve" in r for r in chk.reasons)


def test_budget_requires_transaction_pooling():
    chk = check_budget(ConnectionBudget(pgbouncer_pool_mode="session"))
    assert not chk.ok
    assert any("transaction" in r for r in chk.reasons)


def test_budget_rejects_worker_scaling_with_vus():
    b = ConnectionBudget(
        pools=(
            ServicePoolBudget("api_read", 90, ""),
            ServicePoolBudget("sse_longpoll", 20, ""),
            ServicePoolBudget("operation_worker", 40, "", scales_with_vus=True),
        )
    )
    chk = check_budget(b)
    assert not chk.ok
    assert any("operation_worker" in r and "scale" in r for r in chk.reasons)


def test_budget_rejects_low_max_client_conn():
    chk = check_budget(ConnectionBudget(pgbouncer_max_client_conn=3000))
    assert not chk.ok
    assert any("max_client_conn" in r for r in chk.reasons)


# ---------------------------------------------------------------------------
# Capacity report generator
# ---------------------------------------------------------------------------

def _passing_observations() -> CapacityObservations:
    return CapacityObservations(
        peak_virtual_users=7200,
        steady_seconds=1800,
        burst_seconds=600,
        total_requests=5_000_000,
        total_failures=2_500,  # 0.05% < 1%
        throughput_rps=1800.0,  # >= 1200 floor
        op_latencies=(
            OpLatency("readiness", p50_ms=90, p95_ms=260, p99_ms=800, num_requests=1_200_000, num_failures=300),
            OpLatency("role_views", p50_ms=120, p95_ms=360, p99_ms=1000, num_requests=400_000, num_failures=200),
            OpLatency("post_elimination", p50_ms=130, p95_ms=360, p99_ms=1050, num_requests=450_000, num_failures=200),
            OpLatency("trial_read", p50_ms=90, p95_ms=260, p99_ms=820, num_requests=350_000, num_failures=150),
            OpLatency("operation_list", p50_ms=70, p95_ms=200, p99_ms=600, num_requests=600_000, num_failures=100),
            OpLatency("operation_status", p50_ms=60, p95_ms=160, p99_ms=420, num_requests=700_000, num_failures=100),
            OpLatency("operation_create", p50_ms=250, p95_ms=850, p99_ms=2500, num_requests=40_000, num_failures=50),
            OpLatency("manual_snapshot", p50_ms=400, p95_ms=1600, p99_ms=4200, num_requests=12_000, num_failures=20),
        ),
        cross_project_leakage=0,
        duplicate_operation_effects=0,
        lost_persisted_operations=0,
        backpressure_429_count=5000,
        chaos=(
            ChaosObservation("redis", "unavailable", True, 0, 0, True),
            ChaosObservation("worker", "unavailable", True, 0, 0, True),
            ChaosObservation("db", "slow", True, 0, 0, True),
        ),
        warmup_excluded=True,
        environment="test",
    )


def test_report_passes_on_clean_run():
    report = generate_report(_passing_observations())
    assert report.passed, report.failures
    assert report.error_rate_pct < 1.0
    assert report.connection_budget["ok"]


def test_report_fails_on_p50_breach():
    import dataclasses

    obs = _passing_observations()
    breached = dataclasses.replace(
        obs,
        op_latencies=(
            OpLatency("readiness", p50_ms=200, p95_ms=260, p99_ms=800, num_requests=1_000_000, num_failures=100),
        ),
    )
    report = generate_report(breached)
    assert not report.passed
    assert any("readiness" in f and "p50" in f for f in report.failures)


def test_report_fails_on_p99_breach():
    import dataclasses

    obs = _passing_observations()
    breached = dataclasses.replace(
        obs,
        op_latencies=(
            OpLatency("operation_status", p50_ms=60, p95_ms=160, p99_ms=900, num_requests=700_000, num_failures=0),
        ),
    )
    report = generate_report(breached)
    assert not report.passed
    assert any("operation_status" in f and "p99" in f for f in report.failures)


def test_report_fails_on_high_error_rate():
    import dataclasses

    report = generate_report(dataclasses.replace(_passing_observations(), total_failures=100_000))  # 2%
    assert not report.passed
    assert any("error rate" in f for f in report.failures)


def test_report_fails_on_low_throughput():
    import dataclasses

    report = generate_report(dataclasses.replace(_passing_observations(), throughput_rps=500.0))
    assert not report.passed
    assert any("throughput" in f for f in report.failures)


def test_report_fails_on_cross_project_leakage():
    import dataclasses

    report = generate_report(dataclasses.replace(_passing_observations(), cross_project_leakage=1))
    assert not report.passed
    assert any("leakage" in f for f in report.failures)


def test_report_fails_on_duplicate_operation_effects():
    import dataclasses

    report = generate_report(dataclasses.replace(_passing_observations(), duplicate_operation_effects=1))
    assert not report.passed
    assert any("duplicate operation" in f for f in report.failures)


def test_report_fails_on_lost_persisted_operation():
    import dataclasses

    report = generate_report(dataclasses.replace(_passing_observations(), lost_persisted_operations=1))
    assert not report.passed
    assert any("lost persisted operations" in f for f in report.failures)


def test_report_fails_on_forbidden_terminal_state_under_chaos():
    import dataclasses

    obs = _passing_observations()
    bad_chaos = dataclasses.replace(
        obs,
        chaos=(ChaosObservation("worker", "unavailable", True, forbidden_terminal_states=1,
                                business_data_mutations=0, unaffected_ops_within_slo=True),),
    )
    report = generate_report(bad_chaos)
    assert not report.passed
    assert any("forbidden terminal state" in f for f in report.failures)


def test_report_fails_when_warmup_not_excluded():
    import dataclasses

    report = generate_report(dataclasses.replace(_passing_observations(), warmup_excluded=False))
    assert not report.passed
    assert any("warmup" in f for f in report.failures)


def test_report_fails_when_peak_below_target():
    import dataclasses

    report = generate_report(dataclasses.replace(_passing_observations(), peak_virtual_users=3000))
    assert not report.passed
    assert any("VU" in f for f in report.failures)


def test_report_fails_on_short_steady_window():
    import dataclasses

    report = generate_report(dataclasses.replace(_passing_observations(), steady_seconds=600))
    assert not report.passed
    assert any("steady window" in f for f in report.failures)


def test_report_fails_on_unknown_slo_op():
    import dataclasses

    obs = _passing_observations()
    bad = dataclasses.replace(
        obs,
        op_latencies=(OpLatency("not_a_real_op", 10, 20, 30, 100, 0),),
    )
    report = generate_report(bad)
    assert not report.passed
    assert any("unknown SLO op" in f for f in report.failures)


def test_report_is_json_serialisable():
    report = generate_report(_passing_observations())
    text = report.to_json()
    assert '"passed": true' in text


# ---------------------------------------------------------------------------
# Locust stats adapter
# ---------------------------------------------------------------------------

def test_observations_from_locust_stats():
    stats = {
        "entries": [
            {"slo_op": "readiness", "num_requests": 100, "num_failures": 0, "p50_ms": 80, "p95_ms": 150, "p99_ms": 400},
            {"slo_op": "operation_create", "num_requests": 20, "num_failures": 0, "p50_ms": 200, "p95_ms": 800, "p99_ms": 2000},
            {"name": "login", "num_requests": 10, "num_failures": 0},
        ],
        "custom": {
            "cross_project_leakage": 0,
            "duplicate_operation_effects": 0,
            "lost_persisted_operations": 0,
            "backpressure_429_count": 5,
            "chaos": [
                {"dependency": "worker", "mode": "unavailable", "degraded_status_surfaced": True,
                 "forbidden_terminal_states": 0, "business_data_mutations": 0,
                 "unaffected_ops_within_slo": True},
            ],
        },
    }
    obs = observations_from_locust_stats(
        stats, peak_virtual_users=7200, steady_seconds=1800, burst_seconds=600,
        throughput_rps=1500.0,
    )
    assert obs.total_requests == 130
    assert {lat.op for lat in obs.op_latencies} == {"readiness", "operation_create"}
    assert obs.throughput_rps == 1500.0
    assert len(obs.chaos) == 1


# ---------------------------------------------------------------------------
# Chaos
# ---------------------------------------------------------------------------

def test_forbidden_terminal_states():
    assert set(FORBIDDEN_TERMINAL_STATES) == {"succeeded", "legacy_recompute"}
    assert is_forbidden_terminal_state("succeeded")
    assert is_forbidden_terminal_state("legacy_recompute")
    assert not is_forbidden_terminal_state("queued")


def test_evaluate_degradation_pass():
    ok, reasons = evaluate_degradation(
        dependency="worker",
        degraded_status_surfaced=True,
        produced_terminal_states=["queued", "failed"],
        business_data_mutations=0,
        unaffected_ops_within_slo=True,
    )
    assert ok
    assert reasons == []


def test_evaluate_degradation_detects_fake_success():
    ok, reasons = evaluate_degradation(
        dependency="worker",
        degraded_status_surfaced=True,
        produced_terminal_states=["succeeded"],
        business_data_mutations=0,
        unaffected_ops_within_slo=True,
    )
    assert not ok
    assert any("forbidden terminal state" in r for r in reasons)


def test_evaluate_degradation_detects_version_less_recompute():
    ok, reasons = evaluate_degradation(
        dependency="redis",
        degraded_status_surfaced=True,
        produced_terminal_states=["legacy_recompute"],
        business_data_mutations=0,
        unaffected_ops_within_slo=True,
    )
    assert not ok
    assert any("forbidden terminal state" in r for r in reasons)


def test_evaluate_degradation_detects_missing_degraded_status():
    ok, reasons = evaluate_degradation(
        dependency="redis",
        degraded_status_surfaced=False,
        produced_terminal_states=[],
        business_data_mutations=0,
        unaffected_ops_within_slo=True,
    )
    assert not ok
    assert any("degraded status" in r for r in reasons)


def test_fault_plan_staggers_across_burst():
    plan = build_default_fault_plan(burst_start_offset_s=2000, burst_duration_s=600)
    timeline = plan.to_env_timeline()
    assert len(timeline) == 3
    deps = [t["dependency"] for t in timeline]
    assert deps == ["redis", "worker", "db"]
    for a, b in zip(timeline, timeline[1:]):
        assert a["end_offset_s"] <= b["start_offset_s"]
    assert timeline[0]["env_key"] == "CONSOL_CHAOS_REDIS"
    assert timeline[1]["env_key"] == "CONSOL_CHAOS_WORKER"


# ---------------------------------------------------------------------------
# Guard: this tooling package must not import locust at module scope (deadlocks
# pytest via gevent). We assert locust is not in sys.modules after importing the
# pure deliverable modules above.
# ---------------------------------------------------------------------------

def test_tooling_import_does_not_pull_in_locust():
    import sys

    assert "locust" not in sys.modules, (
        "importing the capacity tooling must not import locust (gevent monkey "
        "patch would deadlock pytest)"
    )
