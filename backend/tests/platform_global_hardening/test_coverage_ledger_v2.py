"""Targeted tests for workpaper-maintainability-convergence task 1.3."""
from __future__ import annotations

import importlib.util
import io
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts/check/check_coverage_ledger.py"
_SPEC = importlib.util.spec_from_file_location("coverage_ledger_guard_v2", _SCRIPT)
assert _SPEC and _SPEC.loader
guard = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(guard)


def _cap(status: str, evidence=None, exemption=None) -> dict:
    value = {"status": status, "evidence": evidence or [], "exemption": exemption}
    return value


def _entry(**overrides: dict) -> dict:
    capabilities = {
        capability: _cap("unknown") for capability in guard.CAPABILITIES
    }
    capabilities.update(overrides)
    return {"capabilities": capabilities}


def _evaluate(entry: dict):
    return guard.evaluate_ledger(
        {"D2"},
        {"schemaVersion": 2, "entries": {"D2": entry}},
    )


def _finding(evaluation, capability: str):
    return next(
        row for row in evaluation.findings if row.capability == capability
    )


def test_v2_distinguishes_runtime_legacy_missing_and_unknown() -> None:
    evaluation = _evaluate(_entry(
        displayPrefs=_cap("covered", ["GtWpRenderer:Runtime_Boundary"]),
        review=_cap("covered", ["GtD2:useWorkpaperReviewProvide"]),
        version=_cap("missing"),
        ai=_cap("unknown"),
    ))

    assert _finding(evaluation, "displayPrefs").state == guard.STATE_RUNTIME_BOUNDARY
    assert _finding(evaluation, "review").state == guard.STATE_LEGACY_PROVIDER
    assert _finding(evaluation, "version").state == guard.STATE_MISSING
    assert _finding(evaluation, "ai").state == guard.STATE_UNKNOWN
    assert len(evaluation.legacy_providers) == 1
    assert evaluation.should_block is True
def test_strict_predicate_ignores_unknown_legacy_and_exempt() -> None:
    evaluation = _evaluate(_entry(
        displayPrefs=_cap("covered", ["GtWpRenderer:Runtime_Boundary"]),
        review=_cap("covered", ["GtD2:useWorkpaperReviewProvide"]),
        ai=_cap("unknown"),
        agingConfig=_cap(
            "exempt",
            exemption={"reason": "该底稿无账龄维度", "approvedBy": "manager"},
        ),
    ))

    assert evaluation.missing == []
    assert evaluation.drifts == []
    assert evaluation.should_block is False


def test_ledger_drift_blocks_invalid_evidence_contract() -> None:
    evaluation = _evaluate(_entry(
        displayPrefs=_cap("covered"),
        importExport=_cap("covered", ["GtWpRenderer:Runtime_Boundary"]),
        acnr=_cap("unknown", ["GtIndexChip"]),
        persistence=_cap("exempt", exemption=None),
    ))

    details = {drift.detail for drift in evaluation.drifts}
    assert "covered 缺少可复现 evidence" in details
    assert "该能力不由 Runtime Boundary 自动提供" in details
    assert "unknown 状态不应携带覆盖 evidence" in details
    assert "exempt 缺少能力级 exemption.reason" in details
    assert evaluation.should_block is True


def test_v2_structure_drift_blocks_entry_exemption_unknown_capability_and_stale_exemption() -> None:
    entry = _entry(
        ai=_cap(
            "unknown",
            exemption={"reason": "stale exemption", "approvedBy": "manager"},
        ),
    )
    entry["exemption"] = {"reason": "blanket exemption"}
    entry["capabilities"]["obsoleteCapability"] = _cap("unknown")

    evaluation = _evaluate(entry)

    drift_details = {
        (drift.capability, drift.detail) for drift in evaluation.drifts
    }
    assert ("*", "v2 Ledger 禁止 entry 级 exemption") in drift_details
    assert (
        "obsoleteCapability",
        "v2 Ledger 包含未知 capability",
    ) in drift_details
    assert ("ai", "unknown 状态不允许携带 exemption") in drift_details
    assert evaluation.should_block is True


def test_report_outputs_full_coverage_and_all_key_categories() -> None:
    evaluation = _evaluate(_entry(
        displayPrefs=_cap("covered", ["GtWpRenderer:Runtime_Boundary"]),
        review=_cap("covered", ["GtD2:useWorkpaperReviewProvide"]),
        importExport=_cap("covered", ["GtD2:useD2ImportExport"]),
        persistence=_cap("missing"),
        ai=_cap("unknown"),
        agingConfig=_cap(
            "exempt",
            exemption={"reason": "无账龄", "approvedBy": "manager"},
        ),
    ))
    output = io.StringIO()

    guard.print_report(evaluation, stream=output)

    text = output.getvalue()
    assert "全量能力槽位 8" in text
    assert "全量覆盖率: 37.50% (3/8)" in text
    assert "Runtime Boundary=1" in text
    assert "Legacy Provider=1" in text
    assert "明确缺失=1" in text
    assert "不确定=3" in text
