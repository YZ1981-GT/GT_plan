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
from tests.load.load_stage_stats import (
    STAGE_STATS_ENV,
    STAGE_STATS_FILE_NAME,
    WORKER_STATS_GLOB,
    load_stage_stats,
    load_worker_stage_stats,
)

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
    parser.add_argument(
        "--worker-stats-dir",
        default=None,
        help="分布式运行：master 侧汇总目录，内含各 worker 的 stage_stats_worker*.json（E4）",
    )
    parser.add_argument("--resource-sample-interval", type=float, default=15.0)
    parser.add_argument(
        "--skip-safety-probes",
        action="store_true",
        help="跳过 A1 探针自动采集（默认在压测前后各跑一次 run_all_probes 喂安全证据）",
    )
    parser.add_argument("--probe-project", default=None, help="探针项目 id（安全计数生产者需要；缺省时写探针类探针 fail-closed）")
    parser.add_argument("--probe-pg-dsn", default=None, help="探针用 PG DSN（连接池对账；缺省从 DATABASE_URL 推导）")
    return parser.parse_args()

def run_locust_full_shape(
    host: str,
    evidence_dir: Path,
    *,
    sample_interval: float = 15.0,
    worker_stats_dir: Path | None = None,
) -> dict[str, Any]:
    """运行单个 Locust 进程并周期采集资源。

    分布式（master/worker 编排）时由外部把各 worker 的 ``stage_stats_worker*.json``
    收进 ``worker_stats_dir``；本函数只按该目录做逐桶相加，不再自己起 worker。
    """
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

    stats = parse_csv_results(csv_prefix, stage_stats_path, worker_stats_dir=worker_stats_dir)
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


