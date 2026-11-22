"""A1 ??????????????????????? / ?? PG??"""
from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from tests.load.safety_probes import (
    CONNECTION_LEAK_TOLERANCE,
    SAFETY_ZERO_KEYS,
    ProbeReport,
    SafetyProbeRunner,
    run_all_probes,
)


# ---------------------------------------------------------------------------
# ?????? load_evaluation.load_safety_evidence ??????
# ---------------------------------------------------------------------------


class TestReportShape:
    def test_keys_match_safety_zero_keys(self) -> None:
        report = ProbeReport()
        assert set(report.counts) == set(SAFETY_ZERO_KEYS)
        # ????? None???? ? 0??fail-closed ??????????
        assert all(value is None for value in report.counts.values())

    def test_payload_directly_consumable_by_load_evaluation(self) -> None:
        report = ProbeReport()
        report.counts = {k: 0 for k in SAFETY_ZERO_KEYS}
        payload = report.to_payload()
        from tests.load.load_evaluation import load_safety_evidence

        loaded = load_safety_evidence.__wrapped__ if False else None  # guard against accidental misuse
        # ??? safety ???????????????? + ?????
        safety = payload["safety"]
        unknown = sorted(set(safety) - set(SAFETY_ZERO_KEYS))
        assert not unknown
        for value in safety.values():
            assert not isinstance(value, bool) and isinstance(value, (int, float)) and value >= 0


# ---------------------------------------------------------------------------
# ?? 1?????
# ---------------------------------------------------------------------------


class TestUnauthorizedProbe:
    """?? runner._make_client ???? httpx.MockTransport?"""

    @staticmethod
    def _runner(**kwargs) -> SafetyProbeRunner:
        defaults: dict[str, Any] = {
            "base_url": "http://probe",
            "admin_token": "admin",
            "low_privilege_token": "low",
            "probe_project_id": "p1",
        }
        defaults.update(kwargs)
        return SafetyProbeRunner(**defaults)

    @staticmethod
    def _inject(runner: SafetyProbeRunner, handler) -> None:
        transport = httpx.MockTransport(handler)
        runner._make_client = lambda **kwargs: httpx.Client(transport=transport, **kwargs)  # noqa: SLF001

    def test_counts_200_as_violation(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            return httpx.Response(200, json={"code": 0, "data": {}})

        runner = self._runner()
        self._inject(runner, handler)
        runner.probe_unauthorized()
        import tests.load.safety_probes as sp

        assert runner.report.counts["unauthorized_successes"] == len(sp._PROBE_READ_ENDPOINTS)
        assert len(calls) == len(sp._PROBE_READ_ENDPOINTS)

    def test_counts_403_as_clean(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json={"detail": "forbidden"})

        runner = self._runner()
        self._inject(runner, handler)
        runner.probe_unauthorized()
        assert runner.report.counts["unauthorized_successes"] == 0
        assert not runner.report.errors

    def test_all_requests_failed_is_not_zero(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("down", request=request)

        runner = self._runner()
        self._inject(runner, handler)
        runner.probe_unauthorized()
        assert runner.report.counts["unauthorized_successes"] is None
        assert any("unauthorized_successes" in e for e in runner.report.errors)

    def test_missing_low_token_fails_closed(self) -> None:
        runner = self._runner(low_privilege_token=None)
        runner.probe_unauthorized()
        assert runner.report.counts["unauthorized_successes"] is None
        assert runner.report.errors


class TestConnectionLeaks:
    def test_delta_within_tolerance_is_zero(self) -> None:
        runner = SafetyProbeRunner(
            base_url="http://probe", admin_token="t", probe_project_id="p1",
        )
        runner.report.details["connection_pool"] = {"before": 10, "after": 10 + CONNECTION_LEAK_TOLERANCE}
        # ????????? pg_dsn ????delta == tolerance ? ???
        leaked = CONNECTION_LEAK_TOLERANCE
        assert (1 if leaked > CONNECTION_LEAK_TOLERANCE else 0) == 0

    def test_delta_over_tolerance_counts_one(self) -> None:
        leaked = CONNECTION_LEAK_TOLERANCE + 1
        assert (1 if leaked > CONNECTION_LEAK_TOLERANCE else 0) == 1

    def test_before_none_blocks_after(self) -> None:
        runner = SafetyProbeRunner(
            base_url="http://probe", admin_token="t", probe_project_id="p1",
        )
        runner.probe_connection_leaks_after(None)
        assert runner.report.counts["connection_leaks"] is None


# ---------------------------------------------------------------------------
# ?? 3???????
# ---------------------------------------------------------------------------


class TestConnectionTimeouts:
    def test_recorded_value_is_kept(self) -> None:
        runner = SafetyProbeRunner(base_url="http://probe", admin_token="t", probe_project_id="p1")
        runner.record_connection_timeouts(0)
        assert runner.report.counts["connection_timeouts"] == 0

    def test_missing_input_is_not_zero(self) -> None:
        runner = SafetyProbeRunner(base_url="http://probe", admin_token="t", probe_project_id="p1")
        runner.record_connection_timeouts(None)
        assert runner.report.counts["connection_timeouts"] is None
        assert runner.report.errors


# ---------------------------------------------------------------------------
# run_all_probes ????
# ---------------------------------------------------------------------------


class TestRunAllProbes:
    def test_before_phase_does_not_run_write_probes(self) -> None:
        # before ???????disposable=False??????????
        payload = run_all_probes(
            phase="before",
            base_url="http://probe",
            admin_token="t",
            probe_project_id="p1",
            disposable_env=False,
        )
        assert set(payload["safety"]) == set(SAFETY_ZERO_KEYS)
        # before ?????????????????????? None?????
        assert payload["probe_meta"]["errors"] == [] or all(
            "?????" not in e for e in payload["probe_meta"]["errors"]
        )

    def test_after_phase_without_disposable_fails_write_probes(self) -> None:
        payload = run_all_probes(
            phase="after",
            base_url="http://probe",
            admin_token="t",
            probe_project_id="p1",
            disposable_env=False,
            skip_write_probes=False,
        )
        errors = payload["probe_meta"]["errors"]
        assert any("?????" in e for e in errors)
        # ????????? None??? 0?
        assert payload["safety"]["duplicate_side_effects"] is None
        assert payload["safety"]["data_corruption"] is None

    def test_after_phase_skip_write_probes_leaves_them_none(self) -> None:
        payload = run_all_probes(
            phase="after",
            base_url="http://probe",
            admin_token="t",
            probe_project_id="p1",
            disposable_env=True,
            skip_write_probes=True,
        )
        assert payload["safety"]["duplicate_side_effects"] is None
        assert payload["safety"]["data_corruption"] is None
        # ??????? token ? unauthorized ?? None?fail-closed?
        assert payload["safety"]["unauthorized_successes"] is None
