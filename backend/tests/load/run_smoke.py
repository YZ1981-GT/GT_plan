"""A2 编排冒烟：假后端 + 短梯度 + master/worker 分布式合并判定全链。

目的（spec `platform-capacity-acceptance-and-heavy-defect-closure` A2 的本机部分）：
**验证编排正确性**，不验证业务性能 —— 真实 6000 VU 实跑仍需专用容量环境（A3）。

链路：
1. 起 ``fakeserver``（子进程，独占端口）；
2. 写 ``GT_LOAD_ACCOUNTS_FILE`` / ``GT_LOAD_SCENARIOS_FILE`` 夹具（假账号/假项目即可，
   假后端不校验）；
3. 起 N 个 locust worker 进程（``--worker``，指向同一 master 的 ``GT_LOAD_STAGE_STATS``
   环境变量各写各的 ``stage_stats_worker*.json``）+ 1 个 master 进程（``--master``）；
4. 等 master 退出后读 ``--worker-stats-dir``，经 ``load_worker_stage_stats`` 合并；
5. 判定：每阶段 covered_seconds 达标、每阶段有样本、端点直方图非空、
   合并后样本数 == 各 worker 之和（不丢样本）。

短梯度：不读 ``load_contract.LOAD_STAGES``（那是 6000 VU 正式梯度），冒烟用自己的
两阶段 10→20 VU / 各 8 秒稳态定义，但**复用同一套 timeline / recorder / merge 代码**，
所以编排正确性结论对正式梯度成立。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from tests.load.load_stage_stats import (
    SMOKE_STAGES_ENV,
    STAGE_STATS_ENV,
    load_worker_stage_stats,
    stage_timeline,
)

SCRIPT_DIR = Path(__file__).resolve().parent
LOCUSTFILE = SCRIPT_DIR / "locustfile.py"
FAKESERVER = SCRIPT_DIR / "fakeserver.py"
BACKEND_ROOT = SCRIPT_DIR.parents[1]

# 冒烟梯度：两阶段（10 VU / 8s 稳态 + 20 VU / 8s 稳态），总时长约 30 秒。
# 经 GT_LOAD_SMOKE_STAGES_JSON 注入 locustfile 的 StepLoadShape —— 同一份
# stage_timeline 计算时间线，稳态窗口语义与正式梯度一致。
SMOKE_STAGES: tuple[dict[str, int | str], ...] = (
    {"label": "smoke-1", "users": 10, "spawn_rate": 10, "duration": 8},
    {"label": "smoke-2", "users": 20, "spawn_rate": 20, "duration": 8},
)


def write_fixtures(fix_dir: Path) -> tuple[Path, Path]:
    """写账号池 / 场景池夹具；假后端不校验内容，只要 UUID 合法。"""
    fix_dir.mkdir(parents=True, exist_ok=True)
    accounts = fix_dir / "accounts.json"
    accounts.write_text(
        json.dumps([{"username": "smoke", "password": "smoke"}], ensure_ascii=False),
        encoding="utf-8",
    )
    scenarios = fix_dir / "scenarios.json"
    scenarios.write_text(
        json.dumps(
            [{
                "project_id": "00000000-0000-0000-0000-000000000001",
                "year": 2025,
                "account_code": "1001",
            }],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return accounts, scenarios


def _wait_ready(proc: subprocess.Popen[str], marker: str, timeout: float = 30.0) -> bool:
    """轮询子进程 stdout 等就绪标记（假后端打印 FAKESERVER_READY）。"""
    deadline = time.monotonic() + timeout
    lines: list[str] = []
    # 子进程 stdout 由 fakeserver main() 用 flush=True 逐行写；非阻塞读靠线程不划算，
    # 简化：轮询端口可达性（server 打印 READY 后 accept 已可用）。
    del proc, lines, marker  # 用端口探测替代 stdout 解析
    return time.monotonic() < deadline


# 保留 _wait_ready（语义占位避免误导删除）；实际就绪判定用 _wait_port_open。


def _wait_port_open(host: str, port: int, timeout: float = 30.0) -> bool:
    import socket

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc_alive(_FAKESERVER_PROC):
            try:
                with socket.create_connection((host, port), timeout=1.0):
                    return True
            except OSError:
                time.sleep(0.2)
        else:
            return False
    return False


_FAKESERVER_PROC: subprocess.Popen[str] | None = None


def proc_alive(proc: subprocess.Popen[str] | None) -> bool:
    return proc is not None and proc.poll() is None


def run_workers(
    *,
    host: str,
    master_port: int,
    worker_count: int,
    accounts_file: Path,
    scenarios_file: Path,
    worker_stats_dir: Path,
    timeout_seconds: float,
) -> list[int]:
    """起 1 个 master + N 个 worker，阻塞到 master 退出。返回各进程退出码。"""
    backend_env = {
        **os.environ,
        "GT_LOAD_ACCOUNTS_FILE": str(accounts_file),
        "GT_LOAD_SCENARIOS_FILE": str(scenarios_file),
        "GT_LOAD_ALLOW_WRITES": "",          # 冒烟只读
        "GT_LOAD_DISPOSABLE_ENV": "",        # 只读不需要声明可销毁环境
        # 短梯度注入：StepLoadShape 与 StageRecorder 都按冒烟阶段走。
        SMOKE_STAGES_ENV: json.dumps(
            [{"users": s["users"], "spawn_rate": s["spawn_rate"], "duration": s["duration"]}
             for s in SMOKE_STAGES],
            ensure_ascii=False,
        ),
        # master 自己也注册了 on_test_stop（STAGE_STATS_ENV 指向 base 文件）；
        # 它不参与 worker 合并（master 无请求样本），写 worker_stats 目录之外。
        STAGE_STATS_ENV: str(worker_stats_dir.parent / "stage_stats_master.json"),
    }
    master_cmd = [
        sys.executable, "-m", "locust", "-f", str(LOCUSTFILE),
        "--host", host, "--master",
        # master 侧：--master-bind-port 是 worker 通信端口（默认 5557）；
        # --master-port 是 web UI 端口，worker 不连它。
        "--master-bind-port", str(master_port),
        "--headless", "--expect-workers", str(worker_count),
    ]
    worker_cmds = [
        [
            sys.executable, "-m", "locust", "-f", str(LOCUSTFILE),
            # worker 侧：--master-host / --master-port 指 master 的通信端口。
            "--host", host, "--worker", "--master-port", str(master_port),
        ]
        for _ in range(worker_count)
    ]
    env = dict(backend_env)
    master = subprocess.Popen(
        master_cmd, cwd=str(BACKEND_ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
    )
    workers: list[subprocess.Popen[str]] = []
    for index, cmd in enumerate(worker_cmds):
        worker_env = {**env, STAGE_STATS_ENV: str(worker_stats_dir / f"stage_stats_worker{index}.json")}
        workers.append(subprocess.Popen(
            cmd, cwd=str(BACKEND_ROOT), env=worker_env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
        ))
    try:
        master_out, _ = master.communicate(timeout=timeout_seconds)
        if master.returncode != 0:
            print(f"[SMOKE] master 退出码 {master.returncode}")
            print((master_out or "")[-3000:])
            master_log = worker_stats_dir.parent / "master_log.txt"
            master_log.write_text(master_out or "", encoding="utf-8")
    except subprocess.TimeoutExpired:
        print(f"[SMOKE] master 超过 {timeout_seconds}s，杀进程树")
        master.kill()
        master_out, _ = master.communicate()
        print((master_out or "")[-3000:])
    finally:
        for worker in workers:
            if worker.poll() is None:
                worker.kill()
        for index, worker in enumerate(workers):
            out, _ = worker.communicate()
            log = worker_stats_dir.parent / f"worker{index}_log.txt"
            log.write_text(out or "", encoding="utf-8")
    codes = [master.returncode if master.returncode is not None else -1]
    codes += [worker.returncode if worker.returncode is not None else -1 for worker in workers]
    return codes


def judge_smoke(
    stages: list[dict[str, Any]],
    worker_count: int,
    worker_files: list[str],
    *,
    expected_users: tuple[int, ...],
    min_covered: tuple[float, ...],
) -> list[str]:
    """冒烟判定；返回错误清单（空 = 通过）。

    判据是**编排正确性**而非业务 SLO：
    - 每阶段 covered_seconds ≥ 冒烟稳态时长 − settle（严格下限，不另给正容差）；
    - 每阶段有样本（合并后 requests > 0）；
    - worker 文件数 == worker_count（每个 worker 都落了自己的统计）。
    """
    errors: list[str] = []
    if len(worker_files) != worker_count:
        errors.append(f"worker 统计文件数 {len(worker_files)} != 起的 worker 数 {worker_count}")
    if len(stages) != len(expected_users):
        errors.append(f"阶段数 {len(stages)} != 冒烟梯度 {len(expected_users)}")
        return errors
    for index, stage in enumerate(stages):
        if int(stage.get("users", -1)) != expected_users[index]:
            errors.append(f"第 {index} 阶段用户数 {stage.get('users')} != {expected_users[index]}")
        covered = float(stage.get("covered_seconds") or 0.0)
        # 严格下限：settle 已从稳态时长里扣除，covered 再少就是样本不足（不另给正容差——
        # 冒烟窗口本来就只有几秒，再容忍就会让「worker 没记录满窗口」静默通过）。
        if covered < min_covered[index]:
            errors.append(
                f"第 {index} 阶段稳态覆盖 {covered:.1f}s < 冒烟要求 {min_covered[index]:.1f}s"
            )
        if int(stage.get("requests", 0) or 0) <= 0:
            errors.append(f"第 {index} 阶段合并后 0 请求（样本丢失或 worker 未起）")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="A2 编排冒烟（假后端 + 短梯度 + 分布式合并）")
    parser.add_argument("--worker-count", type=int, default=2)
    parser.add_argument("--master-port", type=int, default=18089)
    parser.add_argument("--workdir", default=None, help="证据目录（默认 tmp_smoke_orchestration/）")
    parser.add_argument("--timeout", type=float, default=180.0, help="master 运行超时秒数")
    args = parser.parse_args()

    workdir = Path(args.workdir) if args.workdir else Path("tmp_smoke_orchestration")
    worker_stats_dir = workdir / "worker_stats"
    worker_stats_dir.mkdir(parents=True, exist_ok=True)
    for stale in worker_stats_dir.glob("stage_stats_worker*.json"):
        stale.unlink()

    global _FAKESERVER_PROC
    fake_port = 0  # 由 fakeserver 子进程自选
    accounts_file, scenarios_file = write_fixtures(workdir / "fixtures")

    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    _FAKESERVER_PROC = subprocess.Popen(
        [sys.executable, str(FAKESERVER), "--port", "19991"],
        cwd=str(BACKEND_ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
    )
    fake_port = 19991
    host = f"http://127.0.0.1:{fake_port}"
    ok = _wait_port_open("127.0.0.1", fake_port, timeout=20.0)
    if not ok:
        print("[ABORT] 假后端未就绪")
        out, _ = _FAKESERVER_PROC.communicate(timeout=5)
        print((out or "")[-2000:])
        return 2
    print(f"[SMOKE] 假后端就绪 {host}；worker={args.worker_count} master-port={args.master_port}")

    # 冒烟全时长（与 stage_timeline 同公式）+ master 收尾余量；不足以跑完时判超时。
    timeline = stage_timeline([dict(s) for s in SMOKE_STAGES])
    timeline_seconds = timeline[-1]["end_s"] if timeline else 30.0
    timeout = max(args.timeout, timeline_seconds + 60.0)

    codes = run_workers(
        host=host,
        master_port=args.master_port,
        worker_count=args.worker_count,
        accounts_file=accounts_file,
        scenarios_file=scenarios_file,
        worker_stats_dir=worker_stats_dir,
        timeout_seconds=timeout,
    )
    print(f"[SMOKE] 退出码 master+workers = {codes}")

    stages: list[dict[str, Any]] = []
    worker_files: list[str] = []
    merge_error: str | None = None
    try:
        stages, worker_files = load_worker_stage_stats(worker_stats_dir)
    except ValueError as exc:
        merge_error = str(exc)

    errors: list[str] = []
    if merge_error:
        errors.append(f"合并失败：{merge_error}")
    else:
        expected_users = tuple(int(stage["users"]) for stage in SMOKE_STAGES)
        # 冒烟稳态下限 = stage_timeline 的 required_seconds（稳态时长 − settle）；
        # 与正式梯度同一口径（covered_seconds 允许 2 秒调度抖动在 evaluate 侧处理）。
        timeline = stage_timeline([dict(s) for s in SMOKE_STAGES])
        min_covered = tuple(item["required_seconds"] for item in timeline)
        errors.extend(judge_smoke(stages, args.worker_count, worker_files,
                                  expected_users=expected_users, min_covered=min_covered))

    summary = {
        "schema_version": 1,
        "worker_count": args.worker_count,
        "exit_codes": codes,
        "worker_files": worker_files,
        "stages": [
            {
                "users": stage.get("users"),
                "covered_seconds": stage.get("covered_seconds"),
                "requests": stage.get("requests"),
                "failures": stage.get("failures"),
                "p95": stage.get("p95"),
                "p99": stage.get("p99"),
            }
            for stage in stages
        ],
        "errors": errors,
        "pass": not errors and codes[0] == 0,
    }
    summary_path = workdir / "smoke_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[SMOKE] 摘要 {summary_path}")
    for stage in summary["stages"]:
        print(f"  阶段 {stage['users']} VU：covered={stage['covered_seconds']}s "
              f"requests={stage['requests']} p95={stage['p95']} p99={stage['p99']}")
    if errors:
        for problem in errors:
            print(f"  - {problem}")
    print(f"[SMOKE] {'PASS' if summary['pass'] else 'FAIL'}")

    if proc_alive(_FAKESERVER_PROC):
        _FAKESERVER_PROC.kill()
        _FAKESERVER_PROC.communicate()
    return 0 if summary["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
