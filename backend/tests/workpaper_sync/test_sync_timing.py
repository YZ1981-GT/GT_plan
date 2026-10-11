"""P0 分阶段计时（spec workpaper-sync-switch-performance · 需求 1）。"""

from __future__ import annotations

import asyncio
import json
import logging

import pytest

from app.services.workpaper_sync import sync_timing as T
from app.services.workpaper_sync.oo_to_html import ApplyJournal, ApplyStage


def test_mark_without_scope_is_a_no_op() -> None:
    assert T.current_scope() is None
    T.mark("anything")  # 不抛、不产生作用域
    assert T.current_scope() is None


def _timing_lines(caplog: pytest.LogCaptureFixture) -> list[dict]:
    out = []
    for record in caplog.records:
        message = record.getMessage()
        if record.name == "workpaper_sync.timing" and message.startswith(T.TIMING_LOG_PREFIX):
            out.append(json.loads(message[len(T.TIMING_LOG_PREFIX):].strip()))
    return out


def test_scope_records_phases_in_order_and_logs_one_line(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="workpaper_sync.timing")
    with T.timing_scope("html_to_oo", wp="w1", entry="e1", skipped=None) as scope:
        T.mark("preflight")
        T.mark("reuse_lookup")
        assert T.current_scope() is scope
    assert T.current_scope() is None
    lines = _timing_lines(caplog)
    assert len(lines) == 1
    line = lines[0]
    assert line["kind"] == "html_to_oo" and line["outcome"] == "ok"
    assert line["wp"] == "w1" and line["entry"] == "e1" and "skipped" not in line
    assert [p["phase"] for p in line["phases"]] == ["preflight", "reuse_lookup"]
    assert all(p["ms"] >= 0 for p in line["phases"])
    assert line["total_ms"] >= sum(p["ms"] for p in line["phases"]) - 0.5


def test_exception_path_still_logs_and_reraises(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="workpaper_sync.timing")
    with pytest.raises(RuntimeError):
        with T.timing_scope("oo_to_html_apply"):
            T.mark("extract")
            raise RuntimeError("boom")
    lines = _timing_lines(caplog)
    assert lines and lines[-1]["outcome"] == "error"
    assert T.current_scope() is None


def test_nested_scope_restores_the_outer_one() -> None:
    with T.timing_scope("outer") as outer:
        with T.timing_scope("inner") as inner:
            T.mark("x")
        assert T.current_scope() is outer
        T.mark("y")
    assert [p for p, _ in inner.phases] == ["x"]
    assert [p for p, _ in outer.phases] == ["y"]


@pytest.mark.asyncio
async def test_marks_from_worker_threads_land_in_the_request_scope() -> None:
    """`asyncio.to_thread` 复制上下文：CPU 段在线程里 mark 仍记进同一作用域。"""
    with T.timing_scope("html_to_oo") as scope:
        await asyncio.to_thread(T.mark, "cpu_segment")
    assert [p for p, _ in scope.phases] == ["cpu_segment"]


def test_apply_journal_marks_without_changing_its_shape() -> None:
    journal = ApplyJournal()
    with T.timing_scope("oo_to_html_apply") as scope:
        journal.record(ApplyStage.base_extracted, "rep-1")
        journal.record(ApplyStage.merged, "conflicts=0")
    assert journal.entries == [
        (ApplyStage.base_extracted, "rep-1"),
        (ApplyStage.merged, "conflicts=0"),
    ]
    assert [p for p, _ in scope.phases] == ["base_extracted", "merged"]
