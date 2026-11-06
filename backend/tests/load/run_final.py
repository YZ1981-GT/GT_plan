"""最终容量验收 runner：E5/E6 正式梯度、SLO、安全证据和 0.1 A/B 单一入口。"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from tests.load.capacity_resource_sampler import ResourceSampler
from tests.load.load_contract import (
    CORE_ERROR_RATE_PCT,
    CORE_READ_P95_MS,
    CORE_READ_P99_MS,
    ESTIMATED_TOTAL_SECONDS,
    LOAD_STAGES,
)
from tests.load.load_evaluation import (
    compare_to_baseline,
    evaluate_results,
    load_baseline_summary,
    load_safety_evidence,
)
from tests.load.load_report import generate_final_report
from tests.load.load_stage_stats import STAGE_STATS_ENV, STAGE_STATS_FILE_NAME, load_stage_stats

SCRIPT_DIR = Path(__file__).resolve().parent
LOCUSTFILE = SCRIPT_DIR / "locustfile.py"
DEFAULT_HOST = "http://127.0.0.1:9980"
DEFAULT_OUTPUT = SCRIPT_DIR / "final_report.md"
REPO_ROOT = SCRIPT_DIR.parents[2]
DEFAULT_EVIDENCE_ROOT = REPO_ROOT / "tmp_capacity_evidence"

# 向后兼容既有 import；正式真源在 load_contract.py。
STAGES = [dict(stage) for stage in LOAD_STAGES]
TARGET_P95_MS = CORE_READ_P95_MS
TARGET_P99_MS = CORE_READ_P99_MS
TARGET_ERROR_RATE = CORE_ERROR_RATE_PCT


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行 6000 VU 正式容量验收")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--baseline", default=None, help="上一轮 run_final summary.json")
    parser.add_argument("--safety-evidence", default=None, help="E6 六类零值证据 JSON")
    parser.add_argument("--evidence-dir", default=None, help="CSV/JSON/资源样本目录")
    parser.add_argument("--resource-sample-interval", type=float, default=15.0)
    return parser.parse_args()

def run_locust_full_shape(host: str, evidence_dir: Path, *, sample_interval: float = 15.0) -> dict[str, Any]:
    """运行单个 Locust 进程并周期采集资源；E4 会把它换成 master/worker 编排。"""
    evidence_dir.mkdir(parents=True, exist_ok=True)
    csv_prefix = evidence_dir / "locust"
    resource_path = evidence_dir / "resource_samples.json"
    stage_stats_path = evidence_dir / STAGE_STATS_FILE_NAME
    child_env = {
        **os.environ,
        STAGE_STATS_ENV: str(stage_stats_path),
        "PYTHONIOENCODING": "utf-8",
    }
    command = [
        sys.executable, "-m", "locust", "-f", str(LOCUSTFILE),
        "--host", host, "--headless", "--csv", str(csv_prefix), "--csv-full-history",
    ]
    timeout_seconds = ESTIMATED_TOTAL_SECONDS + 120
    print(f"[INFO] 梯度：{' → '.join(str(s['users']) for s in STAGES)} VU")
    print(f"[INFO] 6000 VU 稳态：{STAGES[-1]['duration']} 秒；总时长约 {ESTIMATED_TOTAL_SECONDS / 60:.1f} 分钟")
    print(f"[INFO] 命令：{' '.join(command)}")

    sampler = ResourceSampler(host, resource_path, interval_s=sample_interval)
    sampler.start()
    return_code: int | None = None
    timed_out = False
    try:
        # Windows 管道默认按 gbk 解码，中文日志会让 stdout 静默变 None；子进程与父进程统一 UTF-8。
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=child_env,
            timeout=timeout_seconds,
            cwd=str(SCRIPT_DIR.parent.parent),
        )
        return_code = result.returncode
        if result.stdout:
            print(result.stdout[-3000:])
        if result.stderr:
            print(result.stderr[-2000:])
    except subprocess.TimeoutExpired:
        timed_out = True
        print(f"[WARN] Locust 超过 runner 上限 {timeout_seconds}s；保留已有 CSV 并判失败")
    except FileNotFoundError as exc:
        raise RuntimeError("未找到 Locust，请先安装项目依赖") from exc
    finally:
        sampler.stop()

    stats = parse_csv_results(csv_prefix, stage_stats_path)
    stats.update({
        "evidence_dir": str(evidence_dir),
        "resource_samples_file": resource_path.name,
        "locust_return_code": return_code,
        "locust_timed_out": timed_out,
    })
    return stats


def _number(row: dict[str, str], *names: str, default: float = 0.0) -> float:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            try:
                return float(value)
            except ValueError:
                continue
    return default

def _parse_stats_row(row: dict[str, str]) -> dict[str, Any]:
    return {
        "name": row.get("Name", ""),
        "type": row.get("Type", ""),
        "requests": int(_number(row, "Request Count", "Total Request Count")),
        "failures": int(_number(row, "Failure Count", "Total Failure Count")),
        "median": _number(row, "Median Response Time", "50%"),
        "p95": _number(row, "95%"),
        "p99": _number(row, "99%"),
        "avg": _number(row, "Average Response Time"),
        "max": _number(row, "Max Response Time"),
        "rps": _number(row, "Requests/s"),
    }


def parse_csv_results(csv_prefix: Path, stage_stats_path: Path | None = None) -> dict[str, Any]:
    """全程聚合与端点取 ``_stats.csv``；阶段只取 recorder 的稳态窗口直方图。

    ``_stats_history.csv`` 只作原始曲线归档：其分位列是 10 秒滚动窗口、计数列是全程累计，
    任何一行都代表不了某个阶段的稳态分布，故不参与判定。
    """
    results: dict[str, Any] = {
        "total": {}, "endpoints": [], "stages": [],
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    stats_file = Path(f"{csv_prefix}_stats.csv")
    if stats_file.is_file():
        with stats_file.open("r", encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                item = _parse_stats_row(row)
                if item["name"] == "Aggregated":
                    results["total"] = item
                else:
                    results["endpoints"].append(item)
    stage_path = stage_stats_path or csv_prefix.parent / STAGE_STATS_FILE_NAME
    try:
        results["stages"] = load_stage_stats(stage_path)
        results["stage_stats_file"] = stage_path.name
    except ValueError as exc:
        results["stage_stats_error"] = str(exc)
    return results


def _json_safe(value: Any) -> Any:
    """inf/nan 写成 null：证据文件必须是严格 JSON（jq / 其他语言解析器不认 Infinity）。"""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def write_evidence_json(
    evidence_dir: Path,
    stats: dict[str, Any],
    evaluation: dict[str, Any],
    *,
    host: str,
    comparison: dict[str, Any] | None = None,
) -> Path:
    """写机器可读证据；不写 token/密码，只记可复算统计、原始文件清单和判定。"""
    evidence_dir.mkdir(parents=True, exist_ok=True)
    path = evidence_dir / "summary.json"
    payload = _json_safe({
        "schema_version": 2,
        "host": host,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        # comparison 只在顶层出现一次；summary 被下一轮当 --baseline 时不嵌套上一轮的对比。
        "stats": {key: value for key, value in stats.items() if key != "comparison"},
        "evaluation": evaluation,
        "comparison": comparison,
        "raw_csv": sorted(item.name for item in evidence_dir.glob("locust_*.csv")),
        "stage_stats": stats.get("stage_stats_file"),
        "resource_samples": stats.get("resource_samples_file"),
    })
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def _prepare_external_evidence(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any] | None]:
    try:
        safety = load_safety_evidence(args.safety_evidence)
        baseline = load_baseline_summary(args.baseline)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"外部证据无效：{exc}") from exc
    return safety, baseline


def main() -> int:
    args = parse_args()
    print("=" * 70)
    print("审计平台正式容量验收")
    print(f"目标：核心读 P95 ≤ {TARGET_P95_MS:.0f}ms / P99 ≤ {TARGET_P99_MS:.0f}ms / 核心错误率 < {TARGET_ERROR_RATE}%")
    print(f"梯度：{' → '.join(str(s['users']) for s in STAGES)}；6000 VU 稳态 {STAGES[-1]['duration']} 秒")
    print("=" * 70)

    from tests.load.load_guard import LoadGuardError, require_safe_load_target
    try:
        decision = require_safe_load_target()
        safety, baseline = _prepare_external_evidence(args)
    except (LoadGuardError, RuntimeError) as exc:
        print(f"[ABORT] {exc}")
        return 2
    print(f"[GUARD] {decision.reason}")
    if not LOCUSTFILE.is_file():
        print(f"[ABORT] 未找到压测脚本：{LOCUSTFILE}")
        return 2

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    evidence_dir = (
        Path(args.evidence_dir)
        if args.evidence_dir
        else DEFAULT_EVIDENCE_ROOT / f"run_{stamp}"
    )
    stats = run_locust_full_shape(
        args.host,
        evidence_dir,
        sample_interval=args.resource_sample_interval,
    )
    stats["safety"] = safety
    comparison = compare_to_baseline(stats, baseline)
    stats["comparison"] = comparison
    evaluation = evaluate_results(stats)
    summary = write_evidence_json(
        evidence_dir,
        stats,
        evaluation,
        host=args.host,
        comparison=comparison,
    )
    report = generate_final_report(stats, args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(f"[EVIDENCE] {summary}")
    print(f"[REPORT] {output}")
    print(f"[RESULT] {'PASS' if evaluation['overall_pass'] else 'FAIL'}")
    for problem in [*evaluation["evidence_errors"], *evaluation["safety_errors"]]:
        print(f"  - {problem}")
    return 0 if evaluation["overall_pass"] else 2


if __name__ == "__main__":
    sys.exit(main())
