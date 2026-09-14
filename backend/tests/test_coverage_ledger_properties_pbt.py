"""Coverage Ledger v2 correctness properties P1/P2."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check" / "check_coverage_ledger.py"
_spec = importlib.util.spec_from_file_location("coverage_ledger_v2_guard", _SCRIPT)
assert _spec and _spec.loader
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

_evidence = st.lists(
    st.text(
        alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd")),
        min_size=1,
        max_size=20,
    ),
    min_size=0,
    max_size=4,
    unique=True,
)
_capability_record = st.one_of(
    _evidence.filter(bool).map(
        lambda value: {"status": "covered", "evidence": value, "exemption": None}
    ),
    st.just({"status": "missing", "evidence": [], "exemption": None}),
    st.just({"status": "unknown", "evidence": [], "exemption": None}),
    st.just({
        "status": "exempt",
        "evidence": [],
        "exemption": {"reason": "not applicable", "approvedBy": "manager"},
    }),
)
_capability_map = st.fixed_dictionaries(
    {cap: _capability_record for cap in guard.CAPABILITIES}
)


def _evaluate(records: dict[str, dict]):
    ledger = {
        "schemaVersion": 2,
        "entries": {"T1": {"capabilities": records}},
    }
    return guard.evaluate_ledger({"T1"}, ledger)


def _outcomes_by_capability(evaluation) -> dict[str, tuple]:
    drifts = {
        cap: tuple(sorted(d.detail for d in evaluation.drifts if d.capability == cap))
        for cap in guard.CAPABILITIES
    }
    return {
        finding.capability: (finding.state, finding.evidence, finding.detail, drifts[finding.capability])
        for finding in evaluation.findings
    }


def test_capability_exemption_does_not_mask_sibling_example() -> None:
    """A capability exemption cannot suppress another explicit missing state.

    **Validates: Requirements 1.2, 1.3, 1.4**
    """
    records = {cap: {"status": "unknown", "evidence": []} for cap in guard.CAPABILITIES}
    records["ai"] = {"status": "exempt", "evidence": [], "exemption": {"reason": "N/A"}}
    records["review"] = {"status": "missing", "evidence": []}

    evaluation = _evaluate(records)

    assert [finding.capability for finding in evaluation.missing] == ["review"]
    assert evaluation.findings[guard.CAPABILITIES.index("ai")].state == guard.STATE_EXEMPT


def test_evidence_and_unknown_examples() -> None:
    """Covered requires evidence, while unknown remains fail-open.

    **Validates: Requirements 1.2, 1.4**
    """
    covered, covered_drifts = guard._evaluate_v2_capability(
        "T1", "persistence", {"status": "covered", "evidence": ["useChecklistPersistence:save"]}
    )
    unsupported, unsupported_drifts = guard._evaluate_v2_capability(
        "T1", "persistence", {"status": "covered", "evidence": []}
    )
    unknown, unknown_drifts = guard._evaluate_v2_capability(
        "T1", "persistence", {"status": "unknown", "evidence": []}
    )

    assert covered.state == guard.STATE_COVERED and not covered_drifts
    assert unsupported.state != guard.STATE_COVERED and unsupported_drifts
    assert unknown.state == guard.STATE_UNKNOWN and not unknown_drifts


@given(records=_capability_map, exempted=st.sampled_from(guard.CAPABILITIES))
def test_property_1_capability_exemption_is_isolated(
    records: dict[str, dict], exempted: str
) -> None:
    """P1: exempting one capability leaves every sibling decision unchanged.

    **Validates: Requirements 1.2, 1.3, 1.4**
    """
    before = _outcomes_by_capability(_evaluate(records))
    changed = {cap: dict(record) for cap, record in records.items()}
    changed[exempted] = {
        "status": "exempt",
        "evidence": [],
        "exemption": {"reason": "generated N/A", "approvedBy": "manager"},
    }
    after = _outcomes_by_capability(_evaluate(changed))

    assert after[exempted][0] == guard.STATE_EXEMPT
    assert {cap: value for cap, value in after.items() if cap != exempted} == {
        cap: value for cap, value in before.items() if cap != exempted
    }


@given(evidence=_evidence)
def test_property_2_covered_iff_evidence_and_unknown_fail_open(
    evidence: list[str],
) -> None:
    """P2: covered is valid iff evidence exists; uncertainty never blocks.

    **Validates: Requirements 1.3, 1.4**
    """
    covered_record = {"status": "covered", "evidence": evidence}
    covered_finding, covered_drifts = guard._evaluate_v2_capability(
        "T1", "persistence", covered_record
    )

    assert (covered_finding.state == guard.STATE_COVERED) is bool(evidence)
    assert bool(covered_drifts) is (not evidence)

    unknown_records = {
        cap: {"status": "unknown", "evidence": []}
        for cap in guard.CAPABILITIES
    }
    unknown_evaluation = _evaluate(unknown_records)

    assert all(
        finding.state == guard.STATE_UNKNOWN
        for finding in unknown_evaluation.findings
    )
    assert unknown_evaluation.drifts == []
    assert unknown_evaluation.should_block is False
