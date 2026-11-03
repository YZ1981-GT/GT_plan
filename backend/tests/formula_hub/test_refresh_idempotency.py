"""Draft Refresh 幂等判定纯函数（spec formula-hub-integrity-closure 任务 20 第一段 A-2c-1；ADR-FHIC-08「幂等」）。

不连库（全部非 PG）；prior 用未入会话的 ``DraftRefreshAudit`` 实例与 ``SimpleNamespace``：
- 计划指纹：确定性（同输入同值、scopes 全排列 / 重复同值）、敏感性（逐项改一个组成项 ⇒ 值变，参数化覆盖全部 10 项，
  另核参数化与「函数签名 + ``ReportBasis`` 字段」一一对应）、不勾选 report 时报表四项不进指纹、勾选 report 而报表四项
  缺失或单项为 None ⇒ ValueError；
- 行哈希：规范化（尾零、``-0``、int / float 与 Decimal、定点无指数、不按精度舍入、None、枚举、bool）、行序无关、
  字段序有关、重复行计数、不支持的类型；
- 有效键（去首尾空白、恰 64 / 65 字符边界、中文按字符计、无键回落 plan_fp）、判定表全部情形（含 409 异常）、
  最近一条、写入键、命中结果与预设应用回放。
"""
from __future__ import annotations

import dataclasses
import hashlib
import inspect
import itertools
import re
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum, IntEnum
from types import SimpleNamespace

import pytest

from app.models.workpaper_models import DraftRefreshAudit
from app.services.formula_management.refresh_idempotency import (
    DETAIL_BASE_KEY,
    DETAIL_FP_KEY,
    HIT_OUTCOMES,
    IN_PROGRESS_ERROR_CODE,
    KEY_MAX_LENGTH,
    RefreshInProgress,
    ReportBasis,
    decide,
    effective_key,
    hit_preset_application,
    hit_result,
    latest,
    plan_fp,
    rows_hash,
    write_key,
)
from app.services.formula_management.refresh_outcome import IDEMPOTENT_HIT_STATUS, OUTCOMES
from app.services.formula_management.refresh_report_scope import ROLLBACK_UNAVAILABLE_WARNING
from app.services.formula_runtime.contracts import ExecutionResult

HEX64 = re.compile(r"[0-9a-f]{64}")
PID = uuid.UUID(int=2025)
T0 = datetime(2026, 10, 28, 8, 0, tzinfo=timezone.utc)
FP = "f" * 64
BASIS = ReportBasis(tb_rows_hash="a" * 64, definitions_hash="b" * 64, calc_version=2, stale_count=3)
BASE = {"scopes": ["report", "workpaper:D"], "transaction_mode": "all_or_nothing", "confirm_overwrite": False,
        "tb_snapshot_hash": "c" * 64, "formula_revision": "d" * 64, "preset_revision": "e" * 64, "report": BASIS}
NO_REPORT = {**BASE, "scopes": ["workpaper:D", "note"]}
#: 按 ADR-FHIC-08 原文独立写的命中集合（与模块常量对照）
HIT_EXPECTED = ("applied", "recomputed", "draft_marked", "no_effect")


def _audit(result_status, detail, *, run_id=None, at=None):
    """未入会话的审计实例（只设判定读取的字段与几个非空列）。"""
    return DraftRefreshAudit(id=run_id or uuid.uuid4(), project_id=PID, year=2025, operator_id=uuid.UUID(int=1),
                             operator_role="admin", scope="report", tb_snapshot_hash="0" * 64, affected_count=0,
                             result_status=result_status, detail=detail, operated_at=at)


def _ns(result_status, detail, *, run_id=None, at=None):
    return SimpleNamespace(id=run_id or uuid.uuid4(), result_status=result_status, detail=detail, operated_at=at)


MAKERS = [pytest.param(_audit, id="DraftRefreshAudit"), pytest.param(_ns, id="SimpleNamespace")]


# ── 计划指纹 ──────────────────────────────────────────────────────────────────────────────────────

