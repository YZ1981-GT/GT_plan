"""A4 ????????????????????? / ??? pytest ????"""
from __future__ import annotations

import json
from typing import Any

import pytest

import sys as _sys
from pathlib import Path as _Path

_SCRIPTS_OPS = _Path(__file__).resolve().parents[1] / "scripts" / "ops"
if str(_SCRIPTS_OPS.parent.parent) not in _sys.path:
    # ? backend/ ?? path ?? import scripts.ops.*?scripts ??????????
    _sys.path.insert(0, str(_SCRIPTS_OPS.parents[1]))

import scripts.ops.pgbouncer_gradual_rollout as rollout  # noqa: E402
from scripts.ops.pgbouncer_gradual_rollout import (  # noqa: E402
    GATE_THRESHOLDS,
    ROLLOUT_STAGES,
    check_gate,
    run_preconditions,
    sample_metrics,
)


class TestStageContract:
    def test_three_stages_exist(self) -> None:
        assert [pct for pct, _ in ROLLOUT_STAGES] == [2, 25, 100]

    def test_windows_are_ordered(self) -> None:
        windows = [w for _, w in ROLLOUT_STAGES]
        assert windows == sorted(windows), "??????????"


class TestCheckGate:
    def test_all_zero_passes(self) -> None:
        metrics = {key: 0.0 for key in GATE_THRESHOLDS}
        assert check_gate(metrics) == []

    def test_any_breach_is_listed(self) -> None:
        metrics = {key: 0.0 for key in GATE_THRESHOLDS}
        metrics["pool_wait_p95_ms"] = GATE_THRESHOLDS["pool_wait_p95_ms"] + 1
        breaches = check_gate(metrics)
        assert len(breaches) == 1
        assert "pool_wait_p95_ms" in breaches[0]

    def test_missing_sample_fails_closed(self) -> None:
        """-1????????????? ? ???"""
        metrics = {key: 0.0 for key in GATE_THRESHOLDS}
        metrics["error_rate_pct"] = -1.0
        breaches = check_gate(metrics)
        assert any("error_rate_pct" in b for b in breaches)

    def test_exact_threshold_is_not_a_breach(self) -> None:
        metrics = {key: value for key, value in GATE_THRESHOLDS.items()}
        assert check_gate(metrics) == []


class TestPreconditions:
    def test_runs_real_guard_suites(self) -> None:
        """????????????????? PG ??? PgBouncer ??? 2 passed / 7 skipped??"""
        ok, message = run_preconditions()
        # ??? bouncer??? 7 ? skip?2 ???? ? pytest ??? 0 ? ok=True
        assert ok, message
        assert "PASS" in message

    def test_precondition_list_is_pinned(self) -> None:
        assert "tests/test_pgbouncer_transaction_contract_pg.py" in rollout.PRECONDITION_TESTS
        assert "tests/test_connection_budget.py" in rollout.PRECONDITION_TESTS

    def test_precondition_failure_aborts_rollout(self, tmp_path, monkeypatch) -> None:
        """????????? 2 ?? aborted ???????????"""
        import json as _json
        monkeypatch.setattr(rollout, "run_preconditions", lambda: (False, "??????"))
        monkeypatch.setattr(rollout, "_STATE_FILE", tmp_path / "rollout_state.json")
        rc = rollout.run_rollout("http://127.0.0.1:1", None)
        assert rc == 2
        payload = _json.loads((tmp_path / "rollout_state.json").read_text(encoding="utf-8"))
        assert payload["status"] == "aborted_precondition"


class TestSampleMetrics:
    def test_backend_down_marks_error_rate_100(self) -> None:
        metrics = sample_metrics("http://127.0.0.1:1", None)
        assert metrics["error_rate_pct"] == 100.0
        # ???? -1??????check_gate ? fail-closed
        assert all(metrics[k] < 0 for k in GATE_THRESHOLDS if k != "error_rate_pct")

    def test_gate_rejects_backend_down(self) -> None:
        metrics = sample_metrics("http://127.0.0.1:1", None)
        assert check_gate(metrics), "?????? gate ?????fail-closed?"


class TestRollback:
    def test_rollback_writes_state(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(rollout, "_STATE_FILE", tmp_path / "rollout_state.json")
        rc = rollout.rollback()
        assert rc == 0
        payload = json.loads((tmp_path / "rollout_state.json").read_text(encoding="utf-8"))
        assert payload["status"] == "manually_rolled_back"
        assert "instruction" in payload
