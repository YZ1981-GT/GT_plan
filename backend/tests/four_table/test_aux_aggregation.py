"""四表库共享件 `aux_aggregation`：提升零回归守卫.

`pick_aux_type` 原在 `_f1_import_export`（平台唯一正确实现，G7 直接 import 它），
本 spec 提升为共享件后必须**语义逐字不变**。

spec: .kiro/specs/k1-extraction-chain-and-note-alignment/
Requirements 11.5 / Property 12
"""
from __future__ import annotations

import sqlalchemy as sa

from app.services.four_table.aux_aggregation import (
    AUX_TYPE_PREFERRED_KEYWORDS,
    AuxEntry,
    _prefix_predicate,
    pick_aux_type,
)


def test_reexport_from_f1_is_same_object():
    """F1 / G7 的既有 import 路径必须拿到**同一个函数对象**（薄壳 re-export）。"""
    from app.routers.wp_render_strategies._f1_import_export import (
        _AUX_TYPE_PREFERRED_KEYWORDS as f1_kw,
        pick_aux_type as f1_pick,
    )

    assert f1_pick is pick_aux_type
    assert f1_kw is AUX_TYPE_PREFERRED_KEYWORDS


def test_empty_candidates_return_none():
    assert pick_aux_type([]) is None


def test_preferred_keyword_wins_over_larger_amount():
    """含往来单位关键词的维度优先，即便金额更小（提升前后同款行为）。"""
    got = pick_aux_type([("成本中心", 9999, 1e9), ("客户", 3, 1.0)])
    assert got == "客户"


def test_among_preferred_larger_amount_wins():
    got = pick_aux_type([("客户", 10, 100.0), ("职员", 10, 200.0)])
    assert got == "职员"


def test_amount_negative_uses_absolute():
    got = pick_aux_type([("客户", 1, -500.0), ("供应商", 1, 100.0)])
    assert got == "客户"


def test_falls_back_to_all_when_no_preferred():
    got = pick_aux_type([("成本中心", 1, 10.0), ("保证金类别", 1, 50.0)])
    assert got == "保证金类别"


def test_row_count_breaks_amount_tie():
    got = pick_aux_type([("客户", 2, 100.0), ("职员", 7, 100.0)])
    assert got == "职员"


def test_none_and_blank_types_tolerated():
    assert pick_aux_type([(None, 0, 0.0)]) == ""
    assert pick_aux_type([("", None, None)]) == ""


def test_preferred_keywords_cover_real_aux_types_seen_in_db():
    """实测 1221 的 aux_type：客户 / 成本中心 / 保证金类别 / 职员 / 经营类往来款。
    其中「客户」「职员」「经营类往来款」应被识别为往来单位维度。"""
    preferred = [
        t for t in ("客户", "成本中心", "保证金类别", "职员", "经营类往来款")
        if any(kw in t for kw in AUX_TYPE_PREFERRED_KEYWORDS)
    ]
    assert set(preferred) == {"客户", "职员", "经营类往来款"}


def test_prefix_predicate_empty_is_false():
    assert str(_prefix_predicate(sa.column("account_code"), [])) == "false"
    assert str(_prefix_predicate(sa.column("account_code"), ["  ", ""])) == "false"


def test_prefix_predicate_builds_like_or():
    sql = str(_prefix_predicate(sa.column("account_code"), ["1221", "1231.03"]))
    assert sql.count("LIKE") == 2
    assert " OR " in sql


def test_aux_entry_is_positionally_compatible_with_f1_builder():
    """`AuxEntry` 顺序必须与 F1 的位置化元组一致（F1 builder 按位置解构）。"""
    e = AuxEntry("甲", 1.0, 2.0, 3.0, 4.0)
    assert (e[0], e[1], e[2], e[3], e[4]) == ("甲", 1.0, 2.0, 3.0, 4.0)
    assert e._fields == ("aux_name", "opening", "debit", "credit", "closing")


