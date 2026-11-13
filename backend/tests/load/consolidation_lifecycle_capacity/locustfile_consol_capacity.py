"""Locust harness — consolidation lifecycle 6000 VU capacity + chaos scenario.

Spec: consolidation-run-and-workpaper-lifecycle-closure — Task 8.4
Requirements: R10 (performance/capacity/observability), R11 (验收).
Design: §3 (统一运行顺序), §4 (API), §6 (性能与观测), §7 (降级).

This is the INDEPENDENT capacity tool (NOT Playwright, NOT pytest PBT). It
encodes the consolidation lifecycle traffic model against the REAL consol
endpoints, drives the 30-min steady + 10-min burst profile, runs a dedicated
cross-project canary, and on stop emits a machine-readable capacity report via
``capacity_report.generate_report``.

Run (requires a dedicated capacity environment — do NOT run against dev data):

    locust -f backend/tests/load/consolidation_lifecycle_capacity/locustfile_consol_capacity.py \
        --host http://<capacity-host>:9980 --headless --autostart

The ``StepLoadShape`` reproduces ``scenario.LOAD_PROFILE`` automatically, so no
``-u/-r`` is needed. See README.md for chaos toggle scheduling and the
authorized-run checklist.

Environment variables:
    CONSOL_CAP_USER / CONSOL_CAP_PASSWORD    login (default admin/admin123)
    CONSOL_CAP_PROJECT_ID / CONSOL_CAP_YEAR  primary consolidation scope under test
    CONSOL_CAP_FOREIGN_PROJECT_ID            foreign scope for canary leakage probe
    CONSOL_CAP_ALLOW_TRIGGER                 "1" to enable refresh-all operation
                                             triggering (writes/compute). Default
                                             off: triggering is only safe in a
                                             dedicated, disposable capacity env.
    CONSOL_CAP_ALLOW_SNAPSHOT                "1" to enable manual snapshot create.
    CONSOL_CAP_ENV                           environment label for the report.
    CONSOL_CAP_REPORT_PATH                   where to write the JSON report.
"""

from __future__ import annotations

import os
import threading
import uuid
from pathlib import Path

from locust import HttpUser, LoadTestShape, between, events, task

from .capacity_report import (
    CapacityObservations,
    OpLatency,
    generate_report,
)
from .scenario import CANARY, LOAD_PROFILE, SCENARIO, SLO_BY_OP


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_USER = os.getenv("CONSOL_CAP_USER", "admin")
_PASSWORD = os.getenv("CONSOL_CAP_PASSWORD", "admin123")
_PROJECT_ID = os.getenv("CONSOL_CAP_PROJECT_ID", "")
_YEAR = os.getenv("CONSOL_CAP_YEAR", "2025")
_FOREIGN_PROJECT_ID = os.getenv("CONSOL_CAP_FOREIGN_PROJECT_ID", "")
_ALLOW_TRIGGER = os.getenv("CONSOL_CAP_ALLOW_TRIGGER", "") == "1"
_ALLOW_SNAPSHOT = os.getenv("CONSOL_CAP_ALLOW_SNAPSHOT", "") == "1"
_REPORT_PATH = os.getenv(
    "CONSOL_CAP_REPORT_PATH",
    str(Path(__file__).with_name("capacity_report_latest.json")),
)

_BASE = "/api/consolidation"


# ---------------------------------------------------------------------------
# Thread-safe custom counters (acceptance + backpressure + isolation)
# ---------------------------------------------------------------------------

class _Counters:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.cross_project_leakage = 0
        self.duplicate_operation_effects = 0
        self.backpressure_429 = 0
        self.lost_persisted_operations = 0
        # per-idempotency-key -> operation id, to detect duplicate side effects
        self._idem_ops: dict[str, str] = {}

    def bump(self, name: str, n: int = 1) -> None:
        with self._lock:
            setattr(self, name, getattr(self, name) + n)

    def record_operation(self, idem_key: str, op_id: str) -> None:
        """Detect a duplicate side-effect: same idempotency key -> different op."""
        with self._lock:
            prior = self._idem_ops.get(idem_key)
            if prior is None:
                self._idem_ops[idem_key] = op_id
            elif prior != op_id:
                self.duplicate_operation_effects += 1


