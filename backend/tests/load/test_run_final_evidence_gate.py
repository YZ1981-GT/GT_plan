"""E5/E6 正式阶段、稳态窗口统计、核心 SLO、安全证据、A/B 与机器可读证据合同。

本文件绝不 ``import locust`` / ``locustfile``（gevent 猴子补丁会卡死 pytest 进程）；
locustfile 的接线用 AST 读源码核对。
"""
from __future__ import annotations

import ast
import json
from argparse import Namespace
from pathlib import Path

import pytest

from tests.load.load_contract import (
    CORE_READ_ENDPOINTS,
    LOAD_STAGES,
    SAFETY_ZERO_KEYS,
    STEADY_SETTLE_SECONDS,
)
from tests.load.load_evaluation import compare_to_baseline, load_baseline_summary, load_safety_evidence
from tests.load.load_stage_stats import (
    STAGE_STATS_FILE_NAME,
    StageRecorder,
    bucket_ms,
    load_stage_stats,
    percentile,
    stage_timeline,
    summarize_stage_payload,
)
from tests.load.run_final import (
    STAGES,
    _prepare_external_evidence,
    evaluate_results,
    generate_final_report,
    parse_csv_results,
    write_evidence_json,
)

LOCUSTFILE = Path(__file__).resolve().parent / "locustfile.py"
REQUIRED_SECONDS = {item["users"]: item["required_seconds"] for item in stage_timeline()}


def _safety(**updates) -> dict:
    values = {key: 0 for key in SAFETY_ZERO_KEYS}
    values.update(updates)
    return values


def _core_endpoints(*, p95: float = 200, p99: float = 300,
                    requests: int = 100, failures: int = 0) -> list[dict]:
    return [
        {
            "name": name, "type": "GET", "requests": requests, "failures": failures,
            "p50": 100, "p95": p95, "p99": p99, "rps": 50,
        }
        for name in CORE_READ_ENDPOINTS
    ]


def _valid_stages() -> list[dict]:
    stages = [
        {
            "users": int(stage["users"]),
            "duration": int(stage["duration"]),
            "user_count_actual": int(stage["users"]),
            "covered_seconds": REQUIRED_SECONDS[int(stage["users"])],
            "requests": 100,
            "failures": 0,
            "p50": 100,
            "p95": 200,
            "p99": 300,
            "rps": 50,
            "endpoints": [],
        }
        for stage in STAGES
    ]
    stages[-1]["endpoints"] = _core_endpoints()
    return stages


def _valid_stats() -> dict:
    return {
        "total": {"requests": 400, "failures": 0, "median": 100,
                  "p95": 200, "p99": 300, "avg": 120, "rps": 600},
        "stages": _valid_stages(),
        "endpoints": _core_endpoints(),
        "safety": _safety(),
        "timestamp": "2026-11-06",
    }


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _strict_json(text: str):
    def reject(constant: str):
        raise AssertionError(f"证据文件含非严格 JSON 常量：{constant}")

    return json.loads(text, parse_constant=reject)


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"locustfile 缺函数 {name}")


def _listener_event(func: ast.FunctionDef) -> str | None:
    for decorator in func.decorator_list:
        if (isinstance(decorator, ast.Attribute) and decorator.attr == "add_listener"
                and isinstance(decorator.value, ast.Attribute)
                and isinstance(decorator.value.value, ast.Name)
                and decorator.value.value.id == "events"):
            return decorator.value.attr
    return None


def _recorder_calls(node: ast.AST) -> set[str]:
    return {
        call.func.attr
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "_STAGE_RECORDER"
    }


# ── E5 正式梯度、稳态窗口与 locustfile 接线 ─────────────────────────────

def test_formal_shape_is_exact_and_6000_steady_is_30_minutes():
    assert [stage["users"] for stage in LOAD_STAGES] == [100, 1000, 3000, 6000]
    assert LOAD_STAGES[-1]["duration"] == 1800
    assert STAGES == [dict(stage) for stage in LOAD_STAGES]