# ─────────────────────────────────────────────────────────────────────────────
# Task 3 / four-table-extraction-entry-completion
# fail-open 治理：`aggregate_aux_by_name_ex` 的 reason 分支 + ERROR 日志 (Property 6)
# 以及旧薄壳 `aggregate_aux_by_name` 逐字段零回归守卫（4 消费者不受影响）。
# Requirements 5.1, 5.2 / Property 6
# ─────────────────────────────────────────────────────────────────────────────
import asyncio
import logging
from types import SimpleNamespace

import pytest

from app.services.four_table.aux_aggregation import (
    AuxAggregationResult,
    aggregate_aux_by_name,
    aggregate_aux_by_name_ex,
)


def _run(coro):
    return asyncio.run(coro)


class _Rows:
    def __init__(self, rows):
        self._rows = list(rows)

    def fetchall(self):
        return list(self._rows)


class _FakeAggSession:
    """驱动 `_ex` 的两跳查询：第 1 跳 GROUP BY aux_type 返回维度候选，
    第 2 跳 GROUP BY aux_name 返回归集行。按 execute 调用序区分（第 1 次=维度，
    其后=归集），或在 ``raise_at`` 指定的第几跳抛异常（模拟接线错误被 fail-open 吞）。
    """

    def __init__(self, *, aux_type_rows=None, aux_name_rows=None, raise_at=None):
        self.aux_type_rows = aux_type_rows or []
        self.aux_name_rows = aux_name_rows or []
        self.raise_at = raise_at
        self._calls = 0
        self.rolled_back = False

    async def execute(self, stmt, params=None):
        self._calls += 1
        if self.raise_at is not None and self._calls == self.raise_at:
            raise RuntimeError("aux boom（模拟列名拼错/传错 db 形态被 fail-open 吞）")
        if self._calls == 1:
            return _Rows(self.aux_type_rows)
        return _Rows(self.aux_name_rows)

    async def rollback(self):
        self.rolled_back = True


@pytest.fixture(autouse=True)
def _stub_active_filter(monkeypatch):
    """跳过真实 `get_active_filter`（涉及真库/ORM 表达式），返回 sentinel。
    `_ex` 在函数体内 `from app.services.dataset_query import get_active_filter`，
    故必须打 `dataset_query` 模块上的符号。"""
    import app.services.dataset_query as dq

    async def _fake_active_filter(db, table, project_id, year, **kw):
        return True

    monkeypatch.setattr(dq, "get_active_filter", _fake_active_filter, raising=True)


def test_ex_returns_named_result_type():
    """返回值是 `AuxAggregationResult`，字段顺序与命名固定（下游按名/位置消费）。"""
    res = _run(aggregate_aux_by_name_ex(_FakeAggSession(), "p", 2025, []))
    assert isinstance(res, AuxAggregationResult)
    assert res._fields == ("entries", "aux_type", "total_units", "reason")


# ── 四个 reason 分支 ─────────────────────────────────────────────────────────

def test_reason_no_prefixes_when_empty_prefixes():
    """无科目前缀（报表映射未解析出）→ reason='no_prefixes'，不查库、不记 ERROR。"""
    session = _FakeAggSession()
    res = _run(aggregate_aux_by_name_ex(session, "p", 2025, []))
    assert res == AuxAggregationResult([], None, 0, "no_prefixes")
    assert session._calls == 0  # 短路，未查库


def test_reason_no_prefixes_when_all_blank():
    res = _run(aggregate_aux_by_name_ex(_FakeAggSession(), "p", 2025, ["  ", ""]))
    assert res.reason == "no_prefixes"


def test_reason_no_aux_type_when_no_dimension_candidate():
    """命中科目但无任何 aux 维度候选 → reason='no_aux_type'。"""
    session = _FakeAggSession(aux_type_rows=[])
    res = _run(aggregate_aux_by_name_ex(session, "p", 2025, ["1221"]))
    assert res == AuxAggregationResult([], None, 0, "no_aux_type")