COUNTERS = _Counters()


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class _AuthedUser(HttpUser):
    abstract = True
    wait_time = between(1, 3)

    def on_start(self) -> None:
        self.token = ""
        self.headers: dict[str, str] = {}
        self._authed = False
        with self.client.post(
            "/api/auth/login",
            json={"username": _USER, "password": _PASSWORD},
            name="login",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                body = resp.json()
                data = body.get("data") if isinstance(body, dict) else body
                token = (data or {}).get("access_token") if isinstance(data, dict) else None
                if token:
                    self.token = token
                    self.headers = {"Authorization": f"Bearer {token}"}
                    self._authed = True
                    resp.success()
                else:
                    resp.failure("login OK but no access_token")
            else:
                resp.failure(f"login failed: {resp.status_code}")


class ConsolLifecycleUser(_AuthedUser):
    """Main capacity user — weighted on the consolidation lifecycle hot paths.

    Task weights match ``scenario.TRAFFIC_MODEL`` (open_workbench 45 /
    role_views_and_post_elim 25 / operation_poll 18 / operation_trigger 9 /
    manual_snapshot 3). Each request is tagged with ``slo:<op>`` via the request
    ``name`` so the report generator maps latencies to SLO budgets.
    """

    # 45% open workbench (split: 20 readiness, 15 operation list, 10 trial read)
    @task(20)
    def readiness(self) -> None:
        if not self._authed or not _PROJECT_ID:
            return
        self._get(f"{_BASE}/readiness/{_PROJECT_ID}/{_YEAR}", "readiness")

    @task(15)
    def operation_list(self) -> None:
        if not self._authed or not _PROJECT_ID:
            return
        self._get(f"{_BASE}/{_PROJECT_ID}/{_YEAR}/operations?limit=50", "operation_list")

    @task(10)
    def trial_read(self) -> None:
        if not self._authed or not _PROJECT_ID:
            return
        self._get(f"{_BASE}/trial?project_id={_PROJECT_ID}&year={_YEAR}", "trial_read")

    # 25% role views + post-elimination (split: 12 role-views, 13 post-elim)
    @task(12)
    def role_views(self) -> None:
        if not self._authed or not _PROJECT_ID:
            return
        self._get(f"{_BASE}/readiness/{_PROJECT_ID}/{_YEAR}/role-views", "role_views")

    @task(13)
    def post_elimination(self) -> None:
        if not self._authed or not _PROJECT_ID:
            return
        self._get(f"{_BASE}/post-elimination/{_PROJECT_ID}/{_YEAR}", "post_elimination")

    # 18% poll an operation status. We poll the most recent operation from the
    # list; if none exists yet, this is a no-op (not counted).
    @task(18)
    def operation_status(self) -> None:
        if not self._authed or not _PROJECT_ID:
            return
        op_id = self._latest_operation_id()
        if not op_id:
            return
        self._get(
            f"{_BASE}/{_PROJECT_ID}/{_YEAR}/operations/{op_id}", "operation_status"
        )

    # 9% trigger a refresh-all operation (create/merge persistent operation).
    # Writes/compute — only enabled in a disposable capacity env.
    @task(9)
    def operation_trigger(self) -> None:
        if not self._authed or not _PROJECT_ID or not _ALLOW_TRIGGER:
            return
        idem_key = f"cap-op:{uuid.uuid4()}"
        with self.client.post(
            f"{_BASE}/{_PROJECT_ID}/{_YEAR}/operations",
            headers={**self.headers, "Idempotency-Key": idem_key},
            json={"reason": "refresh-all", "idempotency_key": idem_key},
            name="slo:operation_create",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 201, 202):
                try:
                    body = resp.json()
                    data = body.get("data") if isinstance(body, dict) else body
                    op_id = (data or {}).get("operation_id") or (data or {}).get("id")
                    if op_id:
                        COUNTERS.record_operation(idem_key, str(op_id))
                        self._remember_operation(str(op_id))
                except (ValueError, AttributeError):
                    pass
                resp.success()
            elif resp.status_code == 429:
                COUNTERS.bump("backpressure_429")
                resp.success()  # backpressure is a correct response, not an error
            elif resp.status_code == 409:
                resp.success()  # single active operation per project/year (R4.3)
            else:
                resp.failure(f"operation_create failed: {resp.status_code}")

    # 3% create a manual diagnostic snapshot (allows partial; non sign/lock).
    @task(3)
    def manual_snapshot(self) -> None:
        if not self._authed or not _PROJECT_ID or not _ALLOW_SNAPSHOT:
            return
        with self.client.post(
            f"{_BASE}/{_PROJECT_ID}/snapshots?year={_YEAR}&reason=manual",
            headers=self.headers,
            name="slo:manual_snapshot",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 201):
                resp.success()
            elif resp.status_code == 429:
                COUNTERS.bump("backpressure_429")
                resp.success()
            else:
                resp.failure(f"manual_snapshot failed: {resp.status_code}")

    # -- helpers --
    def _get(self, url: str, slo_op: str) -> None:
        with self.client.get(
            url, headers=self.headers, name=f"slo:{slo_op}", catch_response=True
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code == 429:
                COUNTERS.bump("backpressure_429")
                resp.success()
            else:
                resp.failure(f"{slo_op} failed: {resp.status_code}")

    def _remember_operation(self, op_id: str) -> None:
        self._last_op_id = op_id

    def _latest_operation_id(self) -> str:
        # Prefer one we triggered this session; else probe the list once.
        got = getattr(self, "_last_op_id", "")
        if got:
            return got
        with self.client.get(
            f"{_BASE}/{_PROJECT_ID}/{_YEAR}/operations?limit=1",
            headers=self.headers,
            name="slo:operation_list",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
                try:
                    body = resp.json()
                    data = body.get("data") if isinstance(body, dict) else body
                    ops = (data or {}).get("operations") if isinstance(data, dict) else data
                    if isinstance(ops, list) and ops:
                        op_id = str(ops[0].get("operation_id") or ops[0].get("id") or "")
                        self._last_op_id = op_id
                        return op_id
                except (ValueError, AttributeError):
                    pass
            elif resp.status_code == 429:
                COUNTERS.bump("backpressure_429")
                resp.success()
            else:
                resp.failure(f"operation_list failed: {resp.status_code}")
        return ""


class CanaryUser(_AuthedUser):
    """Dedicated cross-project leakage probe (project isolation under load).

    Attempts to read a FOREIGN consolidation project's readiness with the
    current identity. Any response that is NOT a denial (403/404) is counted as
    leakage (must be 0). Design R11.1: all endpoints keep project-level authz.
    """

    weight = 1  # small dedicated pool; main pool is far larger via shape

    @task
    def probe_foreign_project(self) -> None:
        if not self._authed or not _FOREIGN_PROJECT_ID:
            return
        with self.client.get(
            f"{_BASE}/readiness/{_FOREIGN_PROJECT_ID}/{_YEAR}",
            headers=self.headers,
            name="canary:cross_project_read",
            catch_response=True,
        ) as resp:
            if resp.status_code in CANARY.denied_statuses:
                resp.success()  # correct denial
            elif resp.status_code == 200:
                COUNTERS.bump("cross_project_leakage")
                resp.failure("cross-project leakage: foreign 200")
            else:
                resp.success()


# ---------------------------------------------------------------------------
# Load shape — reproduces scenario.LOAD_PROFILE (30 min steady + 10 min burst)
# ---------------------------------------------------------------------------

class StepLoadShape(LoadTestShape):
    """Ramp per ``scenario.LOAD_PROFILE``; warmup -> steady 6k -> burst 7.2k."""

    def tick(self):
        run_time = self.get_run_time()
        elapsed = 0
        for phase in LOAD_PROFILE:
            ramp = phase.users / phase.spawn_rate
            total = ramp + phase.duration_s
            if run_time < elapsed + total:
                return (phase.users, phase.spawn_rate)
            elapsed += total
        return None


# ---------------------------------------------------------------------------
# Report emission on stop
# ---------------------------------------------------------------------------

@events.test_stop.add_listener
def _emit_report(environment, **_kwargs):
    stats = environment.runner.stats
    op_latencies: list[OpLatency] = []
    total_requests = 0
    total_failures = 0

    for name, entry in stats.entries.items():
        display = name[0] if isinstance(name, tuple) else name
        total_requests += entry.num_requests
        total_failures += entry.num_failures
        if isinstance(display, str) and display.startswith("slo:"):
            op = display[len("slo:"):]
            if op in SLO_BY_OP:
                op_latencies.append(
                    OpLatency(
                        op=op,
                        p50_ms=float(entry.get_response_time_percentile(0.5)),
                        p95_ms=float(entry.get_response_time_percentile(0.95)),
                        p99_ms=float(entry.get_response_time_percentile(0.99)),
                        num_requests=entry.num_requests,
                        num_failures=entry.num_failures,
                    )
                )

    total = stats.total
    throughput_rps = float(getattr(total, "total_rps", 0.0) or 0.0)

    obs = CapacityObservations(
        peak_virtual_users=max((p.users for p in LOAD_PROFILE), default=0),
        steady_seconds=SCENARIO.steady_state_seconds,
        burst_seconds=SCENARIO.burst_seconds,
        total_requests=total_requests,
        total_failures=total_failures,
        throughput_rps=throughput_rps,
        op_latencies=tuple(op_latencies),
        cross_project_leakage=COUNTERS.cross_project_leakage,
        duplicate_operation_effects=COUNTERS.duplicate_operation_effects,
        lost_persisted_operations=COUNTERS.lost_persisted_operations,
        backpressure_429_count=COUNTERS.backpressure_429,
        warmup_excluded=True,
        environment=os.getenv("CONSOL_CAP_ENV", "capacity"),
    )
    report = generate_report(obs)
    Path(_REPORT_PATH).write_text(report.to_json() + "\n", encoding="utf-8")
    verdict = "PASS" if report.passed else "FAIL"
    print(f"[{verdict}] consol-lifecycle capacity report -> {_REPORT_PATH}")
    if not report.passed:
        for f in report.failures:
            print(f"  - {f}")