def test_stage_timeline_windows_exclude_ramp_and_settle():
    timeline = stage_timeline()
    assert [item["users"] for item in timeline] == [100, 1000, 3000, 6000]
    previous_end = 0.0
    for item, stage in zip(timeline, LOAD_STAGES):
        ramp = stage["users"] / stage["spawn_rate"]
        assert item["begin_s"] == pytest.approx(previous_end)
        assert item["steady_start_s"] == pytest.approx(previous_end + ramp + STEADY_SETTLE_SECONDS)
        assert item["end_s"] == pytest.approx(previous_end + ramp + stage["duration"])
        previous_end = item["end_s"]
    assert timeline[-1]["required_seconds"] == pytest.approx(1800 - STEADY_SETTLE_SECONDS)
    with pytest.raises(ValueError, match="稳态时长不足"):
        stage_timeline([{"users": 10, "spawn_rate": 10, "duration": 3}])


def test_locustfile_wires_stage_recorder_and_shape_to_one_timeline():
    tree = ast.parse(LOCUSTFILE.read_text(encoding="utf-8"))
    hooks = {"on_request": "request", "on_test_start": "test_start", "on_test_stop": "test_stop"}
    for name, event in hooks.items():
        assert _listener_event(_function(tree, name)) == event
    assert "record" in _recorder_calls(_function(tree, "on_request"))
    assert "start" in _recorder_calls(_function(tree, "on_test_start"))
    assert {"stop", "write"} <= _recorder_calls(_function(tree, "on_test_stop"))
    shape = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "StepLoadShape"
    )
    names = {node.id for node in ast.walk(shape) if isinstance(node, ast.Name)}
    assert "stage_timeline" in names
    assert "LOAD_STAGES" not in names  # 形状不得另算一套阶段边界


# ── 稳态窗口逐请求统计 ─────────────────────────────────────────────

def test_bucket_and_percentile_follow_locust_rounding_and_nearest_rank():
    assert [bucket_ms(v) for v in (0, 99.4, 304, 306, 1234, 12345)] == [0, 99, 300, 310, 1200, 12000]
    assert percentile({}, 0.95) is None
    assert percentile({100: 1}, 0.99) == 100.0
    histogram = {100: 900, 1000: 100}
    assert percentile(histogram, 0.90) == 100.0
    assert percentile(histogram, 0.95) == 1000.0


def test_stage_recorder_uses_full_steady_window_not_last_seconds():
    clock = _Clock()
    timeline = stage_timeline()
    first = timeline[0]
    recorder = StageRecorder(timeline, clock=clock)
    recorder.start()
    name = CORE_READ_ENDPOINTS[0]

    def hit(response_time: float, *, failed: bool = False, users: int = 100) -> None:
        recorder.record(name=name, request_type="GET", response_time=response_time,
                        failed=failed, user_count=users)

    clock.now = 1000.0 + first["steady_start_s"] - 0.5  # 加压 + settle 期
    hit(5000, users=80)
    clock.now = 1000.0 + first["steady_start_s"] + 1  # 稳态前段：慢
    for _ in range(900):
        hit(1000)
    clock.now = 1000.0 + first["end_s"] - 1  # 稳态最后 1 秒：快、且失败
    for _ in range(100):
        hit(100, failed=True)
    clock.now = 1000.0 + first["end_s"] + 0.5  # 下一阶段加压期
    hit(9000, users=500)
    recorder.stop()

    stages = summarize_stage_payload(recorder.to_payload())
    stage = stages[0]
    assert (stage["requests"], stage["failures"]) == (1000, 100)
    assert stage["p95"] == 1000.0  # 只看最后 10 秒会得到 100ms 假绿
    assert (stage["user_count_actual"], stage["user_count_max"]) == (100, 100)
    assert stage["covered_seconds"] == pytest.approx(first["required_seconds"])
    [endpoint] = stage["endpoints"]
    assert (endpoint["name"], endpoint["type"], endpoint["requests"]) == (name, "GET", 1000)
    assert all(item["requests"] == 0 for item in stages[1:])
    assert stages[1]["p95"] is None