def test_reason_no_rows_when_dimension_locked_but_zero_rows():
    """锁到了 aux_type 但聚合 0 行 → reason='no_rows'（真·无数据，正常空）。
    aux_type 非 None（与旧三元组一致），entries 为空。"""
    session = _FakeAggSession(
        aux_type_rows=[SimpleNamespace(aux_type="客户", n=3, amt=100.0)],
        aux_name_rows=[],
    )
    res = _run(aggregate_aux_by_name_ex(session, "p", 2025, ["1221"]))
    assert res.reason == "no_rows"
    assert res.entries == []
    assert res.aux_type == "客户"
    assert res.total_units == 0


def test_reason_no_rows_when_only_blank_aux_names():
    """全是空 aux_name 的行也判 no_rows（entries 过滤后为空）。"""
    session = _FakeAggSession(
        aux_type_rows=[SimpleNamespace(aux_type="客户", n=1, amt=1.0)],
        aux_name_rows=[SimpleNamespace(aux_name="  ", opening=0, debit=0, credit=0, closing=0)],
    )
    res = _run(aggregate_aux_by_name_ex(session, "p", 2025, ["1221"]))
    assert res.reason == "no_rows"
    assert res.entries == []


def test_reason_ok_when_rows_returned():
    session = _FakeAggSession(
        aux_type_rows=[SimpleNamespace(aux_type="客户", n=2, amt=170.0)],
        aux_name_rows=[
            SimpleNamespace(aux_name="甲公司", opening=100.0, debit=20.0, credit=0.0, closing=120.0),
            SimpleNamespace(aux_name="乙公司", opening=0.0, debit=0.0, credit=0.0, closing=50.0),
        ],
    )
    res = _run(aggregate_aux_by_name_ex(session, "p", 2025, ["1221"]))
    assert res.reason == "ok"
    assert res.aux_type == "客户"
    assert res.total_units == 2
    assert [e.aux_name for e in res.entries] == ["甲公司", "乙公司"]
    assert res.entries[0].closing == 120.0


def test_reason_error_on_internal_exception():
    """内部抛异常 → reason='error' 且 rollback 被调用（fail-open 但不静默）。"""
    session = _FakeAggSession(raise_at=1)
    res = _run(aggregate_aux_by_name_ex(session, "p", 2025, ["1221"]))
    assert res == AuxAggregationResult([], None, 0, "error")
    assert session.rolled_back is True


# ── Property 6: reason 与异常日志分离不变式 ──────────────────────────────────

def test_property6_error_logs_exactly_one_error_with_context(caplog):
    """异常路径必须记**恰好一条** ERROR，且含 project_id / year / account_prefixes。"""
    session = _FakeAggSession(raise_at=1)
    with caplog.at_level(logging.ERROR, logger="app.services.four_table.aux_aggregation"):
        res = _run(aggregate_aux_by_name_ex(session, "proj-42", 2024, ["2203", "2205"]))
    assert res.reason == "error"
    errors = [
        r for r in caplog.records
        if r.levelno >= logging.ERROR
        and r.name == "app.services.four_table.aux_aggregation"
    ]
    assert len(errors) == 1
    msg = errors[0].getMessage()
    assert "proj-42" in msg
    assert "2024" in msg
    assert "2203" in msg and "2205" in msg
    # logger.exception → 必带异常堆栈信息
    assert errors[0].exc_info is not None


def test_property6_no_rows_logs_no_error(caplog):
    """`no_rows`（正常空）路径不得记 ERROR —— 与 error 不可混淆。"""
    session = _FakeAggSession(
        aux_type_rows=[SimpleNamespace(aux_type="客户", n=1, amt=1.0)],
        aux_name_rows=[],
    )
    with caplog.at_level(logging.ERROR, logger="app.services.four_table.aux_aggregation"):
        res = _run(aggregate_aux_by_name_ex(session, "p", 2025, ["1221"]))
    assert res.reason == "no_rows"
    errors = [
        r for r in caplog.records
        if r.levelno >= logging.ERROR
        and r.name == "app.services.four_table.aux_aggregation"
    ]
    assert errors == []


