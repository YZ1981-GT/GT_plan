"""6000 并发报告不得把零样本的 0ms 判为通过。"""
from __future__ import annotations

from argparse import Namespace

from tests.load.run_final import STAGES, evaluate_results, generate_final_report


def _valid_stages() -> list[dict]:
    return [
        {
            "users": stage["users"],
            "user_count_actual": stage["users"],
            "requests": 100,
            "failures": 0,
            "p50": 100,
            "p95": 200,
            "p99": 300,
            "rps": 50,
        }
        for stage in STAGES
    ]


def test_zero_sample_6000_stage_is_hard_failure():
    stages = _valid_stages()
    stages[-1].update(user_count_actual=0, requests=0, p95=0, rps=0)
    evaluation = evaluate_results({
        "total": {"requests": 400, "failures": 0},
        "stages": stages,
    })

    assert evaluation["samples_pass"] is False
    assert evaluation["p95_pass"] is False
    assert evaluation["error_pass"] is False
    assert evaluation["overall_pass"] is False
    assert any("6000 用户阶段请求样本为 0" in item for item in evaluation["evidence_errors"])


def test_every_target_stage_must_reach_real_users_and_samples():
    stages = _valid_stages()
    stages[2]["user_count_actual"] = 899
    evaluation = evaluate_results({
        "total": {"requests": 500, "failures": 0},
        "stages": stages,
    })

    assert evaluation["overall_pass"] is False
    assert any("1000 用户阶段实际并发" in item for item in evaluation["evidence_errors"])


def test_complete_fast_run_passes_and_report_records_evidence_gate():
    stats = {
        "total": {"requests": 500, "failures": 0, "p99": 300, "rps": 600},
        "stages": _valid_stages(),
        "endpoints": [],
        "timestamp": "2026-11-01",
    }
    evaluation = evaluate_results(stats)
    report = generate_final_report(
        stats,
        Namespace(host="http://capacity.invalid", output="report.md"),
    )

    assert evaluation["overall_pass"] is True
    assert "样本完整性" in report
    assert "所有阶段均有真实样本" in report
    assert "最终结果:  PASS" in report