def test_plan_fp_is_deterministic_hex():
    first = plan_fp(**BASE)
    assert HEX64.fullmatch(first)
    assert plan_fp(**dict(BASE)) == first
    assert plan_fp(**{**BASE, "report": ReportBasis(**dataclasses.asdict(BASIS))}) == first


def test_plan_fp_ignores_scope_order_and_duplicates():
    scopes = ["report", "workpaper:D", "note", "adjudication"]
    expected = plan_fp(**{**BASE, "scopes": scopes})
    for perm in itertools.permutations(scopes):
        assert plan_fp(**{**BASE, "scopes": list(perm)}) == expected
        assert plan_fp(**{**BASE, "scopes": (*perm, perm[0], perm[-1], perm[1])}) == expected
    assert plan_fp(**{**BASE, "scopes": iter(scopes)}) == expected


CHANGES = [
    pytest.param({"scopes": ["report", "workpaper:D", "note"]}, id="scopes"),
    pytest.param({"transaction_mode": "partial_success"}, id="transaction_mode"),
    pytest.param({"confirm_overwrite": True}, id="confirm_overwrite"),
    pytest.param({"tb_snapshot_hash": FP}, id="tb_snapshot_hash"),
    pytest.param({"formula_revision": FP}, id="formula_revision"),
    pytest.param({"preset_revision": FP}, id="preset_revision"),
    pytest.param({"report": dataclasses.replace(BASIS, tb_rows_hash=FP)}, id="report.tb_rows_hash"),
    pytest.param({"report": dataclasses.replace(BASIS, definitions_hash=FP)}, id="report.definitions_hash"),
    pytest.param({"report": dataclasses.replace(BASIS, calc_version=3)}, id="report.calc_version"),
    pytest.param({"report": dataclasses.replace(BASIS, stale_count=0)}, id="report.stale_count"),
]


@pytest.mark.parametrize("change", CHANGES)
def test_plan_fp_changes_with_each_component(change):
    assert plan_fp(**{**BASE, **change}) != plan_fp(**BASE)


def test_plan_fp_sensitivity_cases_cover_every_component():
    """参数化与「函数签名（report 除外）+ ReportBasis 四个字段」一一对应：新增组成项而漏写敏感性用例即红。"""
    components = {name for name in inspect.signature(plan_fp).parameters if name != "report"}
    components |= {f"report.{field.name}" for field in dataclasses.fields(ReportBasis)}
    assert {param.id for param in CHANGES} == components
    assert len(components) == 10


@pytest.mark.parametrize("report", [
    pytest.param(None, id="未给"),
    pytest.param(BASIS, id="给了"),
    *[pytest.param(dataclasses.replace(BASIS, **{field.name: value}), id=f"改{field.name}")
      for field, value in zip(dataclasses.fields(ReportBasis), (FP, FP, 3, 0))],
    pytest.param(dataclasses.replace(BASIS, stale_count=None), id="单项为None"),
])
def test_plan_fp_ignores_report_basis_without_report_scope(report):
    assert plan_fp(**{**NO_REPORT, "report": report}) == plan_fp(**{**NO_REPORT, "report": None})


@pytest.mark.parametrize("report", [
    pytest.param(None, id="未给报表四项"),
    *[pytest.param(dataclasses.replace(BASIS, **{field.name: None}), id=f"{field.name}为None")
      for field in dataclasses.fields(ReportBasis)],
])
def test_plan_fp_report_scope_requires_report_basis(report):
    with pytest.raises(ValueError, match="报表四项"):
        plan_fp(**{**BASE, "report": report})


# ── 行哈希 ────────────────────────────────────────────────────────────────────────────────────────

class Kind(str, Enum):
    BS = "balance_sheet"


class Level(IntEnum):
    TWO = 2


@pytest.mark.parametrize(("number", "text"), [
    (Decimal("1.10"), "1.1"), (Decimal("1.00"), "1"), (1, "1"), (Decimal("120"), "120"), (Decimal("1E+2"), "100"),
    (Decimal("-12.3400"), "-12.34"), (Decimal("1.23E-5"), "0.0000123"), (Decimal("-0"), "0"),
    (Decimal("-0.00"), "0"), (Decimal("0E+3"), "0"), (-0.0, "0"), (0.1, "0.1"), (1.5, "1.5"), (Level.TWO, "2"),
])
def test_rows_hash_numbers_become_trimmed_fixed_point_strings(number, text):
    """字符串原样参与 ⇒ 数字行与「它的规范串」字符串行同值，借此钉住规范串本身（定点、去尾零、-0 ⇒ 0）。"""
    assert rows_hash([("1001", number)]) == rows_hash([("1001", text)])