def test_short_6000_steady_window_is_reported_and_blocks_pass():
    clock = _Clock()
    timeline = stage_timeline()
    last = timeline[-1]
    recorder = StageRecorder(timeline, clock=clock)
    recorder.record(name="早到", request_type="GET", response_time=1, failed=False, user_count=1)
    recorder.start()
    clock.now = 1000.0 + last["steady_start_s"] + 600  # 6000 稳态只跑了 600 秒
    recorder.record(name=CORE_READ_ENDPOINTS[0], request_type="GET", response_time=50,
                    failed=False, user_count=6000)
    recorder.stop()
    clock.now += 60
    recorder.record(name="迟到", request_type="GET", response_time=1, failed=False, user_count=6000)
    stage = summarize_stage_payload(recorder.to_payload())[-1]
    assert stage["requests"] == 1
    assert stage["covered_seconds"] == pytest.approx(600)

    stats = _valid_stats()
    stats["stages"][-1]["covered_seconds"] = stage["covered_seconds"]
    evaluation = evaluate_results(stats)
    assert evaluation["samples_pass"] is False
    assert any("6000 用户阶段稳态仅覆盖 600 秒" in item for item in evaluation["evidence_errors"])


def test_stage_stats_file_round_trip_and_tampering_is_rejected(tmp_path):
    clock = _Clock()
    recorder = StageRecorder(clock=clock)
    recorder.start()
    clock.now += stage_timeline()[0]["steady_start_s"] + 1
    recorder.record(name="/api/auth/login", request_type="POST", response_time=42,
                    failed=False, user_count=100)
    recorder.stop()
    path = recorder.write(tmp_path / STAGE_STATS_FILE_NAME)
    assert not list(tmp_path.glob("*.tmp"))
    stages = load_stage_stats(path)
    assert (stages[0]["requests"], stages[0]["p99"]) == (1, 42.0)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["stages"][0]["aggregate"]["histogram"] == {"42": 1}
    payload["stages"][0]["aggregate"]["requests"] = 2
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="histogram 计数与 requests 不一致"):
        load_stage_stats(path)

    path.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="不是合法 JSON"):
        load_stage_stats(path)
    with pytest.raises(ValueError, match="未生成"):
        load_stage_stats(tmp_path / "absent.json")
    with pytest.raises(ValueError, match="schema_version"):
        summarize_stage_payload({"schema_version": 99, "stages": []})


_STATS_CSV_HEADER = (
    "Type,Name,Request Count,Failure Count,Median Response Time,Average Response Time,"
    "Min Response Time,Max Response Time,Average Content Size,Requests/s,Failures/s,"
    "50%,66%,75%,80%,90%,95%,98%,99%,99.9%,99.99%,100%\n"
)


def test_parse_csv_results_reads_totals_and_requires_stage_stats(tmp_path):
    prefix = tmp_path / "locust"
    (tmp_path / "locust_stats.csv").write_text(
        _STATS_CSV_HEADER
        + "GET,/api/projects/{pid}/trial-balance,90,0,120,130,10,900,100,3.0,0,"
          "120,130,140,150,180,250,280,290,800,900,900\n"
        + ",Aggregated,100,1,120,130,10,900,100,3.3,0,"
          "120,130,140,150,180,250,280,290,800,900,900\n",
        encoding="utf-8",
    )
    results = parse_csv_results(prefix)
    assert (results["total"]["requests"], results["total"]["failures"]) == (100, 1)
    assert results["endpoints"][0]["p95"] == 250.0
    assert results["stages"] == []
    assert "未生成" in results["stage_stats_error"]
    evaluation = evaluate_results({**results, "safety": _safety()})
    assert evaluation["overall_pass"] is False
    assert any("稳态窗口统计不可用" in item for item in evaluation["evidence_errors"])

    recorder = StageRecorder(clock=_Clock())
    recorder.start()
    recorder.stop()
    recorder.write(tmp_path / STAGE_STATS_FILE_NAME)
    results = parse_csv_results(prefix)
    assert "stage_stats_error" not in results
    assert results["stage_stats_file"] == STAGE_STATS_FILE_NAME
    assert [stage["users"] for stage in results["stages"]] == [100, 1000, 3000, 6000]


