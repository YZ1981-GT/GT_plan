"""PgBouncer transaction ???????2% ? 25% ? 100% ???????

spec: `platform-capacity-acceptance-and-heavy-defect-closure` A4????? `_archive/188`
E1 ???????????????????

## ??????

??????
1. ?????PgBouncer ?? 9 ? + ???? 14 ?????????? PASS??
2. ? `DB_USE_PGBOUNCER` ???????2% / 25% / 100% ? `GT_PGBOUNCER_PCT`
   ?????????????????????????????
3. ??????? 300 ????? pool wait / hold / timeout?event-loop lag?
   ????/api/health + /metrics??
4. ??????????? ?????? DB_USE_PGBOUNCER?? ?
   `rollout_incident.json` ? exit 2?

## ????

?? = ? `DB_USE_PGBOUNCER` ?????????????????????
`rollout_state.json` ?????????????????????????????
E1 ???????????????

## ??

    python backend/scripts/ops/pgbouncer_gradual_rollout.py --check   # ??????
    python backend/scripts/ops/pgbouncer_gradual_rollout.py --run     # ?????
    python backend/scripts/ops/pgbouncer_gradual_rollout.py --rollback  # ????
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

#: ????????? ? ???????
ROLLOUT_STAGES: tuple[tuple[int, int], ...] = ((2, 300), (25, 600), (100, 900))

#: ?????????????????????
GATE_THRESHOLDS: dict[str, float] = {
    "pool_wait_p95_ms": 50.0,       # checkout ?? p95
    "pool_timeout_rate_pct": 0.1,   # checkout ????
    "error_rate_pct": 1.0,          # /api/health ???
    "event_loop_lag_p99_ms": 200.0, # event loop lag p99
}

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND = _REPO_ROOT / "backend"
_STATE_FILE = _REPO_ROOT / "tmp_capacity_evidence" / "rollout_state.json"
_INCIDENT_FILE = _REPO_ROOT / "tmp_capacity_evidence" / "rollout_incident.json"

#: ????????????? PASS?pytest ???????????????
PRECONDITION_TESTS: tuple[str, ...] = (
    "tests/test_pgbouncer_transaction_contract_pg.py",
    "tests/test_connection_budget.py",
)


@dataclass
class StageObservation:
    stage_pct: int
    window_seconds: int
    metrics: dict[str, float] = field(default_factory=dict)
    gate_breaches: list[str] = field(default_factory=list)
    started_at: str = ""
    ended_at: str = ""


def run_preconditions() -> tuple[bool, str]:
    """??????????????????"""
    env = {**dict(__import__("os").environ), "PYTHONIOENCODING": "utf-8"}
    # ?? pytest??? pytest ?????????????????? no tests ran??
    for var in ("PYTEST_CURRENT_TEST", "PYTEST_VERSION", "PYTEST_DEBUG_TEMPROOT"):
        env.pop(var, None)
    for test_path in PRECONDITION_TESTS:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", test_path, "-q", "--tb=no", "-p", "no:playwright"],
            capture_output=True, env=env, timeout=600, cwd=str(_BACKEND),
        )
        if proc.returncode != 0:
            tail = (proc.stdout or b"").decode("utf-8", errors="replace")[-400:]
            return False, f"?????? {test_path}: {tail}"
    return True, "????? PASS"


def sample_metrics(base_url: str, token: str | None) -> dict[str, float]:
    """??????????????? -1??????????? 0???"""
    metrics = {key: -1.0 for key in GATE_THRESHOLDS}
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        with httpx.Client(timeout=10.0) as client:
            health = client.get(f"{base_url.rstrip('/')}/api/health", headers=headers)
            if health.status_code == 200:
                body = health.json().get("data", {})
                pool = body.get("pool") or {}
                metrics["pool_wait_p95_ms"] = float(pool.get("wait_p95_ms", -1))
                timeout_rate = pool.get("timeout_rate_pct")
                metrics["pool_timeout_rate_pct"] = float(timeout_rate) if timeout_rate is not None else -1.0
                lag = body.get("event_loop") or {}
                lag_p99 = lag.get("lag_p99_ms")
                metrics["event_loop_lag_p99_ms"] = float(lag_p99) if lag_p99 is not None else -1.0
            metrics["error_rate_pct"] = 0.0 if health.status_code == 200 else 100.0
    except httpx.HTTPError:
        metrics["error_rate_pct"] = 100.0
    return metrics


def check_gate(metrics: dict[str, float]) -> list[str]:
    """???????????? = ???????"""
    breaches: list[str] = []
    for key, threshold in GATE_THRESHOLDS.items():
        value = metrics.get(key, -1.0)
        # -1 = ????fail-closed???????? ? 0??????
        if value < 0 or value > threshold:
            breaches.append(f"{key}={value} > {threshold}")
    return breaches


def write_state(payload: dict[str, Any]) -> Path:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return _STATE_FILE


def write_incident(incident: dict[str, Any]) -> Path:
    _INCIDENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    _INCIDENT_FILE.write_text(json.dumps(incident, ensure_ascii=False, indent=2), encoding="utf-8")
    return _INCIDENT_FILE


def load_state() -> dict[str, Any] | None:
    if not _STATE_FILE.is_file():
        return None
    return json.loads(_STATE_FILE.read_text(encoding="utf-8"))


def run_rollout(base_url: str, token: str | None, *, window_override: int | None = None) -> int:
    """???????????? 0 = ???2 = ?????"""
    print("=" * 70)
    print("PgBouncer transaction ?????2% ? 25% ? 100%")
    print("=" * 70)

    ok, message = run_preconditions()
    if not ok:
        print(f"[ABORT] {message}")
        write_state({"status": "aborted_precondition", "reason": message,
                     "at": datetime.now(timezone.utc).isoformat()})
        return 2
    print(f"[PRECONDITION] {message}")

    completed: list[StageObservation] = []
    for stage_pct, window in ROLLOUT_STAGES:
        actual_window = window_override or window
        started = datetime.now(timezone.utc).isoformat()
        print(f"\n[STAGE {stage_pct}%] ?? {actual_window}s ...")
        # ???? DB_USE_PGBOUNCER ???????????????????
        # ??????????
        write_state({
            "status": "stage_active",
            "stage_pct": stage_pct,
            "window_seconds": actual_window,
            "instruction": "???? DB_USE_PGBOUNCER ?? transaction ????????",
            "started_at": started,
        })
        observation = StageObservation(stage_pct=stage_pct, window_seconds=actual_window, started_at=started)
        samples = 0
        deadline = time.monotonic() + actual_window
        while time.monotonic() < deadline:
            metrics = sample_metrics(base_url, token)
            for key, value in metrics.items():
                if value >= 0:
                    # ?????????p95/lag ? max????? max?
                    observation.metrics[key] = max(observation.metrics.get(key, -1.0), value)
            samples += 1
            # ???????????
            breaches = check_gate(observation.metrics)
            if breaches:
                observation.gate_breaches = breaches
                observation.ended_at = datetime.now(timezone.utc).isoformat()
                print(f"[GATE BREACH] {'; '.join(breaches)}")
                break
            time.sleep(min(10.0, max(1.0, actual_window / 30)))
        if samples == 0:
            observation.gate_breaches.append("no samples collected (backend unreachable)")
        if observation.gate_breaches:
            incident = {
                "status": "rolled_back",
                "failed_stage_pct": stage_pct,
                "breaches": observation.gate_breaches,
                "metrics": observation.metrics,
                "completed_stages": [obs.stage_pct for obs in completed],
                "rollback_instruction": "?? DB_USE_PGBOUNCER ??????? --rollback ??",
                "at": datetime.now(timezone.utc).isoformat(),
            }
            write_incident(incident)
            write_state({"status": "rolled_back", "failed_stage_pct": stage_pct,
                         "at": datetime.now(timezone.utc).isoformat()})
            print(f"[INCIDENT] {incident['rollback_instruction']}")
            return 2
        observation.ended_at = datetime.now(timezone.utc).isoformat()
        completed.append(observation)
        print(f"[STAGE {stage_pct}% PASS] metrics={observation.metrics}")

    write_state({
        "status": "all_stages_passed",
        "completed": [obs.stage_pct for obs in completed],
        "at": datetime.now(timezone.utc).isoformat(),
    })
    print("\n[RESULT] ??????????? 100% transaction ??")
    return 0


def rollback() -> int:
    """???????????????????"""
    state = load_state()
    write_state({
        "status": "manually_rolled_back",
        "previous_status": (state or {}).get("status"),
        "instruction": "????? DB_USE_PGBOUNCER ????????",
        "at": datetime.now(timezone.utc).isoformat(),
    })
    print(f"[ROLLBACK] ????? {_STATE_FILE}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PgBouncer transaction ????")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="??????")
    group.add_argument("--run", action="store_true", help="?????")
    group.add_argument("--rollback", action="store_true", help="??????")
    parser.add_argument("--host", default="http://127.0.0.1:9980")
    parser.add_argument("--token", default=None)
    parser.add_argument("--window-override", type=int, default=None,
                        help="??????????????")
    args = parser.parse_args(argv)

    if args.check:
        ok, message = run_preconditions()
        print(f"[{'PASS' if ok else 'FAIL'}] {message}")
        return 0 if ok else 2
    if args.rollback:
        return rollback()
    return run_rollout(args.host, args.token, window_override=args.window_override)


if __name__ == "__main__":
    raise SystemExit(main())
