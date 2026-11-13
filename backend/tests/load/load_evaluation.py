"""E5/E6 容量结果判定与 0.1 基线 A/B 对比。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.load.load_contract import (
    ALL_SCENARIO_ERROR_RATE_PCT,
    CORE_ERROR_RATE_PCT,
    CORE_READ_ENDPOINTS,
    CORE_READ_P95_MS,
    CORE_READ_P99_MS,
    SAFETY_ZERO_KEYS,
    STEADY_COVERAGE_TOLERANCE_SECONDS,
)
from tests.load.load_stage_stats import stage_timeline


def _rate(item: dict[str, Any]) -> float:
    requests = int(item.get("requests", 0) or 0)
    failures = int(item.get("failures", 0) or 0)
    return failures / requests * 100 if requests > 0 else float("inf")


def _latency(value: Any) -> float:
    """缺失 / None 的分位按无穷大处理：没有证据不能当 0ms 通过。"""
    try:
        return float(value) if value is not None else float("inf")
    except (TypeError, ValueError):
        return float("inf")


def evaluate_results(stats: dict[str, Any]) -> dict[str, Any]:
    """阶段完整 + 稳态覆盖 + 核心读 SLO + 分层错误率 + 六类安全零值。"""
    total = stats.get("total") or {}
    stages = stats.get("stages") or []
    by_users = {int(stage.get("users", 0)): stage for stage in stages}
    evidence_errors: list[str] = []
    if stats.get("stage_stats_error"):
        evidence_errors.append(f"稳态窗口统计不可用：{stats['stage_stats_error']}")
    # 稳态时长按合同现算，不信证据文件自报：本地改短梯度跑出的结果不能冒充 30 分钟稳态。
    for expected in stage_timeline():
        users = int(expected["users"])
        stage = by_users.get(users)
        if stage is None:
            evidence_errors.append(f"缺少 {users} 用户阶段")
            continue
        actual = int(stage.get("user_count_actual", 0) or 0)
        requests = int(stage.get("requests", 0) or 0)
        covered = float(stage.get("covered_seconds", 0) or 0)
        required = float(expected["required_seconds"])
        if actual < int(users * 0.9):
            evidence_errors.append(f"{users} 用户阶段实际并发仅 {actual}，低于 90%")
        if requests <= 0:
            evidence_errors.append(f"{users} 用户阶段请求样本为 0")
        if covered + STEADY_COVERAGE_TOLERANCE_SECONDS < required:
            evidence_errors.append(
                f"{users} 用户阶段稳态仅覆盖 {covered:.0f} 秒，要求至少 {required:.0f} 秒"
            )
    if int(total.get("requests", 0) or 0) <= 0:
        evidence_errors.append("全程聚合请求样本为 0")

    stage_6000 = by_users.get(6000) or {}
    endpoint_by_name = {
        str(item.get("name")): item
        for item in (stage_6000.get("endpoints") or [])
        if item.get("name")
    }

    core_results: list[dict[str, Any]] = []
    for name in CORE_READ_ENDPOINTS:
        item = endpoint_by_name.get(name)
        if not item or int(item.get("requests", 0) or 0) <= 0:
            evidence_errors.append(f"6000 用户阶段核心读端点无样本：{name}")
            core_results.append({
                "name": name, "requests": 0, "failures": 0,
                "p95": float("inf"), "p99": float("inf"),
                "error_rate": float("inf"),
            })
            continue
        core_results.append({
            "name": name,
            "requests": int(item.get("requests", 0) or 0),
            "failures": int(item.get("failures", 0) or 0),
            "p95": _latency(item.get("p95")),
            "p99": _latency(item.get("p99")),
            "error_rate": _rate(item),
        })

    core_p95_pass = bool(core_results) and all(
        item["p95"] <= CORE_READ_P95_MS for item in core_results
    )
    core_p99_pass = bool(core_results) and all(
        item["p99"] <= CORE_READ_P99_MS for item in core_results
    )
    core_error_pass = bool(core_results) and all(
        item["error_rate"] < CORE_ERROR_RATE_PCT for item in core_results
    )
    full_error_rate = _rate(total)
    stage_error_rate = _rate(stage_6000)
    all_error_rate = max(full_error_rate, stage_error_rate)
    all_error_pass = all_error_rate < ALL_SCENARIO_ERROR_RATE_PCT

    safety = stats.get("safety") or {}
    missing_safety = [key for key in SAFETY_ZERO_KEYS if key not in safety]
    nonzero_safety = {
        key: safety.get(key) for key in SAFETY_ZERO_KEYS
        if key in safety and safety.get(key) != 0
    }
    safety_errors = [f"缺少安全证据字段：{key}" for key in missing_safety]
    safety_errors.extend(
        f"{key}={value}，必须为 0" for key, value in nonzero_safety.items()
    )
    safety_pass = not safety_errors
    samples_pass = not evidence_errors
    overall_pass = all((
        samples_pass, core_p95_pass, core_p99_pass,
        core_error_pass, all_error_pass, safety_pass,
    ))

    return {
        "samples_pass": samples_pass,
        "evidence_errors": evidence_errors,
        "stage_6000": stage_6000,
        "p95_6000": stage_6000.get("p95"),
        "p99_6000": stage_6000.get("p99"),
        "error_rate_6000": stage_error_rate,
        "core_results": core_results,
        "core_p95_pass": core_p95_pass,
        "core_p99_pass": core_p99_pass,
        "core_error_pass": core_error_pass,
        "all_error_rate": all_error_rate,
        "all_error_pass": all_error_pass,
        "safety": safety,
        "safety_errors": safety_errors,
        "safety_pass": safety_pass,
        # 兼容旧调用方字段，语义改为新 E6 门。
        "p95_pass": core_p95_pass,
        "p99_pass": core_p99_pass,
        "error_pass": core_error_pass and all_error_pass,
        "overall_pass": overall_pass,
    }


def load_safety_evidence(path: str | Path | None) -> dict[str, Any]:
    """加载六类零值证据；不提供时返回空，让 evaluate_results fail-closed。"""
    if not path:
        return {}
    source = Path(path)
    if not source.is_file():
        raise ValueError(f"安全证据文件不存在：{source}")
    payload = json.loads(source.read_text(encoding="utf-8"))
    safety = payload.get("safety", payload) if isinstance(payload, dict) else None
    if not isinstance(safety, dict):
        raise ValueError("安全证据必须是 JSON object 或包含 safety object")
    unknown = sorted(set(safety) - set(SAFETY_ZERO_KEYS))
    if unknown:
        raise ValueError(f"安全证据包含未知字段：{unknown}")
    for key, value in safety.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ValueError(f"安全证据 {key} 必须是非负数，实际 {value!r}")
    return safety


def load_baseline_summary(path: str | Path | None) -> dict[str, Any] | None:
    """读取上一轮 summary.json；提供路径后缺失/损坏必须报错，禁止静默无对比。"""
    if not path:
        return None
    source = Path(path)
    if not source.is_file():
        raise ValueError(f"基线 summary.json 不存在：{source}")
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("stats"), dict):
        raise ValueError("基线文件不是 run_final summary.json（缺 stats object）")
    return payload

def _delta(current: Any, baseline: Any) -> dict[str, float | None]:
    try:
        current_f = float(current)
        baseline_f = float(baseline)
    except (TypeError, ValueError):
        return {"current": None, "baseline": None, "delta": None, "ratio": None}
    ratio = current_f / baseline_f if baseline_f != 0 else None
    return {
        "current": current_f,
        "baseline": baseline_f,
        "delta": current_f - baseline_f,
        "ratio": ratio,
    }


def compare_to_baseline(
    current_stats: dict[str, Any],
    baseline_summary: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """同输入 A/B：聚合、同名端点、同并发阶段逐指标比较，不参与 PASS 门。"""
    if baseline_summary is None:
        return None
    baseline_stats = baseline_summary["stats"]
    comparison: dict[str, Any] = {
        "baseline_generated_at": baseline_summary.get("generated_at"),
        "total": {},
        "endpoints": [],
        "stages": [],
    }
    for metric in ("requests", "failures", "median", "p95", "p99", "avg", "rps"):
        comparison["total"][metric] = _delta(
            current_stats.get("total", {}).get(metric),
            baseline_stats.get("total", {}).get(metric),
        )

    baseline_eps = {
        str(item.get("name")): item for item in baseline_stats.get("endpoints", [])
    }
    for current in current_stats.get("endpoints", []):
        name = str(current.get("name") or "")
        previous = baseline_eps.get(name)
        if not name or previous is None:
            continue
        comparison["endpoints"].append({
            "name": name,
            **{metric: _delta(current.get(metric), previous.get(metric))
               for metric in ("p95", "p99", "rps", "failures")},
        })

    baseline_stages = {
        int(item.get("users", 0)): item for item in baseline_stats.get("stages", [])
    }
    for current in current_stats.get("stages", []):
        users = int(current.get("users", 0))
        previous = baseline_stages.get(users)
        if previous is None:
            continue
        comparison["stages"].append({
            "users": users,
            **{metric: _delta(current.get(metric), previous.get(metric))
               for metric in ("p95", "p99", "rps", "failures")},
        })

    current_hashes = current_stats.get("business_hashes")
    baseline_hashes = baseline_stats.get("business_hashes")
    comparison["business_hashes_equal"] = (
        current_hashes == baseline_hashes
        if current_hashes is not None and baseline_hashes is not None
        else None
    )
    return comparison
