"""Draft Refresh 结果聚合合同（spec formula-hub-integrity-closure 任务 20 第一段 A-1；需求 3.2 / 3.3；ADR-FHIC-08）。

纯函数与数据结构，不连库（全部非 PG）：
- 需求 3.2 状态表 6 行（「幂等命中」由调用方处理、不进 ``derive_outcome``）逐行参数化，含跨范围合计；表结构（6 行、
  outcome / status 各不相同）；0~2 小网格穷举「恰命中 1 行」并与按需求原文独立写的判定逐格对照；事务模式与负计数的拒绝；
- 两个结果类的 ``to_dict``：新键、``affected_count`` 口径、``post_commit_events`` 不序列化、旧构造方式的输出不变；
- 规范化（半分进位、``"1.00"`` 与 ``Decimal("1")``、首尾空白、``None``）与 ``split_unchanged`` 分组（不丢不重、保序）；
- ``DraftRefreshResponse``：7 个 status 都能构造、其他值被拒；Literal 与 ``refresh_outcome`` 的取值表相等。
"""
from __future__ import annotations

import itertools
import json
import typing
import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models.audit_platform_schemas import EventPayload, EventType
from app.schemas.formula_runtime import DraftRefreshResponse
from app.services.draft_refresh_service import RefreshResult
from app.services.formula_management.refresh_outcome import (
    IDEMPOTENT_HIT_STATUS,
    OUTCOME_TABLE,
    OUTCOMES,
    RESPONSE_STATUSES,
    TRANSACTION_MODES,
    Outcome,
    OutcomeTotals,
    ResponseStatus,
    ScopeOutcome,
    derive_outcome,
    effective_count,
    normalize_value,
    split_unchanged,
    summarize,
    values_equal,
)
from app.services.formula_runtime.contracts import CanonicalFormulaTarget, ExecutionResult, FormulaMutation

AON, PARTIAL = "all_or_nothing", "partial_success"
PID = uuid.UUID(int=20)
FAIL = {"scope": "workpaper:D", "error": "adapter error"}


def _event() -> EventPayload:
    return EventPayload(event_type=EventType.REPORTS_UPDATED, project_id=PID, year=2025, extra={})


# ── 需求 3.2 状态表 ──────────────────────────────────────────────────────────────────────────────

TABLE_CASES = [
    pytest.param([ScopeOutcome("report", recomputed=3), ScopeOutcome("workpaper:D", value_changes=1, draft_marked=2)],
                 AON, ("applied", "success"), id="金额变化>0-无失败"),
    pytest.param([ScopeOutcome("report", recomputed=4), ScopeOutcome("note", draft_marked=1)],
                 AON, ("recomputed", "recomputed"), id="金额变化=0-仅重算>0"),
    pytest.param([ScopeOutcome("note", draft_marked=5)], PARTIAL, ("draft_marked", "draft_marked"), id="只有draft标记"),
    pytest.param([ScopeOutcome("workpaper:D"), ScopeOutcome("report")], AON, ("no_effect", "no_effect"), id="三者均0"),
    pytest.param([ScopeOutcome("workpaper:D", failures=[FAIL]), ScopeOutcome("report", recomputed=2)],
                 PARTIAL, ("partial", "partial_success"), id="partial模式-有失败-有效>0"),
    pytest.param([ScopeOutcome("workpaper:D", failures=[FAIL]), ScopeOutcome("report")],
                 PARTIAL, ("failed", "failed"), id="有失败-有效=0"),
    pytest.param([ScopeOutcome("workpaper:D", value_changes=3, failures=[FAIL]), ScopeOutcome("note", draft_marked=1)],
                 AON, ("failed", "failed"), id="all_or_nothing-有失败-有效>0"),
]


@pytest.mark.parametrize(("outcomes", "mode", "expected"), TABLE_CASES)
def test_derive_outcome_follows_requirement_table_row_by_row(outcomes, mode, expected):
    assert derive_outcome(outcomes, mode) == expected


def test_every_table_row_has_a_case_and_vocabularies_match_the_table():
    covered = {case.values[2][0] for case in TABLE_CASES}
    assert covered == set(OUTCOMES)
    assert {rule.outcome: rule.status for rule in OUTCOME_TABLE} == {
        "applied": "success", "recomputed": "recomputed", "draft_marked": "draft_marked",
        "no_effect": "no_effect", "partial": "partial_success", "failed": "failed",
    }
    assert len(OUTCOME_TABLE) == len(set(OUTCOMES)) == len({rule.status for rule in OUTCOME_TABLE}) == 6
    assert RESPONSE_STATUSES == (*(rule.status for rule in OUTCOME_TABLE), IDEMPOTENT_HIT_STATUS)
    assert sorted(typing.get_args(Outcome)) == sorted(OUTCOMES)
    assert sorted(typing.get_args(ResponseStatus)) == sorted(RESPONSE_STATUSES)