@pytest.mark.parametrize(("left", "right"), [
    pytest.param(Decimal("1.10"), Decimal("1.1"), id="尾零"),
    pytest.param(1, Decimal("1.00"), id="int与Decimal"),
    pytest.param(1.25, Decimal("1.250"), id="float与Decimal"),
    pytest.param(Decimal("-0"), 0, id="负零"),
    pytest.param(-0.0, Decimal("0.000"), id="float负零"),
    pytest.param(Kind.BS, "balance_sheet", id="枚举取value"),
    pytest.param(Level.TWO, Decimal("2.00"), id="整数枚举取value再规范化"),
])
def test_rows_hash_equal_after_normalization(left, right):
    assert rows_hash([("1001", left, None)]) == rows_hash([("1001", right, None)])


@pytest.mark.parametrize(("left", "right"), [
    pytest.param([(None,)], [("null",)], id="None不是字符串null"),
    pytest.param([(None,)], [("",)], id="None不是空串"),
    pytest.param([(None,)], [(0,)], id="None不是0"),
    pytest.param([(True,)], [(1,)], id="True不是1"),
    pytest.param([(False,)], [(0,)], id="False不是0"),
    pytest.param([(Decimal("1.1"),)], [(Decimal("1.2"),)], id="值不同"),
    pytest.param([(Decimal("1.0000000000000000000000000000001"),)], [(1,)], id="不按上下文精度舍入"),
    pytest.param([("1001", "2")], [("2", "1001")], id="字段序有关"),
    pytest.param([("1001",)], [("1001",), ("1001",)], id="重复行计数"),
    pytest.param([("1001", None)], [("1001",)], id="字段数不同"),
])
def test_rows_hash_distinguishes(left, right):
    assert rows_hash(left) != rows_hash(right)


def test_rows_hash_ignores_row_order():
    """全排列同值；同一列里 None 与数字混排也能排序（按每行的规范编码排，不直接比较字段）。"""
    rows = [("1001", Decimal("10.00"), None, Decimal("0")), ("1002", None, Decimal("-3.5"), 1),
            ("1001", Decimal("9"), None, None), ("6001", Decimal("1E+2"), Decimal("100"), Decimal("-0"))]
    expected = rows_hash(rows)
    assert HEX64.fullmatch(expected)
    for perm in itertools.permutations(rows):
        assert rows_hash(perm) == expected
    assert rows_hash([list(row) for row in rows]) == expected
    assert rows_hash(iter(rows)) == expected


def test_rows_hash_of_no_rows_is_hash_of_empty_array():
    assert rows_hash([]) == hashlib.sha256(b"[]").hexdigest()


@pytest.mark.parametrize("value", [uuid.UUID(int=1), T0, b"1001", {"a": 1}])
def test_rows_hash_rejects_unsupported_field_types(value):
    with pytest.raises(TypeError, match="行哈希不支持"):
        rows_hash([("1001", value)])


# ── 有效键 ────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(("request_key", "expected"), [
    pytest.param("abc", "abc", id="请求键"),
    pytest.param("  abc\t\n", "abc", id="去首尾空白"),
    pytest.param("k" * 64, "k" * 64, id="恰64字符原样"),
    pytest.param(" " + "k" * 64 + " ", "k" * 64, id="去空白后恰64字符"),
    pytest.param("键" * 64, "键" * 64, id="64个中文字符按字符计"),
    pytest.param(None, FP, id="None回落plan_fp"),
    pytest.param("", FP, id="空串回落plan_fp"),
    pytest.param(" \t\n", FP, id="全空白回落plan_fp"),
])
def test_effective_key(request_key, expected):
    assert effective_key(request_key, FP) == expected