def parse_csv_results(
    csv_prefix: Path,
    stage_stats_path: Path | None = None,
    *,
    worker_stats_dir: Path | None = None,
) -> dict[str, Any]:
    """全程聚合与端点取 ``_stats.csv``；阶段只取 recorder 的稳态窗口直方图。

    ``_stats_history.csv`` 只作原始曲线归档：其分位列是 10 秒滚动窗口、计数列是全程累计，
    任何一行都代表不了某个阶段的稳态分布，故不参与判定。

    ``worker_stats_dir``：分布式运行时传 master 侧汇总目录，里面每个 Locust worker
    各写一份 ``stage_stats_worker*.json``。此时阶段统计取**全部 worker 逐桶相加**后
    的结果；缺失或损坏一律记进 ``stage_stats_error``（fail-closed，绝不退回单 worker
    口径 —— 那会让样本量只有 1/N 而判定看起来更好）。
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

    if worker_stats_dir is not None:
        try:
            stages, worker_files = load_worker_stage_stats(Path(worker_stats_dir))
            results["stages"] = stages
            results["stage_stats_file"] = WORKER_STATS_GLOB
            results["worker_stats_files"] = worker_files
            results["worker_count"] = len(worker_files)
        except ValueError as exc:
            results["stage_stats_error"] = str(exc)
        return results

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


def _probe_pg_dsn(args: argparse.Namespace) -> str | None:
    """探针连接池对账用 DSN；--probe-pg-dsn 优先，否则从 DATABASE_URL 推导。"""
    if args.probe_pg_dsn:
        return args.probe_pg_dsn
    url = os.environ.get("DATABASE_URL", "")
    if "postgresql" not in url:
        return None
    # asyncpg:// → psycopg 需要的 postgres://（其余部分兼容）
    dsn = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    if dsn.startswith("postgresql+"):
        dsn = dsn.split("+", 1)[0].replace("postgresql", "postgresql", 1) and dsn.split("://", 1)[0].split("+")[0] + "://" + dsn.split("://", 1)[1]
    return dsn


def _probe_env_flags(args: argparse.Namespace) -> tuple[bool, str | None, str | None]:
    """从环境推导探针三要素：disposable、低权账号密码、探针项目 id。"""
    disposable = (os.environ.get("GT_LOAD_DISPOSABLE_ENV") or "").strip() == "YES"
    low_user = (os.environ.get("GT_LOAD_PROBE_LOW_USER") or "").strip() or None
    low_password = (os.environ.get("GT_LOAD_PROBE_LOW_PASSWORD") or "").strip() or None
    return disposable, low_user, low_password


def _admin_token_for_probe(host: str) -> str | None:
    """压测发起方需要管理员 token 供探针读端点使用；从账号池第一个账号登录获取。"""
    from tests.load.load_config import load_config

    try:
        config = load_config()
    except ValueError as exc:
        print(f"[PROBE] 账号池不可用，探针将 fail-closed：{exc}")
        return None
    if not config.accounts:
        return None
    account = config.accounts[0]
    import httpx

    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(
                f"{host.rstrip('/')}/api/auth/login",
                json={"username": account.username, "password": account.password},
            )
    except httpx.HTTPError as exc:
        print(f"[PROBE] 探针登录失败（fail-closed）：{exc}")
        return None
    if response.status_code != 200:
        print(f"[PROBE] 探针登录 HTTP {response.status_code}（fail-closed）")
        return None
    body = response.json()
    data = body.get("data") if isinstance(body, dict) else None
    token = (data or {}).get("access_token") if isinstance(data, dict) else None
    return str(token) if token else None


def _low_privilege_token_for_probe(host: str, username: str | None, password: str | None) -> str | None:
    """低权账号登录（越权回放探针用）；未配置返回 None（探针自己 fail-closed）。"""
    if not username or not password:
        return None
    import httpx

    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(
                f"{host.rstrip('/')}/api/auth/login",
                json={"username": username, "password": password},
            )
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    body = response.json()
    data = body.get("data") if isinstance(body, dict) else None
    token = (data or {}).get("access_token") if isinstance(data, dict) else None
    return str(token) if token else None


def run_probe_evidence(
    *,
    phase: str,
    host: str,
    evidence_dir: Path,
    args: argparse.Namespace,
    connection_timeouts: int | None = None,
    skip_write_probes: bool = False,
) -> dict[str, Any]:
    """A1 接线：调 ``safety_probes.run_all_probes`` 生成六类安全计数证据。

    - before/after 两个时点各调一次（探针的连接池对账需要压测前后采样对）；
      before 在 Locust 启动前、after 在压测结束后；
    - 结果写 ``evidence_dir/probe_evidence.json``，并把两个时点的
      ``safety`` 合并进 stats（after 时点为准，before 采样明细进 probe_meta）；
    - 探针 runner 的 ``errors``（环境前提缺失/探针执行失败）原样落
      ``probe_meta.errors``，由 evaluate/校验层 fail-closed——本函数不吞、
      也不伪造 0。
    """
    from tests.load.safety_probes import run_all_probes

    disposable, low_user, low_password = _probe_env_flags(args)
    admin_token = _admin_token_for_probe(host)
    low_token = _low_privilege_token_for_probe(host, low_user, low_password) if low_user else None
    payload = run_all_probes(
        phase=phase,
        base_url=host,
        admin_token=admin_token or "",
        low_privilege_token=low_token,
        probe_project_id=args.probe_project,
        disposable_env=disposable,
        pg_dsn=_probe_pg_dsn(args),
        connection_timeouts=connection_timeouts,
        skip_write_probes=skip_write_probes,
    )
    evidence_dir.mkdir(parents=True, exist_ok=True)
    path = evidence_dir / f"probe_evidence_{phase}.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    return payload


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

    # A1：压测前时点探针（连接池 before 采样 + 环境自检；读探针不在此时点跑）。
    if not args.skip_safety_probes:
        try:
            before_payload = run_probe_evidence(
                phase="before", host=args.host, evidence_dir=evidence_dir, args=args,
            )
            print(f"[PROBE] before 时点证据已写 {evidence_dir / 'probe_evidence_before.json'}")
        except Exception as exc:  # noqa: BLE001 - 探针失败不挡压测，after 时点会 fail-closed
            before_payload = None
            print(f"[PROBE] before 时点执行失败（不挡压测）：{exc}")

    stats = run_locust_full_shape(
        args.host,
        evidence_dir,
        sample_interval=args.resource_sample_interval,
        worker_stats_dir=Path(args.worker_stats_dir) if args.worker_stats_dir else None,
    )
    # A1：压测后时点探针（全量六类）；connection_timeouts 由 Locust 统计喂入，
    # 拿不到就传 None（探针自己 fail-closed，不伪造 0）。
    if not args.skip_safety_probes:
        try:
            after_payload = run_probe_evidence(
                phase="after", host=args.host, evidence_dir=evidence_dir, args=args,
                connection_timeouts=None,
                skip_write_probes=bool(args.worker_stats_dir),
            )
            stats["safety"] = after_payload.get("safety") or {}
            stats["probe_meta"] = {
                "before": (before_payload or {}).get("probe_meta"),
                "after": after_payload.get("probe_meta"),
            }
            probe_errors = list(after_payload.get("probe_meta", {}).get("errors") or [])
            if probe_errors:
                stats["probe_errors"] = probe_errors
                print(f"[PROBE] {len(probe_errors)} 条探针错误（fail-closed 进判定）")
                for message in probe_errors:
                    print(f"  - {message}")
            else:
                print(f"[PROBE] after 时点证据已写 {evidence_dir / 'probe_evidence_after.json'}")
        except Exception as exc:  # noqa: BLE001 - 同上：探针异常落 errors 不伪造证据
            stats["probe_errors"] = [f"after 探针执行失败：{exc}"]
            print(f"[PROBE] after 时点执行失败（fail-closed）：{exc}")
    else:
        stats["probe_meta"] = {"skipped": True}

    stats["safety"] = safety if safety else stats.get("safety", {})
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
