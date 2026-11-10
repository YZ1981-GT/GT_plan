"""R4 冻结年度：在真实 SQLite 行上逐年比较，不调用共享服务。"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa

from app.models.consol_note_data_models import ConsolNoteData
from app.models.core import Project
from app.models.report_models import DisclosureNote, FinancialReport
from app.models.workpaper_models import WorkingPaper, WpFormula, WpIndex
from app.services.formula_settings import note_settings, outbox, propagation

from ._env import add_global_row, add_project, make_db
from .test_domain_adapters import add_wp
from .test_propagation import _seed_reports


async def test_report_enqueue_mark_only_updates_frozen_year():
    async with make_db() as factory:
        async with factory() as db:
            pid = await add_project(db, "报告年度")
            await add_global_row(db, "BS-001", "100")
            await add_global_row(db, "BS-002", "ROW('BS-001')", row_number=2)
            for year in (2024, 2025, 2026):
                await _seed_reports(db, pid, ["BS-001", "BS-002"], year=year)
            result = await propagation.mark_in_year(db, "report", pid, 2025, ["balance_sheet:BS-001"])
            assert result["marked"] == 2
            await db.commit()
        async with factory() as db:
            flags = {(r.year, r.row_code): r.is_stale for r in (await db.execute(sa.select(FinancialReport))).scalars()}
    assert len(flags) == 6
    assert flags == {(y, c): y == 2025 for y in (2024, 2025, 2026) for c in ("BS-001", "BS-002")}


async def test_note_materialize_and_mark_are_limited_to_year(monkeypatch):
    async def slots(*_a, **_kw):
        return {"五、1|0:1": SimpleNamespace(definition={"formula": "1"}, layer="project")}

    monkeypatch.setattr(note_settings, "effective_slots", slots)
    async with make_db(extra_models=(DisclosureNote,)) as factory:
        async with factory() as db:
            pid = await add_project(db, "附注年度")
            for year in (2024, 2025, 2026):
                db.add(DisclosureNote(project_id=pid, year=year, note_section="五、1", section_title="货币资金",
                                      table_data={"_user_formulas_origin": "formula_settings", "_user_formulas": []}))
            await db.commit()
        propagation.set_session_factory(factory)
        try:
            result = await propagation.propagate_note(pid, 2025, ["五、1|0:1"])
        finally:
            propagation.set_session_factory(None)
        assert result["materialized"] == result["marked"] == 1
        async with factory() as db:
            notes = {n.year: n for n in (await db.execute(sa.select(DisclosureNote))).scalars()}
    assert notes[2025].is_stale and notes[2025].table_data["_user_formulas"][0]["formula"] == "1"
    for year in (2024, 2026):
        assert notes[year].is_stale is False and notes[year].table_data["_user_formulas"] == []


async def test_consol_note_mark_updates_only_frozen_year_and_section():
    async with make_db(extra_models=(ConsolNoteData,)) as factory:
        async with factory() as db:
            pid = await add_project(db, "合并附注年度", report_scope="consolidated")
            for year in (2024, 2025, 2026):
                for section in ("五、1", "五、2"):
                    db.add(ConsolNoteData(project_id=pid, year=year, section_id=section,
                                         data={"amount": year}))
            await db.commit()
            result = await propagation.mark_in_year(db, "consol_note", pid, 2025, ["五、1|0:1"])
            assert result["marked"] == 1
            await db.commit()
        async with factory() as db:
            rows = {(r.year, r.section_id): (r.is_stale, r.data) for r in
                    (await db.execute(sa.select(ConsolNoteData))).scalars()}
    assert len(rows) == 6
    for (year, section), (stale, data) in rows.items():
        assert stale is (year == 2025 and section == "五、1")
        assert data == {"amount": year}


@pytest.mark.parametrize("year,reason", [(None, "no_year"), (2024, "year_mismatch")])
async def test_project_level_workpapers_not_changed_by_missing_or_old_year(year, reason):
    async with make_db(extra_models=(WpIndex, WorkingPaper, WpFormula)) as factory:
        async with factory() as db:
            pid = await add_project(db, "底稿年度边界")
            wid = await add_wp(db, pid, "D2")
            await db.commit()
            result = await propagation.mark_in_year(db, "wp", pid, year, ["D2|审定表|C5"])
            assert result["marked"] == 0 and result["skipped"] == reason
            await db.commit()
        propagation.set_session_factory(factory)
        try:
            result = await propagation.propagate_wp(pid, year, ["D2|审定表|C5"])
        finally:
            propagation.set_session_factory(None)
        assert result == {"skipped": reason}
        async with factory() as db:
            assert (await db.get(WorkingPaper, wid)).prefill_stale is False


async def test_report_handler_recalculates_only_frozen_year(monkeypatch):
    from app.services.event_bus import event_bus

    published = AsyncMock()
    monkeypatch.setattr(event_bus, "publish", published)
    async with make_db() as factory:
        async with factory() as db:
            pid = await add_project(db, "报表真实重算年度")
            for code, formula in (("BS-001", "150"), ("BS-002", "ROW('BS-001')"), ("BS-003", "7")):
                await add_global_row(db, code, formula)
            for year in (2024, 2025, 2026):
                await _seed_reports(db, pid, ["BS-001", "BS-002", "BS-003"], year=year)
            for row in (await db.execute(sa.select(FinancialReport))).scalars():
                row.current_period_amount = Decimal(row.year)
                row.is_stale = row.year == 2024
            await db.commit()
        propagation.set_session_factory(factory)
        try:
            result = await propagation.propagate_report(pid, 2025, ["balance_sheet:BS-001"])
        finally:
            propagation.set_session_factory(None)
        assert result["marked"] == 2
        assert result["recalculated"]["failed_count"] == 0
        async with factory() as db:
            rows = {(r.year, r.row_code): (r.current_period_amount, r.is_stale) for r in
                    (await db.execute(sa.select(FinancialReport))).scalars()}
    assert len(rows) == 9
    for (year, code), value in rows.items():
        expected = Decimal("150") if year == 2025 and code != "BS-003" else Decimal(year)
        assert value == (expected, year == 2024)
    assert published.await_count == 1
    assert published.await_args.args[0].year == 2025


def _memory_graph(*, degraded=False, graph=None):
    from app.services.stale_propagation_engine import StalePropagationEngine

    engine = StalePropagationEngine(defer_load=True)
    engine.__dict__.update(
        _deferred_load=False, _graph=graph or {}, _reverse_graph={},
        _identity_index={}, _identity_version=None,
        _degraded=degraded, _loaded=not degraded,
    )
    return engine


@pytest.mark.parametrize("reload_error", [None, RuntimeError("注入图重载失败")])
async def test_graph_unavailable_does_not_enter_yearless_fallback(monkeypatch, reload_error):
    from unittest.mock import Mock
    from app.services import stale_propagation_engine as graph_module

    engine = _memory_graph(degraded=True)
    reload_graph = Mock(side_effect=reload_error)
    fallback, notify, audit = AsyncMock(), AsyncMock(), AsyncMock()
    preview = Mock(side_effect=AssertionError("严格执行不得依赖预览"))
    monkeypatch.setattr(engine, "_load_graph", reload_graph)
    monkeypatch.setattr(engine, "_fallback_mark_stale", fallback)
    monkeypatch.setattr(engine, "preview_impact", preview)
    monkeypatch.setattr(engine, "_notify_frontend", notify)
    monkeypatch.setattr(engine, "_write_audit_log", audit)
    monkeypatch.setattr(graph_module, "stale_engine", engine)
    expected = "注入图重载失败" if reload_error else "不限定年度的降级写入"
    async with make_db() as factory, factory() as db:
        pid = await add_project(db, "依赖图年度")
        await db.commit()
        with pytest.raises(RuntimeError, match=expected):
            await outbox._stale_engine_for_formula_change(db, pid, 2025, ["BS-001"])
    reload_graph.assert_called_once_with()
    preview.assert_not_called()
    fallback.assert_not_awaited()
    notify.assert_not_awaited()
    audit.assert_not_awaited()


async def test_graph_rejects_changed_project_year_before_preview(monkeypatch):
    from app.services.stale_propagation_engine import stale_engine
    from unittest.mock import Mock

    preview, write = Mock(), AsyncMock()
    monkeypatch.setattr(stale_engine, "preview_impact", preview)
    monkeypatch.setattr(stale_engine, "on_change", write)
    async with make_db() as factory, factory() as db:
        pid = await add_project(db, "图旧年度")
        (await db.get(Project, pid)).audit_year = 2026
        await db.commit()
        with pytest.raises(propagation.PropagationIncomplete, match="项目审计年度已变化"):
            await outbox._stale_engine_for_formula_change(db, pid, 2025, ["BS-001"])
    preview.assert_not_called()
    write.assert_not_awaited()


async def test_graph_passes_exact_year_and_unique_report_rows(monkeypatch):
    from app.services.stale_propagation_engine import stale_engine
    from unittest.mock import Mock, call

    preview, write = Mock(return_value={"degraded": False}), AsyncMock(return_value={"marked": 1})
    monkeypatch.setattr(stale_engine, "preview_impact", preview)
    monkeypatch.setattr(type(stale_engine), "is_degraded", property(lambda _self: False))
    monkeypatch.setattr(stale_engine, "on_change", write)
    async with make_db() as factory, factory() as db:
        pid = await add_project(db, "图精确年度")
        await db.commit()
        await outbox._stale_engine_for_formula_change(db, pid, 2025, ["BS-002", "BS-001", "BS-001"])
    preview.assert_not_called()
    assert write.await_args_list == [
        call("REPORT:BS-001::", pid, 2025, strict=True),
        call("REPORT:BS-002::", pid, 2025, strict=True),
    ]


@pytest.mark.parametrize("result", [{"degraded": True}, {"error": "注入图异常"}, None])
async def test_graph_bad_result_is_visible_failure(monkeypatch, result):
    from app.services.stale_propagation_engine import stale_engine

    monkeypatch.setattr(stale_engine, "preview_impact", lambda _uri: {})
    monkeypatch.setattr(type(stale_engine), "is_degraded", property(lambda _self: False))
    write = AsyncMock(return_value=result)
    monkeypatch.setattr(stale_engine, "on_change", write)
    async with make_db() as factory, factory() as db:
        pid = await add_project(db, "图失败结果")
        await db.commit()
        with pytest.raises(propagation.PropagationIncomplete, match="依赖图传播未完成"):
            await outbox._stale_engine_for_formula_change(db, pid, 2025, ["BS-001"])
    write.assert_awaited_once_with("REPORT:BS-001::", pid, 2025, strict=True)

@pytest.mark.parametrize("path", ["enqueue", "handler", "graph"])
async def test_wp_writers_exclude_deleted_and_cross_project_rows(monkeypatch, path):
    from app.services import stale_propagation_engine as graph_module

    async with make_db(extra_models=(WpIndex, WorkingPaper)) as factory:
        async with factory() as db:
            pid = await add_project(db, "目标底稿项目")
            other = await add_project(db, "其他底稿项目")
            live, deleted_index, deleted_wp = [await add_wp(db, pid, code) for code in ("D2", "D3", "D4")]
            foreign = await add_wp(db, other, "D2")
            crossed_wp, crossed_index = await add_wp(db, other, "D3"), await add_wp(db, pid, "D5")
            live_row = await db.get(WorkingPaper, live)
            deleted_row = await db.get(WorkingPaper, deleted_index)
            (await db.get(WpIndex, deleted_row.wp_index_id)).is_deleted = True
            (await db.get(WorkingPaper, deleted_wp)).is_deleted = True
            (await db.get(WorkingPaper, crossed_wp)).wp_index_id = live_row.wp_index_id
            (await db.get(WorkingPaper, crossed_index)).wp_index_id = (
                await db.get(WorkingPaper, foreign)).wp_index_id
            await db.commit()
        codes = ["D2", "D3", "D4", "D5"]
        slots = [f"{code}|审定表|C5" for code in codes]
        if path == "enqueue":
            async with factory() as db:
                result = await propagation.mark_in_year(db, "wp", pid, 2025, slots)
                await db.commit()
            assert result["marked"] == 1
        elif path == "handler":
            monkeypatch.setattr(propagation, "_session_factory", factory)
            result = await propagation.propagate_wp(pid, 2025, slots)
            assert result == {"wp_codes": codes, "marked": 1}
        else:
            monkeypatch.setattr(graph_module, "async_session_factory", factory)
            uris = [f"WP:{code}:审定表:C5" for code in codes]
            result = await _memory_graph()._mark_stale_by_uri(uris, pid, 2025, strict=True)
            assert result == {"wp": 1, "report": 0, "note": 0, "deliverable": 0}
        async with factory() as db:
            flags = {row.id: row.prefill_stale for row in
                     (await db.execute(sa.select(WorkingPaper))).scalars()}
        assert len(flags) == 6
        assert flags == {wid: wid == live for wid in
                         (live, deleted_index, deleted_wp, foreign, crossed_wp, crossed_index)}


@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize("failure", ["late_write", "commit"])
async def test_graph_write_failure_rolls_back_without_success_signals(monkeypatch, strict, failure):
    from contextlib import asynccontextmanager
    from app.services import stale_propagation_engine as graph_module, stale_state

    source = "REPORT:BS-001::"
    targets = ["WP:D2:审定表:C5", "NOTE:五、1:0:1"]
    engine = _memory_graph(graph={source: targets})
    notify, audit = AsyncMock(), AsyncMock()
    monkeypatch.setattr(engine, "_notify_frontend", notify)
    monkeypatch.setattr(engine, "_write_audit_log", audit)
    message = f"注入图事务失败:{failure}"
    if failure == "late_write":
        monkeypatch.setattr(stale_state, "mark_note_stale", AsyncMock(side_effect=RuntimeError(message)))
    else:
        targets.pop()
    async with make_db(extra_models=(WpIndex, WorkingPaper)) as factory:
        async with factory() as db:
            pid = await add_project(db, "图回滚反例")
            wid = await add_wp(db, pid)
            await db.commit()

        @asynccontextmanager
        async def write_session():
            async with factory() as session:
                if failure == "commit":
                    monkeypatch.setattr(session, "commit", AsyncMock(side_effect=RuntimeError(message)))
                yield session

        monkeypatch.setattr(graph_module, "async_session_factory", write_session)
        if strict:
            with pytest.raises(RuntimeError, match=message):
                await engine.on_change(source, pid, 2025, strict=True)
        else:
            result = await engine.on_change(source, pid, 2025)
            assert result["degraded"] is True and result["error"] == message
            assert result["written"] == {
                "wp": 0, "report": 0, "note": 0, "deliverable": 0, "error": message}
        async with factory() as db:
            assert (await db.get(WorkingPaper, wid)).prefill_stale is False
    notify.assert_not_awaited()
    audit.assert_not_awaited()


async def test_graph_receipt_counts_actual_rows_not_graph_hits(monkeypatch):
    from app.services import stale_propagation_engine as graph_module

    source = "REPORT:BS-001::"
    targets = ["WP:D2:审定表:C5", "WP:D3:审定表:C5"]
    engine = _memory_graph(graph={source: targets})
    notify, audit = AsyncMock(), AsyncMock()
    monkeypatch.setattr(engine, "_notify_frontend", notify)
    monkeypatch.setattr(engine, "_write_audit_log", audit)
    async with make_db(extra_models=(WpIndex, WorkingPaper)) as factory:
        async with factory() as db:
            pid = await add_project(db, "图命中不等于写入")
            wid = await add_wp(db, pid, "D2")
            await db.commit()
        monkeypatch.setattr(graph_module, "async_session_factory", factory)
        result = await engine.on_change(source, pid, 2025, strict=True)
        assert set(result["affected"]) == set(targets) and result["total"] == 2
        assert result["written"] == {"wp": 1, "report": 0, "note": 0, "deliverable": 0}
        assert result["marked"] == 1 and result["degraded"] is False
        async with factory() as db:
            assert (await db.get(WorkingPaper, wid)).prefill_stale is True
    notify.assert_awaited_once()
    audit.assert_awaited_once()


async def test_graph_write_session_refreshes_stale_project_identity(monkeypatch):
    from contextlib import asynccontextmanager
    from app.services import stale_propagation_engine as graph_module

    async with make_db(extra_models=(WpIndex, WorkingPaper)) as factory:
        async with factory() as db:
            pid = await add_project(db, "实际写事务年度重读")
            wid = await add_wp(db, pid)
            await db.commit()
        async with factory() as writing:
            cached = await writing.get(Project, pid)
            async with factory() as changing:
                await changing.execute(sa.update(Project).where(Project.id == pid).values(audit_year=2026))
                await changing.commit()
            assert cached.audit_year == 2025

            @asynccontextmanager
            async def write_session():
                yield writing

            monkeypatch.setattr(graph_module, "async_session_factory", write_session)
            with pytest.raises(RuntimeError, match="项目审计年度已变化"):
                await _memory_graph()._mark_stale_by_uri(["WP:D2:审定表:C5"], pid, 2025, strict=True)
        async with factory() as db:
            assert (await db.get(Project, pid)).audit_year == 2026
            assert (await db.get(WorkingPaper, wid)).prefill_stale is False