def test_property6_no_aux_type_logs_no_error(caplog):
    """`no_aux_type` 也是正常空，不记 ERROR。"""
    session = _FakeAggSession(aux_type_rows=[])
    with caplog.at_level(logging.ERROR, logger="app.services.four_table.aux_aggregation"):
        _run(aggregate_aux_by_name_ex(session, "p", 2025, ["1221"]))
    errors = [
        r for r in caplog.records
        if r.levelno >= logging.ERROR
        and r.name == "app.services.four_table.aux_aggregation"
    ]
    assert errors == []


# ── 旧薄壳零回归守卫：4 消费者逐字段不变 ─────────────────────────────────────

def test_legacy_shell_returns_three_tuple_ok():
    """旧 `aggregate_aux_by_name` 仍返回三元组 `(entries, aux_type, total_units)`，
    丢弃 reason。4 消费者（_k1_import_export / row_name_alignment / K1 测试两桩）
    按三元组解包，逐字段与 `_ex` 一致。"""
    session = _FakeAggSession(
        aux_type_rows=[SimpleNamespace(aux_type="客户", n=1, amt=120.0)],
        aux_name_rows=[
            SimpleNamespace(aux_name="甲公司", opening=100.0, debit=20.0, credit=0.0, closing=120.0),
        ],
    )
    got = _run(aggregate_aux_by_name(session, "p", 2025, ["1221"]))
    assert isinstance(got, tuple) and len(got) == 3
    entries, aux_type, total_units = got
    assert aux_type == "客户"
    assert total_units == 1
    assert entries[0].aux_name == "甲公司" and entries[0].closing == 120.0


def test_legacy_shell_empty_prefixes_matches_old_contract():
    """无前缀旧契约返回 `([], None, 0)`（reason 被薄壳丢弃）。"""
    got = _run(aggregate_aux_by_name(_FakeAggSession(), "p", 2025, []))
    assert got == ([], None, 0)


def test_legacy_shell_no_rows_matches_old_contract():
    """旧实现：锁到 aux_type 但 0 行时返回 `([], aux_type, 0)`（非 None）——薄壳须逐字保留。"""
    session = _FakeAggSession(
        aux_type_rows=[SimpleNamespace(aux_type="客户", n=1, amt=1.0)],
        aux_name_rows=[],
    )
    got = _run(aggregate_aux_by_name(session, "p", 2025, ["1221"]))
    assert got == ([], "客户", 0)


def test_legacy_shell_exception_matches_old_contract():
    """异常时旧契约返回 `([], None, 0)`；薄壳委托 `_ex`，reason='error' 被丢弃。"""
    session = _FakeAggSession(raise_at=1)
    got = _run(aggregate_aux_by_name(session, "p", 2025, ["1221"]))
    assert got == ([], None, 0)


def test_legacy_shell_is_field_for_field_projection_of_ex():
    """守卫：薄壳的返回三元组必须是 `_ex` 结果前三字段的逐字节投影
    （改 `_ex` 若破坏三元组顺序/值，这里必红）。"""
    session_a = _FakeAggSession(
        aux_type_rows=[SimpleNamespace(aux_type="供应商", n=2, amt=5.0)],
        aux_name_rows=[
            SimpleNamespace(aux_name="X", opening=1.0, debit=2.0, credit=3.0, closing=4.0),
        ],
    )
    session_b = _FakeAggSession(
        aux_type_rows=[SimpleNamespace(aux_type="供应商", n=2, amt=5.0)],
        aux_name_rows=[
            SimpleNamespace(aux_name="X", opening=1.0, debit=2.0, credit=3.0, closing=4.0),
        ],
    )
    ex = _run(aggregate_aux_by_name_ex(session_a, "p", 2025, ["1221"]))
    shell = _run(aggregate_aux_by_name(session_b, "p", 2025, ["1221"]))
    assert shell == (ex.entries, ex.aux_type, ex.total_units)
