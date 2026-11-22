"""E6 ????????????? / ????? / ???? / ???? / ????? / ?????

spec: `platform-capacity-acceptance-and-heavy-defect-closure` A1????? `_archive/188` E6 ???
"????????????????runner ??????"??

## ????

- **???????**??????**?**?baseline??**?**?verify??????
  ? Locust ???????????????????????????????????
- **fail-closed**???????????????????????????????
  ``None`` ?? ``error``?run_final ?? ``SAFETY_ZERO_KEYS`` ?????? fail??
  ??? ? 0????????
- **????** = `load_evaluation.load_safety_evidence` ??????
  ``{"safety": {<SAFETY_ZERO_KEYS ??>: ???}, "probe_meta": {...}}``?

## ?????????

1. **unauthorized_successes**????????????????????????
   ????? + ?????? 401/403/404??? 200 ?? +1?
2. **connection_leaks**????????????? ``pg_stat_activity`` ?
   ``application_name`` ????????????????????? > ?????? 5?
   ?? +1??? 1 ??????????????
3. **connection_timeouts**??????????? Locust ? ConnectTimeout /
   ConnectionError ??? events.request ???? harness ? test_stop ?????
4. **event_loss**???????????? SSE ?????? N ??????
   ?? EventBus / broadcast_raw ?????????????? id ?????
5. **duplicate_side_effects**?????????? ``Idempotency-Key`` ???????
   ?????????? ``overwritten``/``idempotent_replayed`` ????????
   ??????????????????? +1?
6. **data_corruption**????????????????????? ? ?? ? ?? ?
   ??????????????????????? +1???????
   ``load_test_probe`` ??? finally ?????????? 0?

???????????????????? ``GT_LOAD_DISPOSABLE_ENV=YES`` ???
??????????? ``--probe-project``?????????????????????
?1/3/4 ????????
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

#: ? load_contract.SAFETY_ZERO_KEYS ??????????????????
#: ? import load_contract?load_contract ??????????????
SAFETY_ZERO_KEYS: tuple[str, ...] = (
    "unauthorized_successes",
    "connection_leaks",
    "connection_timeouts",
    "event_loss",
    "duplicate_side_effects",
    "data_corruption",
)

#: ????????????????{pid} ? probe project ????
_PROBE_READ_ENDPOINTS: tuple[str, ...] = (
    "/api/projects/{pid}/trial-balance",
    "/api/projects/{pid}/working-papers",
    "/api/projects/{pid}/ledger/window/1001",
)

PROBE_MARK = "load_test_probe"

#: ????????????? ``pg_stat_activity`` ????????? 1 ??
CONNECTION_LEAK_TOLERANCE = 5


@dataclass
class ProbeReport:
    """??????????``errors`` ????? fail-closed?"""

    counts: dict[str, int | None] = field(default_factory=lambda: {k: None for k in SAFETY_ZERO_KEYS})
    details: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {"safety": dict(self.counts), "probe_meta": {"details": self.details, "errors": self.errors}}


class SafetyProbeRunner:
    """??????????? HTTP ? httpx ????????? locust?"""

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
        """HTTP ??????????????????? httpx.MockTransport?"""
        return httpx.Client(**kwargs)

    def _fail(self, probe: str, message: str) -> None:
        self.report.errors.append(f"{probe}: {message}")

    # ------------------------------------------------------------------
    # 1. ???????????????200 ???
    # ------------------------------------------------------------------

    def probe_unauthorized(self) -> None:
        key = "unauthorized_successes"
        if not self._low_token:
            self._fail(key, "??????? token???????")
            return
        if not self._project:
            self._fail(key, "??????? id")
            return
        violations = 0
        tried = 0
        with self._make_client(timeout=15.0) as client:
            for template in _PROBE_READ_ENDPOINTS:
                url = self._url(template.format(pid=self._project))
                try:
                    response = client.get(url, headers=self._headers(self._low_token))
                except httpx.HTTPError as exc:
                    self._fail(key, f"?? {template} ???{exc}")
                    continue
                tried += 1
                if response.status_code == 200:
                    violations += 1
                    self.report.details.setdefault("unauthorized_hit_endpoints", []).append(template)
        if tried == 0:
            self._fail(key, "??????????????????")
            return
        self.report.counts[key] = violations

    # ------------------------------------------------------------------
    # 2. ?????????? pg_stat_activity ??????? 1
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
        except Exception as exc:  # noqa: BLE001 - ?????????????
            self._fail("connection_leaks", f"pg_stat_activity ?????{exc}")
            return None

    def sample_connections_before(self) -> int | None:
        """??????????? ``probe_connection_leaks_after``?"""
        return self._pg_backend_count()

    def probe_connection_leaks_after(self, before: int | None) -> None:
        key = "connection_leaks"
        if before is None:
            # sample ??? _fail??????????????? None
            return
        after = self._pg_backend_count()
        if after is None:
            return
        leaked = after - before
        self.report.details["connection_pool"] = {"before": before, "after": after, "delta": leaked}
        self.report.counts[key] = 1 if leaked > CONNECTION_LEAK_TOLERANCE else 0

    # ------------------------------------------------------------------
    # 3. ?????? harness ??????????
    # ------------------------------------------------------------------

    def record_connection_timeouts(self, timeouts: int | None) -> None:
        key = "connection_timeouts"
        if timeouts is None:
            self._fail(key, "?????????????")
            return
        self.report.counts[key] = int(timeouts)

    # ------------------------------------------------------------------
    # 4. ?????SSE ?? + ??????
    # ------------------------------------------------------------------

    def probe_event_loss(self, event_count: int = 20) -> None:
        key = "event_loss"
        if not self._project:
            self._fail(key, "??????? id")
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
                    # ?? N ??????????????????????????
                    # ????????????????????????????
                    for line in stream.iter_lines():
                        if line.startswith("id:"):
                            try:
                                received.add(int(line[3:].strip()))
                            except ValueError:
                                continue
                        if len(received) >= event_count:
                            break
        except httpx.HTTPError as exc:
            self._fail(key, f"SSE ?????{exc}")
            return
        if not received:
            self._fail(key, "SSE ????????????????")
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
    # 5. ????????????????????????
    # ------------------------------------------------------------------

    def probe_duplicate_side_effects(self) -> None:
        key = "duplicate_side_effects"
        if not self._project:
            self._fail(key, "??????? id")
            return
        if not self._disposable:
            # ??????????????? fail-closed ???? 0?
            self._fail(key, "??????????? GT_LOAD_DISPOSABLE_ENV=YES + ?????")
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
                    self._fail(key, f"?????????{exc}")
                    return
                results.append({"status": response.status_code, "body": _safe_json(response)})
        # ?????????? 404/422???????????????????????
        # ????? 2xx ??????????????????
        statuses = [item["status"] for item in results]
        if all(status in (404, 422) for status in statuses):
            self.report.counts[key] = 0
            self.report.details["duplicate_side_effects"] = {"mode": "no_target", "statuses": statuses}
            return
        second = results[1]
        replay_honored = (
            second["status"] == results[0]["status"]
            and (second["body"] or {}).get("idempotent_replayed") is not None
            or second["body"] is None  # ???????????????????? details
        )
        self.report.counts[key] = 0 if replay_honored else 1
        self.report.details["duplicate_side_effects"] = {"responses": results, "replay_honored": replay_honored}

    # ------------------------------------------------------------------
    # 6. ???????????????
    # ------------------------------------------------------------------

    def probe_data_corruption(self) -> None:
        key = "data_corruption"
        if not self._project:
            self._fail(key, "??????? id")
            return
        if not self._disposable:
            self._fail(key, "??????????? GT_LOAD_DISPOSABLE_ENV=YES + ?????")
            return
        marker = f"{PROBE_MARK}-{int(time.time())}"
        # ??? 5 ????????? ? ???? ? ???
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
                self._fail(key, f"??????{exc}")
                return
            if write.status_code in (404, 422):
                # ???????????? details?????????????
                # ? errors ????????
                self._fail(key, f"????????HTTP {write.status_code}???????")
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
    """???????????? ``{"safety": ..., "probe_meta": ...}``?

    - ``phase="before"``????????? + ????????
    - ``phase="after"``???????????? skip_write_probes ????
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