# ── E6 判定 ─────────────────────────────────────────────────────

def test_complete_run_passes_and_report_records_all_gates():
    stats = _valid_stats()
    evaluation = evaluate_results(stats)
    report = generate_final_report(stats, Namespace(host="http://capacity.invalid"))
    assert evaluation["overall_pass"] is True
    assert "样本完整性" in report
    assert "所有阶段均有真实样本" in report
    assert "核心读 P95 ≤ 300ms" in report
    assert "核心读 P99 ≤ 1000ms" in report
    assert "不声称已完成 A/B" in report
    assert "最终结果:  PASS" in report


def test_zero_sample_6000_stage_is_hard_failure():
    stats = _valid_stats()
    stats["stages"][-1].update(user_count_actual=0, requests=0, p95=None, p99=None, rps=0)
    stats["stages"][-1]["endpoints"] = []
    evaluation = evaluate_results(stats)
    report = generate_final_report(stats, Namespace(host="http://capacity.invalid"))
    assert evaluation["samples_pass"] is False
    assert evaluation["overall_pass"] is False
    assert any("6000 用户阶段请求样本为 0" in item for item in evaluation["evidence_errors"])
    assert "最终结果:  FAIL" in report


def test_every_target_stage_must_reach_real_users():
    stats = _valid_stats()
    stage_1000 = next(stage for stage in stats["stages"] if stage["users"] == 1000)
    stage_1000["user_count_actual"] = 899
    evaluation = evaluate_results(stats)
    assert evaluation["overall_pass"] is False
    assert any("1000 用户阶段实际并发仅 899" in item for item in evaluation["evidence_errors"])


def test_missing_stage_is_hard_failure():
    stats = _valid_stats()
    stats["stages"] = [stage for stage in stats["stages"] if stage["users"] != 3000]
    evaluation = evaluate_results(stats)
    assert evaluation["overall_pass"] is False
    assert "缺少 3000 用户阶段" in evaluation["evidence_errors"]


def test_core_read_p95_over_300ms_blocks_pass():
    stats = _valid_stats()
    stats["stages"][-1]["endpoints"][0]["p95"] = 301
    evaluation = evaluate_results(stats)
    assert evaluation["core_p95_pass"] is False
    assert evaluation["overall_pass"] is False


def test_core_read_p99_over_1s_blocks_pass_even_when_p95_passes():
    stats = _valid_stats()
    stats["stages"][-1]["endpoints"][1]["p99"] = 1001
    evaluation = evaluate_results(stats)
    assert evaluation["core_p95_pass"] is True
    assert evaluation["core_p99_pass"] is False
    assert evaluation["overall_pass"] is False


def test_core_latency_without_evidence_cannot_pass():
    stats = _valid_stats()
    stats["stages"][-1]["endpoints"][2]["p99"] = None
    evaluation = evaluate_results(stats)
    assert evaluation["core_p99_pass"] is False
    assert evaluation["overall_pass"] is False


def test_missing_core_endpoint_sample_is_hard_failure():
    stats = _valid_stats()
    stats["stages"][-1]["endpoints"] = stats["stages"][-1]["endpoints"][:-1]
    evaluation = evaluate_results(stats)
    assert evaluation["samples_pass"] is False
    assert any("核心读端点无样本" in item for item in evaluation["evidence_errors"])


def test_core_error_rate_must_be_below_point_one_percent():
    stats = _valid_stats()
    stats["stages"][-1]["endpoints"][2].update(requests=1000, failures=1)  # 恰好 0.1% 也不达标
    evaluation = evaluate_results(stats)
    assert evaluation["core_error_pass"] is False
    assert evaluation["overall_pass"] is False


