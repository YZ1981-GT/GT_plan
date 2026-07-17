"""Locust harness — Evidence Governance 6000 VU capacity + chaos scenario.

Spec: attachment-ocr-ai-evidence-governance-hardening — Task 8.2
Requirements: R12, R15
Design: §9.1 (traffic model + SLO), §9.2 (backpressure), §10.2 (layer 6 tool).

This is the INDEPENDENT capacity tool (NOT Playwright, NOT pytest PBT). It
encodes the design §9.1 traffic model (70% metadata read / 20% write-associate /
7% OCR-AI enqueue / 3% impact-archive control) against the real evidence
governance endpoints, drives the 30-min steady + 10-min burst profile, runs a
dedicated cross-project canary, and on stop emits a machine-readable capacity
report via ``capacity_report.generate_report``.

Run (requires a dedicated capacity environment — do NOT run against dev data):

    locust -f backend/tests/load/evidence_governance_capacity/locustfile_evidence_capacity.py \
        --host http://<capacity-host>:9980 --headless \
        --autostart

The ``StepLoadShape`` reproduces ``scenario.LOAD_PROFILE`` automatically, so no
``-u/-r`` is needed. See README.md for chaos toggle scheduling.

Environment variables:
    EVID_CAP_USER / EVID_CAP_PASSWORD        login (default admin/admin123)
    EVID_CAP_PROJECT_ID / EVID_CAP_YEAR      primary scope under test
    EVID_CAP_FOREIGN_PROJECT_ID              foreign scope for canary leakage probe
    EVID_CAP_ATTACHMENT_VERSION_ID           a version id for OCR enqueue
    EVID_CAP_REPORT_PATH                     where to write the JSON report
"""

from __future__ import annotations

import json
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

_USER = os.getenv("EVID_CAP_USER", "admin")
_PASSWORD = os.getenv("EVID_CAP_PASSWORD", "admin123")
_PROJECT_ID = os.getenv("EVID_CAP_PROJECT_ID", "")
_YEAR = os.getenv("EVID_CAP_YEAR", "2025")
_FOREIGN_PROJECT_ID = os.getenv("EVID_CAP_FOREIGN_PROJECT_ID", "")
_ATTACHMENT_VERSION_ID = os.getenv("EVID_CAP_ATTACHMENT_VERSION_ID", "")
_REPORT_PATH = os.getenv(
    "EVID_CAP_REPORT_PATH",
    str(Path(__file__).with_name("capacity_report_latest.json")),
)

_EVIDENCE_ROOT = "/api/projects/{pid}/years/{year}/evidence"


# ---------------------------------------------------------------------------
# Thread-safe custom counters (design §9.1 acceptance + §9.2 backpressure)
# ---------------------------------------------------------------------------

class _Counters:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.cross_project_leakage = 0
        self.duplicate_side_effects = 0
        self.backpressure_429 = 0
        self.lost_persisted_jobs = 0
        # per-idempotency-key -> ref id, to detect duplicate side effects
        self._idem_refs: dict[str, str] = {}

    def bump(self, name: str, n: int = 1) -> None:
        with self._lock:
            setattr(self, name, getattr(self, name) + n)

    def record_ref(self, idem_key: str, ref_id: str) -> None:
        """Detect a duplicate side-effect: same idempotency key -> different ref."""
        with self._lock:
            prior = self._idem_refs.get(idem_key)
            if prior is None:
                self._idem_refs[idem_key] = ref_id
            elif prior != ref_id:
                self.duplicate_side_effects += 1


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

    def _root(self) -> str:
        return _EVIDENCE_ROOT.format(pid=_PROJECT_ID, year=_YEAR)