@pytest.mark.parametrize("request_key", ["k" * 65, "键" * 65, " " + "k" * 65, "x" * 500])
def test_effective_key_hashes_keys_longer_than_64(request_key):
    key = effective_key(request_key, FP)
    assert key == hashlib.sha256(request_key.strip().encode("utf-8")).hexdigest()
    assert HEX64.fullmatch(key) and len(key) == KEY_MAX_LENGTH == 64


# ── 判定 ──────────────────────────────────────────────────────────────────────────────────────────

def test_hit_outcomes_are_the_four_successful_outcomes():
    assert sorted(HIT_OUTCOMES) == sorted(HIT_EXPECTED)
    assert set(OUTCOMES) - set(HIT_OUTCOMES) == {"partial", "failed"}


DECIDE_CASES = [
    pytest.param("rolled_back", {"outcome": "applied"}, "execute", id="rolled_back-即使outcome可命中"),
    *[pytest.param("success", {"outcome": outcome, "applied_count": 1}, "hit", id=f"命中-{outcome}")
      for outcome in HIT_EXPECTED],
    pytest.param("success", {"outcome": "partial", "applied_count": 2}, "execute", id="partial"),
    pytest.param("success", {"outcome": "failed"}, "execute", id="failed"),
    pytest.param("success", {"affected_count": 3, "refreshed_units": ["a"]}, "execute", id="无outcome键-改造前"),
    pytest.param("success", {"outcome": None}, "execute", id="outcome为None"),
    pytest.param("success", None, "execute", id="detail为None"),
    pytest.param("success", ["applied"], "execute", id="detail为list"),
    pytest.param("success", "applied", "execute", id="detail为str"),
    pytest.param("blocked", {}, "execute", id="blocked-无outcome"),
]


@pytest.mark.parametrize("make", MAKERS)
@pytest.mark.parametrize(("status", "detail", "expected"), DECIDE_CASES)
def test_decide_table(make, status, detail, expected):
    assert decide(make(status, detail)) == expected


def test_decide_without_prior_executes():
    assert decide(None) == "execute"


@pytest.mark.parametrize("make", MAKERS)
def test_decide_executing_raises_in_progress(make):
    run_id = uuid.uuid4()
    with pytest.raises(RefreshInProgress) as caught:
        decide(make("executing", {"outcome": "applied"}, run_id=run_id))
    exc = caught.value
    assert (exc.status_code, exc.code, IN_PROGRESS_ERROR_CODE) == (409, "DRAFT_REFRESH_IN_PROGRESS", exc.code)
    assert str(run_id) in exc.message and str(exc) == exc.message
    assert re.search(r"[\u4e00-\u9fff]", exc.message)
    assert exc.to_detail() == {"error_code": "DRAFT_REFRESH_IN_PROGRESS", "message": exc.message,
                               "run_id": str(run_id)}


# ── 最近一条 ──────────────────────────────────────────────────────────────────────────────────────

def _rec(at, n):
    return _ns("success", {}, run_id=uuid.UUID(int=n), at=at)


def test_latest_picks_newest_in_any_input_order():
    newest = _rec(T0 + timedelta(minutes=5), 1)
    records = [_rec(T0, 9), newest, _rec(None, 99), _rec(T0 + timedelta(minutes=1), 50)]
    for perm in itertools.permutations(records):
        assert latest(perm) is newest


def test_latest_breaks_operated_at_ties_by_id_desc():
    records = [_rec(T0, 3), _rec(T0, 7), _rec(T0, 5)]
    for perm in itertools.permutations(records):
        assert latest(perm) is records[1]


def test_latest_puts_missing_operated_at_last():
    timed = _rec(T0 - timedelta(days=365), 1)
    untimed = [_audit("success", {}, run_id=uuid.UUID(int=1000)), _audit("success", {}, run_id=uuid.UUID(int=2000))]
    for perm in itertools.permutations([timed, *untimed]):
        assert latest(perm) is timed
    assert latest(untimed) is untimed[1] and latest(reversed(untimed)) is untimed[1]


def test_latest_of_nothing_is_none():
    assert latest([]) is None and latest(iter(())) is None


# ── 写入键 ────────────────────────────────────────────────────────────────────────────────────────