def test_all_scenario_error_rate_takes_worse_of_full_run_and_6000_stage():
    stats = _valid_stats()
    stats["total"].update(requests=100, failures=1)
    evaluation = evaluate_results(stats)
    assert evaluation["core_error_pass"] is True
    assert evaluation["all_error_pass"] is False

    stats = _valid_stats()
    stats["stages"][-1].update(requests=100, failures=1)  # 全程达标，但 6000 稳态 1%
    evaluation = evaluate_results(stats)
    assert evaluation["all_error_rate"] == pytest.approx(1.0)
    assert evaluation["all_error_pass"] is False
    assert evaluation["overall_pass"] is False


def test_missing_safety_evidence_is_fail_closed():
    stats = _valid_stats()
    stats["safety"] = {}
    evaluation = evaluate_results(stats)
    assert evaluation["safety_pass"] is False
    assert evaluation["overall_pass"] is False
    assert len(evaluation["safety_errors"]) == len(SAFETY_ZERO_KEYS)


def test_nonzero_safety_evidence_blocks_pass():
    stats = _valid_stats()
    stats["safety"] = _safety(event_loss=1)
    evaluation = evaluate_results(stats)
    assert evaluation["safety_pass"] is False
    assert "event_loss=1，必须为 0" in evaluation["safety_errors"]


def test_safety_evidence_loader_accepts_closed_schema(tmp_path):
    path = tmp_path / "safety.json"
    path.write_text(json.dumps({"safety": _safety()}), encoding="utf-8")
    assert load_safety_evidence(path) == _safety()
    assert load_safety_evidence(None) == {}
    with pytest.raises(ValueError, match="安全证据文件不存在"):
        load_safety_evidence(tmp_path / "absent.json")


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"safety": {**_safety(), "unknown": 0}}, "未知字段"),
        ({"safety": _safety(event_loss=-1)}, "非负数"),
        ({"safety": _safety(data_corruption=True)}, "非负数"),
        ({"safety": _safety(connection_leaks="0")}, "非负数"),
        ([0, 0], "JSON object"),
    ],
)
def test_safety_evidence_loader_rejects_invalid_payload(tmp_path, payload, message):
    path = tmp_path / "safety.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_safety_evidence(path)


def test_invalid_external_evidence_aborts_before_load(tmp_path):
    args = Namespace(safety_evidence=None, baseline=str(tmp_path / "absent.json"))
    with pytest.raises(RuntimeError, match="外部证据无效"):
        _prepare_external_evidence(args)


def test_baseline_summary_requires_existing_run_final_summary(tmp_path):
    assert load_baseline_summary(None) is None
    with pytest.raises(ValueError, match="基线 summary.json 不存在"):
        load_baseline_summary(tmp_path / "absent.json")
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps({"schema_version": 2}), encoding="utf-8")
    with pytest.raises(ValueError, match="缺 stats object"):
        load_baseline_summary(broken)


# ── 0.1 A/B 与机器可读证据 ─────────────────────────────────────────

def test_baseline_comparison_reports_deltas_and_does_not_gate_pass():
    baseline = {"generated_at": "2026-11-01T00:00:00+08:00", "stats": _valid_stats()}
    current = _valid_stats()
    current["total"]["p95"] = 250
    current["endpoints"][0]["p95"] = 260
    current["stages"][-1]["p99"] = 400
    comparison = compare_to_baseline(current, baseline)
    assert comparison["baseline_generated_at"] == "2026-11-01T00:00:00+08:00"
    assert comparison["total"]["p95"] == {"current": 250.0, "baseline": 200.0, "delta": 50.0, "ratio": 1.25}
    endpoint = next(item for item in comparison["endpoints"] if item["name"] == CORE_READ_ENDPOINTS[0])
    assert endpoint["p95"]["delta"] == 60.0
    stage = next(item for item in comparison["stages"] if item["users"] == 6000)
    assert stage["p99"]["delta"] == 100.0
    assert [item["users"] for item in comparison["stages"]] == [100, 1000, 3000, 6000]
    assert comparison["business_hashes_equal"] is None

    current["comparison"] = comparison
    assert evaluate_results(current)["overall_pass"] is True
    report = generate_final_report(current, Namespace(host="http://capacity.invalid"))
    assert "| 聚合 p95 | 200.000 | 250.000 | 50.000 |" in report