def _oracle(v: int, r: int, d: int, f: int, mode: str) -> tuple[str, str]:
    """按需求 3.2 原文另写一遍（不读 OUTCOME_TABLE），供穷举对照。"""
    if f:
        return ("partial", "partial_success") if mode == PARTIAL and v + r + d else ("failed", "failed")
    if v:
        return "applied", "success"
    if r:
        return "recomputed", "recomputed"
    return ("draft_marked", "draft_marked") if d else ("no_effect", "no_effect")


def test_table_rows_are_exclusive_complete_and_match_the_requirement_text():
    for v, r, d, f in itertools.product(range(3), repeat=4):
        totals = OutcomeTotals(v, r, d, f)
        for mode in TRANSACTION_MODES:
            hits = [rule.outcome for rule in OUTCOME_TABLE if rule.when(totals, mode)]
            assert len(hits) == 1, (totals, mode, hits)
            outcomes = [ScopeOutcome("a", value_changes=v, recomputed=r), ScopeOutcome("b", draft_marked=d,
                                                                                         failures=[FAIL] * f)]
            assert derive_outcome(outcomes, mode) == _oracle(v, r, d, f, mode), (totals, mode)


def test_unknown_transaction_mode_is_rejected():
    with pytest.raises(ValueError, match="未知事务模式"):
        derive_outcome([ScopeOutcome("report", value_changes=1)], "best_effort")


def test_negative_count_is_rejected():
    with pytest.raises(ValueError, match="计数不能为负"):
        derive_outcome([ScopeOutcome("report", recomputed=-1)], AON)


def test_effective_count_and_totals_sum_across_scopes():
    outcomes = [ScopeOutcome("workpaper:D", value_changes=1, recomputed=2),
                ScopeOutcome("note", draft_marked=4, failures=[FAIL, FAIL], post_commit_events=[_event()])]
    assert effective_count(outcomes) == 7
    assert summarize(outcomes) == OutcomeTotals(value_changes=1, recomputed=2, draft_marked=4, failures=2)
    assert summarize([]) == OutcomeTotals() and summarize([]).effective == 0


# ── 结果类 to_dict ───────────────────────────────────────────────────────────────────────────────

def test_execution_result_affected_count_is_applied_plus_recomputed_and_events_not_serialized():
    result = ExecutionResult(run_id=uuid.uuid4(), status="success", applied_count=2, recomputed_count=3,
                             draft_marked_count=4, outcome="applied", post_commit_events=[_event(), _event()])
    data = result.to_dict()
    assert (data["affected_count"], data["applied_count"], data["recomputed_count"], data["draft_marked_count"],
            data["outcome"]) == (5, 2, 3, 4, "applied")
    assert "post_commit_events" not in data
    json.dumps(data)  # 只含 JSON 原生类型：事件对象没有混进序列化结果
    assert len(result.post_commit_events) == 2 and "post_commit_events" not in repr(result)


def test_execution_result_legacy_construction_serializes_as_before():
    data = ExecutionResult(run_id=uuid.uuid4(), status="rolled_back", restored_count=3).to_dict()
    assert (data["affected_count"], data["applied_count"], data["restored_count"]) == (0, 0, 3)
    legacy = ExecutionResult(run_id=uuid.uuid4(), status="success", applied_count=7).to_dict()
    assert (legacy["affected_count"], legacy["outcome"], legacy["recomputed_count"], legacy["draft_marked_count"]) == (
        7, None, 0, 0)


def test_refresh_result_serializes_new_counts_and_events_not_serialized():
    result = RefreshResult(tb_snapshot_hash="h", scope="report", status="success", affected_count=5, applied_count=2,
                           recomputed_count=3, draft_marked_count=4, outcome="applied", post_commit_events=[_event()])
    data = result.to_dict()
    assert (data["affected_count"], data["applied_count"], data["recomputed_count"], data["draft_marked_count"],
            data["outcome"]) == (5, 2, 3, 4, "applied")
    assert data["affected_count"] == data["applied_count"] + data["recomputed_count"]
    assert "post_commit_events" not in data
    json.dumps(data)


def test_refresh_result_legacy_construction_keeps_stored_affected_count():
    """旧调用方只传 ``affected_count``（现行 ``refresh()`` 赋的是 Draft 标记数）：``to_dict`` 原样输出存储值、不重算，
    新键取默认值 —— 本段不改 ``refresh()`` 行为；改赋值（标记数进 ``draft_marked_count``）属第一段 A-2。"""
    data = RefreshResult(tb_snapshot_hash="h", scope="workpaper:D", status="success", affected_count=4).to_dict()
    assert (data["affected_count"], data["applied_count"], data["recomputed_count"], data["draft_marked_count"],
            data["outcome"]) == (4, 0, 0, 0, None)


def test_execution_result_status_literal_covers_every_derived_status():
    hints = typing.get_type_hints(ExecutionResult, localns={"EventPayload": EventPayload})
    allowed = set(typing.get_args(hints["status"]))
    assert set(RESPONSE_STATUSES) <= allowed
    assert {"rolled_back", "conflict"} <= allowed