EFF = "k" * 64


def test_write_key_unoccupied_is_effective_key():
    assert write_key(EFF, 0) == EFF and write_key("abc", 0) == "abc"


def test_write_key_occupied_gets_distinct_64_hex():
    """第 n 次重新执行（已有 n 条同族记录）⇒ sha256(f"{有效键}#{n}")：64 位、与有效键及其他 n 互不相同。"""
    keys = [write_key(EFF, n) for n in range(1, 9)]
    for n, key in enumerate(keys, 1):
        assert HEX64.fullmatch(key) and key == hashlib.sha256(f"{EFF}#{n}".encode()).hexdigest()
    assert len({EFF, *keys}) == 1 + len(keys)
    assert write_key("abc", 1) != write_key("abd", 1)


def test_write_key_rejects_negative_count():
    with pytest.raises(ValueError, match="不能为负"):
        write_key(EFF, -1)


# ── 命中结果 ──────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("make", MAKERS)
def test_hit_result_replays_first_run(make):
    run_id = uuid.uuid4()
    prior = make("success", {"outcome": "applied", "applied_count": 4, "recomputed_count": 2, "draft_marked_count": 3,
                             "affected_count": 6, "scopes": ["workpaper:D", "note"]}, run_id=run_id)
    result = hit_result(prior)
    assert isinstance(result, ExecutionResult)
    assert (result.run_id, result.status, result.outcome) == (run_id, IDEMPOTENT_HIT_STATUS, "applied")
    assert (result.applied_count, result.recomputed_count, result.draft_marked_count) == (4, 2, 3)
    assert result.failures == [] and result.post_commit_events == []
    assert result.rollback_available is True and result.warnings == []
    body = result.to_dict()
    assert (body["status"], body["idempotent"], body["run_id"]) == ("idempotent_hit", True, str(run_id))
    assert (body["affected_count"], body["failed_count"], body["restored_count"], body["skipped_count"]) == (6, 0, 0, 0)


@pytest.mark.parametrize(("detail", "rollback_available", "warnings"), [
    pytest.param({"scopes": ["report"]}, False, [ROLLBACK_UNAVAILABLE_WARNING], id="只有report"),
    pytest.param({"scopes": ["workpaper:D", "report"]}, False, [ROLLBACK_UNAVAILABLE_WARNING], id="含report"),
    pytest.param({"scopes": ["workpaper:D", "note"]}, True, [], id="不含report"),
    pytest.param({"scopes": []}, True, [], id="scopes为空"),
    pytest.param({"scopes": None}, True, [], id="scopes为None"),
    pytest.param({}, True, [], id="缺scopes键"),
])
def test_hit_result_rollback_follows_first_run_scopes(detail, rollback_available, warnings):
    result = hit_result(_audit("success", {"outcome": "recomputed", "recomputed_count": 5, **detail}))
    assert result.rollback_available is rollback_available and result.warnings == warnings
    assert result.to_dict()["rollback_available"] is rollback_available


@pytest.mark.parametrize("make", MAKERS)
def test_hit_result_missing_counts_are_zero(make):
    result = hit_result(make("success", {"outcome": "no_effect"}))
    assert (result.outcome, result.applied_count, result.recomputed_count, result.draft_marked_count) == (
        "no_effect", 0, 0, 0)
    assert (result.to_dict()["affected_count"], result.to_dict()["idempotent"]) == (0, True)


@pytest.mark.parametrize("make", MAKERS)
def test_hit_preset_application(make):
    application = {"page_keys": ["report:balance_sheet"], "applied_units": 2}
    assert hit_preset_application(make("success", {"outcome": "applied", "preset_application": application})) == (
        application)
    for value in (None, [], "report:*", 3):
        assert hit_preset_application(make("success", {"outcome": "applied", "preset_application": value})) is None
    assert hit_preset_application(make("success", {"outcome": "applied"})) is None
    assert hit_preset_application(make("success", None)) is None


def test_detail_key_names():
    assert (DETAIL_BASE_KEY, DETAIL_FP_KEY, KEY_MAX_LENGTH) == ("idempotency_base", "plan_fp", 64)