def test_business_hash_comparison_is_tristate():
    baseline = {"stats": {**_valid_stats(), "business_hashes": {"tb": "a"}}}
    same = {**_valid_stats(), "business_hashes": {"tb": "a"}}
    changed = {**_valid_stats(), "business_hashes": {"tb": "b"}}
    assert compare_to_baseline(same, baseline)["business_hashes_equal"] is True
    assert compare_to_baseline(changed, baseline)["business_hashes_equal"] is False
    assert compare_to_baseline(_valid_stats(), baseline)["business_hashes_equal"] is None
    assert compare_to_baseline(_valid_stats(), None) is None


def test_baseline_delta_handles_missing_and_zero_values():
    baseline = {"stats": {"total": {"p95": 0, "rps": None}, "endpoints": [], "stages": []}}
    current = {"total": {"p95": 10, "rps": 5}, "endpoints": _core_endpoints(), "stages": []}
    comparison = compare_to_baseline(current, baseline)
    assert comparison["total"]["p95"] == {"current": 10.0, "baseline": 0.0, "delta": 10.0, "ratio": None}
    assert comparison["total"]["rps"] == {"current": None, "baseline": None, "delta": None, "ratio": None}
    assert comparison["endpoints"] == [] and comparison["stages"] == []


def test_machine_readable_evidence_keeps_raw_files_and_seeds_next_baseline(tmp_path):
    for name in ("locust_stats.csv", "locust_stats_history.csv", "locust_failures.csv"):
        (tmp_path / name).write_text("Name\n", encoding="utf-8")
    (tmp_path / "notes.csv").write_text("x\n", encoding="utf-8")
    stats = {
        **_valid_stats(),
        "resource_samples_file": "resource_samples.json",
        "stage_stats_file": STAGE_STATS_FILE_NAME,
        "comparison": {"stale": True},
    }
    evaluation = evaluate_results(stats)
    comparison = {"total": {}, "endpoints": [], "stages": [], "business_hashes_equal": None}
    path = write_evidence_json(tmp_path, stats, evaluation, host="http://capacity.invalid",
                               comparison=comparison)
    payload = _strict_json(path.read_text(encoding="utf-8"))
    assert path.name == "summary.json"
    assert payload["schema_version"] == 2
    assert payload["host"] == "http://capacity.invalid"
    assert payload["raw_csv"] == ["locust_failures.csv", "locust_stats.csv", "locust_stats_history.csv"]
    assert payload["stage_stats"] == STAGE_STATS_FILE_NAME
    assert payload["resource_samples"] == "resource_samples.json"
    assert payload["comparison"] == comparison
    assert "comparison" not in payload["stats"]
    assert payload["evaluation"]["overall_pass"] is True
    assert not list(tmp_path.glob("*.tmp"))
    assert load_baseline_summary(path)["stats"]["total"]["requests"] == 400


def test_evidence_json_is_strict_even_when_rates_are_infinite(tmp_path):
    stats = {"total": {}, "stages": [], "endpoints": [], "safety": {}}
    evaluation = evaluate_results(stats)
    assert evaluation["all_error_rate"] == float("inf")
    path = write_evidence_json(tmp_path / "run", stats, evaluation, host="http://capacity.invalid")
    payload = _strict_json(path.read_text(encoding="utf-8"))
    assert payload["evaluation"]["all_error_rate"] is None
    assert payload["evaluation"]["overall_pass"] is False