# ── 规范化与 split_unchanged ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(("raw", "expected"), [
    (Decimal("0.005"), Decimal("0.01")), ("0.005", Decimal("0.01")), (0.005, Decimal("0.01")),
    (1.005, Decimal("1.01")), (Decimal("-0.005"), Decimal("-0.01")), (Decimal("0.004"), Decimal("0.00")),
    (" 12.345 ", Decimal("12.35")), (7, Decimal("7.00")),
])
def test_numbers_quantize_half_up_to_cents(raw, expected):
    got = normalize_value(raw)
    assert isinstance(got, Decimal) and got == expected and got.as_tuple().exponent == -2


@pytest.mark.parametrize(("before", "after", "equal"), [
    ("1.00", Decimal("1"), True),
    (" 1.00 ", 1, True),
    ("1234.5600", "1234.56", True),
    (Decimal("1.004"), Decimal("1.00"), True),
    (Decimal("1.005"), Decimal("1.00"), False),
    ("  应收账款 ", "应收账款", True),
    ("应收账款", "应付账款", False),
    (None, None, True),
    (None, "", True),
    (None, "   ", True),
    (None, 0, False),
    (None, "0", False),
    ("", Decimal("0"), False),
    (True, 1, False),
    ({"v": "1.00"}, {"v": "1.00"}, True),
    ({"v": "1.00"}, {"v": "1"}, False),
    (Decimal("1E+30"), "1000000000000000000000000000000", True),
    (Decimal("sNaN"), Decimal("sNaN"), True),
])
def test_values_equal_after_normalization(before, after, equal):
    assert values_equal(before, after) is equal
    assert values_equal(after, before) is equal


def _mutation(addr: str, before, after) -> FormulaMutation:
    target = CanonicalFormulaTarget(domain="report", project_id=PID, year=2025, addr_id=addr, locator={"row": addr})
    return FormulaMutation(target=target, before_value=before, after_value=after)


def test_split_unchanged_groups_by_normalized_equality_without_loss_or_duplication():
    items = [
        _mutation("a", "1234.5600", "1234.56"),
        _mutation("b", "10.00", "10.01"),
        _mutation("c", None, ""),
        _mutation("d", None, "0"),
        _mutation("e", " 备注 ", "备注"),
        _mutation("f", Decimal("5"), 5.0),
        _mutation("g", "0.004", None),
    ]
    to_write, unchanged = split_unchanged(items)
    assert [m.target.addr_id for m in to_write] == ["b", "d", "g"]
    assert [m.target.addr_id for m in unchanged] == ["a", "c", "e", "f"]
    together = to_write + unchanged
    assert len(together) == len(items) and {id(m) for m in together} == {id(m) for m in items}


def test_split_unchanged_accepts_custom_accessors_and_empty_input():
    rows = [{"before": "1", "after": "1.00"}, {"before": "1", "after": "2"}]
    to_write, unchanged = split_unchanged(rows, before_of=lambda r: r["before"], after_of=lambda r: r["after"])
    assert to_write == [rows[1]] and unchanged == [rows[0]]
    assert split_unchanged([]) == ([], [])


# ── DraftRefreshResponse ────────────────────────────────────────────────────────────────────────

def _response(**overrides) -> DraftRefreshResponse:
    return DraftRefreshResponse(**{"status": "success", "run_id": uuid.uuid4(), "transaction_mode": AON, **overrides})


@pytest.mark.parametrize("status", RESPONSE_STATUSES)
def test_response_accepts_each_of_the_seven_statuses(status):
    assert _response(status=status).status == status


@pytest.mark.parametrize("status", ["applied", "blocked", "rolled_back"])
def test_response_rejects_any_other_status(status):
    with pytest.raises(ValidationError):
        _response(status=status)


def test_response_literals_equal_refresh_outcome_vocabularies():
    fields = DraftRefreshResponse.model_fields
    statuses = typing.get_args(fields["status"].annotation)
    assert len(statuses) == 7 and sorted(statuses) == sorted(RESPONSE_STATUSES)
    outcome_literal = [arg for arg in typing.get_args(fields["outcome"].annotation) if arg is not type(None)]
    assert len(outcome_literal) == 1 and sorted(typing.get_args(outcome_literal[0])) == sorted(OUTCOMES)


def test_response_new_fields_default_and_round_trip():
    legacy = _response(affected_count=3, applied_count=3)
    assert (legacy.outcome, legacy.recomputed_count, legacy.draft_marked_count) == (None, 0, 0)
    full = _response(status="recomputed", outcome="recomputed", affected_count=4, recomputed_count=4,
                     draft_marked_count=2)
    restored = DraftRefreshResponse.model_validate_json(full.model_dump_json())
    assert (restored.status, restored.outcome, restored.recomputed_count, restored.draft_marked_count) == (
        "recomputed", "recomputed", 4, 2)


def test_response_rejects_status_name_as_outcome():
    with pytest.raises(ValidationError):
        _response(outcome="success")