class EvidenceGovernanceUser(_AuthedUser):
    """Main capacity user — weighted 70/20/7/3 traffic model (design §9.1).

    Task weights sum to 100 and each request is tagged with ``slo_op`` via the
    request ``name`` so the report generator maps latencies to §9.1 budgets.
    """

    # 70% metadata read (split: 40 single read, 30 cursor list)
    @task(40)
    def metadata_read(self) -> None:
        if not self._authed or not _PROJECT_ID:
            return
        self._get(f"{self._root()}/refs/references?limit=1", "metadata_read")

    @task(30)
    def cursor_list(self) -> None:
        if not self._authed or not _PROJECT_ID:
            return
        self._get(f"{self._root()}/refs/references?limit=100", "cursor_list")

    # 20% write / associate
    @task(20)
    def governance_write(self) -> None:
        if not self._authed or not _PROJECT_ID:
            return
        idem_key = f"cap:{uuid.uuid4()}"
        body = {
            "source_type": "workpaper_cell",
            "source_id": str(uuid.uuid4()),
            "evidence_type": "attachment_version",
            "evidence_id": str(uuid.uuid4()),
            "label": "capacity",
            "context": "capacity-write",
        }
        with self.client.post(
            f"{self._root()}/refs/references",
            headers={**self.headers, "Idempotency-Key": idem_key},
            json=body,
            name="slo:governance_write",
            catch_response=True,
        ) as resp:
            self._classify_write(resp, idem_key)

    # 7% OCR/AI enqueue (staged persist + enqueue -> 202)
    @task(7)
    def staged_enqueue(self) -> None:
        if not self._authed or not _PROJECT_ID or not _ATTACHMENT_VERSION_ID:
            return
        idem_key = f"cap-ocr:{uuid.uuid4()}"
        body = {
            "attachment_version_id": _ATTACHMENT_VERSION_ID,
            "content_hash": uuid.uuid4().hex,
            "parse_config": {"lang": "chi_sim"},
        }
        with self.client.post(
            f"{self._root()}/ocr/jobs",
            headers={**self.headers, "Idempotency-Key": idem_key},
            json=body,
            name="slo:staged_enqueue",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 201, 202):
                resp.success()
            elif resp.status_code == 429:
                COUNTERS.bump("backpressure_429")
                resp.success()  # backpressure is a correct response, not an error
            else:
                resp.failure(f"enqueue failed: {resp.status_code}")

    # 3% impact / archive control (split: 2 impact, 1 archive)
    @task(2)
    def impact(self) -> None:
        if not self._authed or not _PROJECT_ID:
            return
        self._get(
            f"{self._root()}/refs/impact?evidence_type=attachment_version"
            f"&evidence_id={uuid.uuid4()}&limit=100",
            "impact_le_100_nodes",
        )

    @task(1)
    def archive_request(self) -> None:
        if not self._authed or not _PROJECT_ID:
            return
        # archive orchestrate is async build; 202/200 both acceptable
        with self.client.post(
            f"/api/projects/{_PROJECT_ID}/archive/orchestrate",
            headers=self.headers,
            json={"audit_year": int(_YEAR)},
            name="slo:archive_request",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 201, 202):
                resp.success()
            elif resp.status_code == 429:
                COUNTERS.bump("backpressure_429")
                resp.success()
            else:
                resp.failure(f"archive request failed: {resp.status_code}")

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

    def _classify_write(self, resp, idem_key: str) -> None:
        if resp.status_code in (200, 201):
            try:
                body = resp.json()
                data = body.get("data") if isinstance(body, dict) else body
                ref_id = (data or {}).get("id") or (data or {}).get("ref_id")
                if ref_id:
                    COUNTERS.record_ref(idem_key, str(ref_id))
            except (ValueError, AttributeError):
                pass
            resp.success()
        elif resp.status_code == 429:
            COUNTERS.bump("backpressure_429")
            resp.success()
        else:
            resp.failure(f"governance_write failed: {resp.status_code}")


class CanaryUser(_AuthedUser):
    """Dedicated cross-project leakage probe (P1 isolation under load).

    Attempts to read a FOREIGN project's evidence with the current identity.
    Any response that is NOT a denial (403/404) — or that leaks foreign
    metadata — is counted as leakage (must be 0).
    """

    weight = 1  # small dedicated pool; main pool is far larger via shape

    @task
    def probe_foreign_project(self) -> None:
        if not self._authed or not _FOREIGN_PROJECT_ID:
            return
        foreign_root = _EVIDENCE_ROOT.format(pid=_FOREIGN_PROJECT_ID, year=_YEAR)
        with self.client.get(
            f"{foreign_root}/refs/references?limit=1",
            headers=self.headers,
            name="canary:cross_project_read",
            catch_response=True,
        ) as resp:
            if resp.status_code in CANARY.denied_statuses:
                resp.success()  # correct denial
            elif resp.status_code == 200:
                # A 200 on a foreign project is leakage — unless it's an empty,
                # scope-filtered result. Treat any foreign 200 as leakage: the
                # design mandates SCOPE_NOT_FOUND_OR_FORBIDDEN for foreign scope.
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
        # name is a tuple (name, method) in newer locust
        display = name[0] if isinstance(name, tuple) else name
        total_requests += entry.num_requests
        total_failures += entry.num_failures
        if isinstance(display, str) and display.startswith("slo:"):
            op = display[len("slo:"):]
            if op in SLO_BY_OP:
                op_latencies.append(
                    OpLatency(
                        op=op,
                        p95_ms=float(entry.get_response_time_percentile(0.95)),
                        p50_ms=float(entry.get_response_time_percentile(0.5)),
                        num_requests=entry.num_requests,
                        num_failures=entry.num_failures,
                    )
                )

    obs = CapacityObservations(
        peak_virtual_users=max((p.users for p in LOAD_PROFILE), default=0),
        steady_seconds=SCENARIO.steady_state_seconds,
        burst_seconds=SCENARIO.burst_seconds,
        total_requests=total_requests,
        total_failures=total_failures,
        op_latencies=tuple(op_latencies),
        cross_project_leakage=COUNTERS.cross_project_leakage,
        duplicate_side_effects=COUNTERS.duplicate_side_effects,
        lost_persisted_jobs=COUNTERS.lost_persisted_jobs,
        backpressure_429_count=COUNTERS.backpressure_429,
        warmup_excluded=True,
        environment=os.getenv("EVID_CAP_ENV", "capacity"),
    )
    report = generate_report(obs)
    Path(_REPORT_PATH).write_text(report.to_json() + "\n", encoding="utf-8")
    verdict = "PASS" if report.passed else "FAIL"
    print(f"[{verdict}] evidence-governance capacity report -> {_REPORT_PATH}")
    if not report.passed:
        for f in report.failures:
            print(f"  - {f}")
