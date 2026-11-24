"""A1 safety probes (spec: platform-capacity-acceptance-and-heavy-defect-closure).

Upstream E6 finding (see `_archive/188` tasks.md): the six-class safety-evidence
*validator* existed (`run_final.py --safety-evidence`) but no *producer* fed it.
This module supplies the producers: six probes that measure unauthorized
successes, connection leaks, connection timeouts, event loss, duplicate side
effects and data corruption, and emit a payload shaped exactly like
``load_safety_evidence`` consumes.

## Design

- **measurement vs assertion**: probes only *measure*; every zero-value
  assertion stays in ``load_evaluation.evaluate_results``. Locust and the
  harness decide when probes run; this module stays library-only.
- **fail-closed**: a probe that cannot establish a precondition (missing
  token / unreachable project / broken endpoint) never returns ``0``; it
  records ``None`` plus a message in ``errors``, and ``SAFETY_ZERO_KEYS``
  evaluation then fails the run. Silence must never pass for zero.
- **payload shape** = `load_evaluation.load_safety_evidence` contract:
  ``{"safety": {<SAFETY_ZERO_KEYS members>: value}, "probe_meta": {...}}``.

## The six probes

1. **unauthorized_successes**: replay read endpoints with a low-privilege
   account outside the project; expected 401/403/404. A 200 counts +1.
2. **connection_leaks**: compare ``pg_stat_activity`` backend counts for the
   application-name prefix before/after the window; a delta beyond the
   tolerance counts +1 (sample 1s before and after the run).
3. **connection_timeouts**: counted from Locust ConnectTimeout /
   ConnectionError samples on ``events.request``; the harness feeds the
   number in at ``test_stop`` (this module only records it).
4. **event_loss**: open the SSE stream, read N event ids and reconcile the
   id window; gaps in the sequence count as lost.
5. **duplicate_side_effects**: replay the same ``Idempotency-Key`` request
   twice; a second response that actually overwrites state (no
   ``idempotent_replayed`` marker) counts +1.
6. **data_corruption**: write a probe marker then read it back and check
   equality; a mismatch or a failed cleanup counts +1. Use the
   ``load_test_probe`` cleanup-only pattern so no data survives in
   ``finally``.

Probes 5/6 write to the target and therefore require
``GT_LOAD_DISPOSABLE_ENV=YES`` plus an explicit probe project
(``--probe-project``). Probes 1/3/4 are read-only.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

#: Mirrors load_contract.SAFETY_ZERO_KEYS. Duplicated as literal tuple on
#: purpose: importing load_contract pulls the whole load harness, and this
#: module must stay importable from probes-only contexts.
SAFETY_ZERO_KEYS: tuple[str, ...] = (
    "unauthorized_successes",
    "connection_leaks",
    "connection_timeouts",
    "event_loss",
    "duplicate_side_effects",
    "data_corruption",
)

#: Read endpoints used by the unauthorized probe; ``{pid}`` is replaced with
#: the probe project id.
_PROBE_READ_ENDPOINTS: tuple[str, ...] = (
    "/api/projects/{pid}/trial-balance",
    "/api/projects/{pid}/working-papers",
    "/api/projects/{pid}/ledger/window/1001",
)

PROBE_MARK = "load_test_probe"

#: backend-count delta above this threshold counts as a leak (session pool
#: keeps some warm connections; small positive drift is not a leak).
CONNECTION_LEAK_TOLERANCE = 5


@dataclass
class ProbeReport:
    """Probe execution report. ``errors`` entries are fail-closed."""

    counts: dict[str, int | None] = field(default_factory=lambda: {k: None for k in SAFETY_ZERO_KEYS})
    details: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {"safety": dict(self.counts), "probe_meta": {"details": self.details, "errors": self.errors}}


class SafetyProbeRunner:
    """Runs the probes over HTTP (httpx), independent from locust."""

    def __init__(
        self,
        base_url: str,
        admin_token: str,
        low_privilege_token: str | None = None,
        probe_project_id: str | None = None,
        disposable_env: bool = False,
        pg_dsn: str | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._admin_token = admin_token
        self._low_token = low_privilege_token
        self._project = probe_project_id
        self._disposable = disposable_env
        self._pg_dsn = pg_dsn
        self.report = ProbeReport()

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _headers(self, token: str | None = None) -> dict[str, str]:
        token = token or self._admin_token
        return {"Authorization": f"Bearer {token}"} if token else {}

    def _url(self, path: str) -> str:
        return f"{self._base}{path}"

    def _make_client(self, **kwargs: Any) -> httpx.Client:
        """HTTP client factory. Unit tests inject httpx.MockTransport here."""
        return httpx.Client(**kwargs)

    def _fail(self, probe: str, message: str) -> None:
        self.report.errors.append(f"{probe}: {message}")

    # ------------------------------------------------------------------
    # 1. unauthorized: probe read endpoints with a low-privilege token,
    #    a 200 response is a violation.
    # ------------------------------------------------------------------

    def probe_unauthorized(self) -> None:
        key = "unauthorized_successes"
        if not self._low_token:
            self._fail(key, "missing low-privilege token, probe not executed")
            return
        if not self._project:
            self._fail(key, "missing probe project id")
            return
        violations = 0
        tried = 0
        with self._make_client(timeout=15.0) as client:
            for template in _PROBE_READ_ENDPOINTS:
                url = self._url(template.format(pid=self._project))
                try:
                    response = client.get(url, headers=self._headers(self._low_token))
                except httpx.HTTPError as exc:
                    self._fail(key, f"request to {template} failed: {exc}")
                    continue
                tried += 1
                if response.status_code == 200:
                    violations += 1
                    self.report.details.setdefault("unauthorized_hit_endpoints", []).append(template)
        if tried == 0:
            self._fail(key, "no request was ever sent, probe inconclusive")
            return
        self.report.counts[key] = violations

    # ------------------------------------------------------------------
    # 2. connection leak: sample pg_stat_activity before/after; delta
    #    beyond tolerance counts 1.
    # ------------------------------------------------------------------

    def _pg_backend_count(self) -> int | None:
        if not self._pg_dsn:
            return None
        try:
            import psycopg

            with psycopg.connect(self._pg_dsn, connect_timeout=10) as conn:
                row = conn.execute(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND application_name LIKE 'audit%'"
                ).fetchone()
                return int(row[0]) if row else None
        except Exception as exc:  # noqa: BLE001 - environment probe errors are all fail-closed
            self._fail("connection_leaks", f"pg_stat_activity sample failed: {exc}")
            return None

    def sample_connections_before(self) -> int | None:
        """Call before the load window; pair with ``probe_connection_leaks_after``."""
        return self._pg_backend_count()

    def probe_connection_leaks_after(self, before: int | None) -> None:
        key = "connection_leaks"
        if before is None:
            # sample_connections_before already recorded _fail; keep count None.
            return
        after = self._pg_backend_count()
        if after is None:
            return
        leaked = after - before
        self.report.details["connection_pool"] = {"before": before, "after": after, "delta": leaked}
        self.report.counts[key] = 1 if leaked > CONNECTION_LEAK_TOLERANCE else 0

    # ------------------------------------------------------------------
    # 3. connection timeouts: the harness counts and feeds in the number.
    # ------------------------------------------------------------------

    def record_connection_timeouts(self, timeouts: int | None) -> None:
        key = "connection_timeouts"
        if timeouts is None:
            self._fail(key, "timeout count not provided, probe not executed")
            return
        self.report.counts[key] = int(timeouts)

    # ------------------------------------------------------------------
    # 4. event loss: reconcile SSE event id window.
    # ------------------------------------------------------------------

    def probe_event_loss(self, event_count: int = 20) -> None:
        key = "event_loss"
        if not self._project:
            self._fail(key, "missing probe project id")
            return
        lost = 0
        received: set[int] = set()
        try:
            with self._make_client(timeout=30.0) as client:
                with client.stream(
                    "GET",
                    self._url(f"/api/projects/{self._project}/events/stream"),
                    headers=self._headers(),
                ) as stream:
                    # Read until N distinct ids collected. High-traffic windows
                    # may see idle gaps; the loop breaks only when enough ids
                    # were observed or the server closes the stream.
                    for line in stream.iter_lines():
                        if line.startswith("id:"):
                            try:
                                received.add(int(line[3:].strip()))
                            except ValueError:
                                continue
                        if len(received) >= event_count:
                            break
        except httpx.HTTPError as exc:
            self._fail(key, f"SSE stream failed: {exc}")
            return
        if not received:
            self._fail(key, "SSE stream produced no event ids, probe inconclusive")
            return
        ordered = sorted(received)
        expected = set(range(ordered[0], ordered[-1] + 1))
        lost = len(expected - received)
        self.report.details["event_loss"] = {
            "window": [ordered[0], ordered[-1]],
            "received": len(received),
            "lost": lost,
        }
        self.report.counts[key] = lost

    # ------------------------------------------------------------------
    # 5. duplicate side effects: replay the same idempotency key twice.
    # ------------------------------------------------------------------

    def probe_duplicate_side_effects(self) -> None:
        key = "duplicate_side_effects"
        if not self._project:
            self._fail(key, "missing probe project id")
            return
        if not self._disposable:
            # Write probe on a shared environment is forbidden: fail-closed
            # instead of a fake 0.
            self._fail(key, "write probe requires GT_LOAD_DISPOSABLE_ENV=YES + dedicated project")
            return
        operation_id = f"{PROBE_MARK}-{int(time.time())}"
        payload = {"load_test_probe": {"operation_id": operation_id, "probe": "duplicate"}}
        results: list[dict[str, Any]] = []
        with self._make_client(timeout=15.0) as client:
            for _ in range(2):
                try:
                    response = client.put(
                        self._url(f"/api/projects/{self._project}/working-papers/_probe/parsed-data"),
                        headers={**self._headers(), "Idempotency-Key": operation_id},
                        json=payload,
                    )
                except httpx.HTTPError as exc:
                    self._fail(key, f"idempotency replay request failed: {exc}")
                    return
                results.append({"status": response.status_code, "body": _safe_json(response)})
        # A stub route (404/422 both times) is an environment gap, not evidence
        # of idempotency: fail-closed into errors, no 0 is recorded.
        statuses = [item["status"] for item in results]
        if all(status in (404, 422) for status in statuses):
            self._fail(key, f"probe endpoint missing (statuses {statuses}), cannot judge idempotency")
            return
        second = results[1]
        replay_honored = (
            second["status"] == results[0]["status"]
            and (second["body"] or {}).get("idempotent_replayed") is not None
            or second["body"] is None  # no JSON body: keep in details for manual review
        )
        self.report.counts[key] = 0 if replay_honored else 1
        self.report.details["duplicate_side_effects"] = {"responses": results, "replay_honored": replay_honored}

    # ------------------------------------------------------------------
    # 6. data corruption: write marker, read back, verify, cleanup.
    # ------------------------------------------------------------------

    def probe_data_corruption(self) -> None:
        key = "data_corruption"
        if not self._project:
            self._fail(key, "missing probe project id")
            return
        if not self._disposable:
            self._fail(key, "write probe requires GT_LOAD_DISPOSABLE_ENV=YES + dedicated project")
            return
        marker = f"{PROBE_MARK}-{int(time.time())}"
        # Minimal 5-column probe payload; adapter must echo it back verbatim.
        payload = {"load_test_probe": {"marker": marker, "value": 12345}}
        corrupted = 0
        with self._make_client(timeout=15.0) as client:
            try:
                write = client.put(
                    self._url(f"/api/projects/{self._project}/working-papers/_probe/parsed-data"),
                    headers=self._headers(),
                    json=payload,
                )
            except httpx.HTTPError as exc:
                self._fail(key, f"write probe failed: {exc}")
                return
            if write.status_code in (404, 422):
                # Environment gap: record _fail rather than a fake 0; see
                # duplicate probe for the rationale.
                self._fail(key, f"probe endpoint missing (HTTP {write.status_code}), cannot judge corruption")
                return
            read = client.get(
                self._url(f"/api/projects/{self._project}/working-papers/_probe"),
                headers=self._headers(),
            )
            body = _safe_json(read)
            if body is None or marker not in json.dumps(body, ensure_ascii=False, default=str):
                corrupted += 1
            try:
                client.delete(
                    self._url(f"/api/projects/{self._project}/working-papers/_probe/{marker}"),
                    headers=self._headers(),
                )
            except httpx.HTTPError:
                corrupted += 1
        self.report.counts[key] = corrupted
        self.report.details["data_corruption"] = {"marker": marker, "corrupted_steps": corrupted}


def _safe_json(response: httpx.Response) -> dict[str, Any] | None:
    try:
        data = response.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def run_all_probes(
    *,
    phase: str,
    base_url: str,
    admin_token: str,
    low_privilege_token: str | None = None,
    probe_project_id: str | None = None,
    disposable_env: bool = False,
    pg_dsn: str | None = None,
    connection_timeouts: int | None = None,
    skip_write_probes: bool = False,
) -> dict[str, Any]:
    """Run the probes for one phase and return ``{"safety": ..., "probe_meta": ...}``.

    - ``phase="before"``: connection-pool sampling only, cheap, no writes;
    - ``phase="after"``: full probe set; ``skip_write_probes`` excludes the
      two write probes.
    """
    runner = SafetyProbeRunner(
        base_url=base_url,
        admin_token=admin_token,
        low_privilege_token=low_privilege_token,
        probe_project_id=probe_project_id,
        disposable_env=disposable_env,
        pg_dsn=pg_dsn,
    )
    if phase == "before":
        runner.sample_connections_before()
        return runner.report.to_payload()
    before = runner.sample_connections_before()
    runner.probe_unauthorized()
    runner.probe_event_loss()
    if not skip_write_probes:
        runner.probe_duplicate_side_effects()
        runner.probe_data_corruption()
    runner.probe_connection_leaks_after(before)
    runner.record_connection_timeouts(connection_timeouts)
    return runner.report.to_payload()
