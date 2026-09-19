"""Self-tests for the Evidence Governance capacity/chaos tooling (Task 8.2).

These verify the *tooling* is coherent and its threshold logic is correct — they
do NOT run 6000 VU and do NOT fake a capacity result. They exercise:
  * scenario integrity (traffic weights, SLO coverage, steady/burst contract);
  * connection budget invariant (design §9.2);
  * capacity report generator pass/fail logic (design §9.1 thresholds);
  * chaos fail-closed degradation evaluation (R15.3).

Run: python -m pytest tests/load/evidence_governance_capacity/test_capacity_tooling.py
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


def test_traffic_model_is_70_20_7_3():
    got = {c.name: c.weight_pct for c in SCENARIO.traffic_model}
    assert got == {
        "metadata_read": 70,
        "write_associate": 20,
        "ocr_ai_enqueue": 7,
        "impact_archive_control": 3,
    }


def test_steady_and_burst_contract():
    assert SCENARIO.steady_state_seconds == 30 * 60
    assert SCENARIO.burst_seconds == 10 * 60
    steady_peak = max(p.users for p in SCENARIO.load_profile if p.kind == "steady")
    assert steady_peak == 6000


def test_slo_table_matches_design_9_1():
    # spot-check the design §9.1 budgets are encoded verbatim
    assert SLO_BY_OP["metadata_read"].p95_ms == 200
    assert SLO_BY_OP["cursor_list"].p95_ms == 300
    assert SLO_BY_OP["impact_le_100_nodes"].p95_ms == 500
    assert SLO_BY_OP["governance_write"].p95_ms == 500
    assert SLO_BY_OP["staged_enqueue"].p95_ms == 300
    assert SLO_BY_OP["sync_finalize_create"].p95_ms == 1000
    assert SLO_BY_OP["finalize_external_task"].p95_ms == 30000
    assert SLO_BY_OP["formal_preflight_le_500_deps"].p95_ms == 750
    assert SLO_BY_OP["stale_enqueue"].p95_ms == 200
    assert SLO_BY_OP["archive_request"].p95_ms == 500


def test_scenario_json_roundtrip():
    import json

    data = SCENARIO.to_dict()
    assert data["target_virtual_users"] == 6000
    assert tuple(data["requirements"]) == ("R12", "R15")
    # to_json emits JSON arrays and is loadable
    loaded = json.loads(SCENARIO.to_json())
    assert loaded["requirements"] == ["R12", "R15"]
    assert loaded["traffic_model"][0]["weight_pct"] == 70


def test_scenario_validate_rejects_bad_weights(monkeypatch):
    import dataclasses

    from . import scenario as scen

    bad = dataclasses.replace(
        SCENARIO,
        traffic_model=(scen.TrafficClass("x", 50, "", ("metadata_read",)),),
    )
    with pytest.raises(ValueError):
        bad.validate()


# ---------------------------------------------------------------------------
# Connection budget invariant (design §9.2)
# ---------------------------------------------------------------------------

def test_default_budget_ok():
    chk = check_budget()
    assert chk.ok, chk.reasons
    assert chk.pgbouncer_pool_mode == "transaction"
    # total committed strictly below max_connections
    assert chk.total_committed < chk.pg_max_connections
    # >= 20% reserved for admin/recovery
    assert chk.admin_reserve_pct >= 20.0


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
    # 150 service + 10 ops = 160 committed of 200 -> only 20% left, but push it
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
    b = ConnectionBudget(pgbouncer_pool_mode="session")
    chk = check_budget(b)
    assert not chk.ok
    assert any("transaction" in r for r in chk.reasons)


# ---------------------------------------------------------------------------
# Capacity report generator
# ---------------------------------------------------------------------------

def _passing_observations() -> CapacityObservations:
    return CapacityObservations(
        peak_virtual_users=7200,
        steady_seconds=1800,
        burst_seconds=600,
        total_requests=1_000_000,
        total_failures=500,  # 0.05% < 1%
        op_latencies=(
            OpLatency("metadata_read", p95_ms=180, p50_ms=40, num_requests=700_000, num_failures=100),
            OpLatency("cursor_list", p95_ms=280, p50_ms=90, num_requests=200_000, num_failures=100),
            OpLatency("governance_write", p95_ms=470, p50_ms=120, num_requests=80_000, num_failures=100),
            OpLatency("staged_enqueue", p95_ms=250, p50_ms=90, num_requests=15_000, num_failures=100),
            OpLatency("impact_le_100_nodes", p95_ms=480, p50_ms=150, num_requests=4_000, num_failures=50),
            OpLatency("archive_request", p95_ms=430, p50_ms=200, num_requests=1_000, num_failures=50),
        ),
        cross_project_leakage=0,
        duplicate_side_effects=0,
        lost_persisted_jobs=0,
        backpressure_429_count=1234,
        chaos=(
            ChaosObservation("storage", "unavailable", True, 0, 0, True),
            ChaosObservation("ocr", "timeout", True, 0, 0, True),
            ChaosObservation("retrieval", "unverifiable", True, 0, 0, True),
            ChaosObservation("ai", "stub", True, 0, 0, True),
        ),
        warmup_excluded=True,
        environment="test",
    )


def test_report_passes_on_clean_run():
    report = generate_report(_passing_observations())
    assert report.passed, report.failures
    assert report.error_rate_pct < 1.0
    assert report.connection_budget["ok"]


def test_report_fails_on_slo_breach():
    import dataclasses

    obs = _passing_observations()
    breached = dataclasses.replace(
        obs,
        op_latencies=(
            OpLatency("metadata_read", p95_ms=250, p50_ms=40, num_requests=700_000, num_failures=100),
        ),
    )
    report = generate_report(breached)
    assert not report.passed
    assert any("metadata_read" in f and "SLO breach" in f for f in report.failures)


def test_report_fails_on_high_error_rate():
    import dataclasses

    obs = _passing_observations()
    bad = dataclasses.replace(obs, total_failures=20_000)  # 2%
    report = generate_report(bad)
    assert not report.passed
    assert any("error rate" in f for f in report.failures)


def test_report_fails_on_cross_project_leakage():
    import dataclasses

    report = generate_report(dataclasses.replace(_passing_observations(), cross_project_leakage=1))
    assert not report.passed
    assert any("leakage" in f for f in report.failures)


def test_report_fails_on_duplicate_side_effects():
    import dataclasses

    report = generate_report(dataclasses.replace(_passing_observations(), duplicate_side_effects=1))
    assert not report.passed
    assert any("duplicate" in f for f in report.failures)


def test_report_fails_on_lost_persisted_job():
    import dataclasses

    report = generate_report(dataclasses.replace(_passing_observations(), lost_persisted_jobs=1))
    assert not report.passed
    assert any("lost persisted jobs" in f for f in report.failures)


def test_report_fails_on_forbidden_terminal_state_under_chaos():
    import dataclasses

    obs = _passing_observations()
    bad_chaos = dataclasses.replace(
        obs,
        chaos=(ChaosObservation("ocr", "timeout", True, forbidden_terminal_states=1,
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
            {"slo_op": "metadata_read", "num_requests": 100, "num_failures": 0, "p95_ms": 150, "p50_ms": 40},
            {"slo_op": "governance_write", "num_requests": 20, "num_failures": 0, "p95_ms": 400, "p50_ms": 100},
            {"name": "login", "num_requests": 10, "num_failures": 0},
        ],
        "custom": {
            "cross_project_leakage": 0,
            "duplicate_side_effects": 0,
            "lost_persisted_jobs": 0,
            "backpressure_429_count": 5,
            "chaos": [
                {"dependency": "ocr", "mode": "timeout", "degraded_status_surfaced": True,
                 "forbidden_terminal_states": 0, "business_data_mutations": 0,
                 "unaffected_ops_within_slo": True},
            ],
        },
    }
    obs = observations_from_locust_stats(
        stats, peak_virtual_users=7200, steady_seconds=1800, burst_seconds=600
    )
    assert obs.total_requests == 130
    assert {l.op for l in obs.op_latencies} == {"metadata_read", "governance_write"}
    assert len(obs.chaos) == 1


# ---------------------------------------------------------------------------
# Chaos
# ---------------------------------------------------------------------------

def test_forbidden_terminal_states():
    assert set(FORBIDDEN_TERMINAL_STATES) == {"confirmed", "written_back", "archived"}
    assert is_forbidden_terminal_state("archived")
    assert not is_forbidden_terminal_state("queued")


def test_evaluate_degradation_pass():
    ok, reasons = evaluate_degradation(
        dependency="ocr",
        degraded_status_surfaced=True,
        produced_terminal_states=["queued", "failed"],
        business_data_mutations=0,
        unaffected_ops_within_slo=True,
    )
    assert ok
    assert reasons == []


def test_evaluate_degradation_detects_forbidden_state():
    ok, reasons = evaluate_degradation(
        dependency="ai",
        degraded_status_surfaced=True,
        produced_terminal_states=["confirmed"],
        business_data_mutations=0,
        unaffected_ops_within_slo=True,
    )
    assert not ok
    assert any("forbidden terminal state" in r for r in reasons)


def test_evaluate_degradation_detects_missing_degraded_status():
    ok, reasons = evaluate_degradation(
        dependency="storage",
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
    assert len(timeline) == 4
    deps = [t["dependency"] for t in timeline]
    assert deps == ["storage", "ocr", "retrieval", "ai"]
    # windows are non-overlapping and ordered
    for a, b in zip(timeline, timeline[1:]):
        assert a["end_offset_s"] <= b["start_offset_s"]
    # all env keys present
    assert timeline[1]["env_key"] == "EVIDENCE_CHAOS_OCR"
