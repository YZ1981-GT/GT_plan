"""变更传播（R8）：闭包、标过期、重算、冻结项目不动、事件只认本 spec 来源、失败可见降级。"""
from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import sqlalchemy as sa

from app.models.base import ProjectStatus
from app.models.report_models import FinancialReport
from app.services.formula_settings import propagation
from app.services.formula_settings.propagation import on_formula_config_changed, report_closure

from ._env import BS, add_global_row, add_project, add_project_row, make_db


def _cfg(code, formula=None):
    return SimpleNamespace(row_code=code, formula=formula, aje_formula=None, rje_formula=None)


def test_closure_follows_row_and_sum_row_transitively():
    configs = [_cfg("BS-001", "TB('1001','期末余额')"), _cfg("BS-002", "ROW('BS-001')"),
               _cfg("BS-010", "SUM_ROW('BS-001','BS-005')"), _cfg("BS-020", "ROW('BS-010')*2"),
               _cfg("BS-030", "ROW('BS-099')"), _cfg("BS-040", "SUM_ROW('BS-006','BS-009')")]
    assert report_closure(configs, {"BS-001"}) == {"BS-001", "BS-002", "BS-010", "BS-020"}


async def _seed_reports(db, pid, codes, *, year=2025):
    for code in codes:
        db.add(FinancialReport(project_id=pid, year=year, report_type=BS, row_code=code, row_name=code,
                               current_period_amount=Decimal("1")))
    await db.flush()


async def test_propagate_report_marks_closure_and_recalculates(monkeypatch):
    async with make_db() as factory:
        async with factory() as db:
            await add_global_row(db, "BS-001", "100")
            await add_global_row(db, "BS-002", "ROW('BS-001')", row_number=2)
            await add_global_row(db, "BS-003", "7", row_number=3)
            pid = await add_project(db, "传播")
            await add_project_row(db, pid, "BS-001", "250", base_formula="100")
            await _seed_reports(db, pid, ["BS-001", "BS-002", "BS-003"])
            await db.commit()
        propagation.set_session_factory(factory)
        published = []

        async def fake_publish(payload):
            published.append(payload)

        from app.services.event_bus import event_bus

        monkeypatch.setattr(event_bus, "publish", fake_publish)
        try:
            out = await propagation.propagate_report(pid, 2025, ["balance_sheet:BS-001"])
        finally:
            propagation.set_session_factory(None)
        assert out["closure"] == ["BS-001", "BS-002"] and out["marked"] == 2
        async with factory() as db:
            rows = {r.row_code: r for r in (await db.execute(sa.select(FinancialReport))).scalars()}
        assert (rows["BS-001"].current_period_amount, rows["BS-001"].is_stale) == (Decimal("250"), False)
        assert (rows["BS-002"].current_period_amount, rows["BS-002"].is_stale) == (Decimal("250"), False)
        assert (rows["BS-003"].current_period_amount, rows["BS-003"].is_stale) == (Decimal("1"), False)
        assert [p.event_type.value for p in published] == ["reports.updated"]


async def test_frozen_project_is_not_recalculated():
    async with make_db() as factory:
        async with factory() as db:
            await add_global_row(db, "BS-001", "100")
            pid = await add_project(db, "归档", status=ProjectStatus.archived)
            await _seed_reports(db, pid, ["BS-001"])
            await db.commit()
        propagation.set_session_factory(factory)
        try:
            out = await propagation.propagate_report(pid, 2025, ["balance_sheet:BS-001"])
        finally:
            propagation.set_session_factory(None)
        assert out == {"skipped": "frozen"}
        async with factory() as db:
            row = (await db.execute(sa.select(FinancialReport))).scalar_one()
        assert (row.is_stale, row.current_period_amount) == (False, Decimal("1"))


async def test_handler_ignores_foreign_events_and_logs_failures(monkeypatch):
    calls, degraded = [], []

    async def fake(pid, year, slots):
        calls.append((pid, year, slots))
        raise RuntimeError("注入失败")

    monkeypatch.setitem(propagation.HANDLERS, "report", fake)
    import app.services.stale_degraded_logger as sdl

    monkeypatch.setattr(sdl, "log_stale_degraded", lambda **kw: degraded.append(kw))
    pid = uuid.uuid4()
    await on_formula_config_changed(SimpleNamespace(project_id=pid, year=2025, extra={"row_code": "BS-001"}))
    assert calls == []
    await on_formula_config_changed(SimpleNamespace(project_id=pid, year=2025, extra={
        "origin": "formula_settings", "domain": "report", "slot_keys": ["balance_sheet:BS-001"]}))
    assert calls == [(pid, 2025, ["balance_sheet:BS-001"])]
    assert degraded and degraded[0]["source"] == "formula_settings:report"


async def test_publish_events_payload_shape(monkeypatch):
    sent = []
    from app.services.event_bus import event_bus

    async def fake_publish(payload):
        sent.append(payload)

    monkeypatch.setattr(event_bus, "publish", fake_publish)
    pid = uuid.uuid4()
    n = await propagation.publish_events([{"project_id": str(pid), "slot_keys": ["balance_sheet:BS-001"]},
                                          {"project_id": str(uuid.uuid4()), "slot_keys": []}],
                                         domain="report", source="global_edit", token="tok")
    assert n == 1
    extra = sent[0].extra
    assert (extra["origin"], extra["row_code"], extra["row_codes"], extra["publish_token"]) == (
        "formula_settings", "", ["BS-001"], "tok")


async def _stale_flags(factory) -> dict[str, bool]:
    async with factory() as db:
        return {r.row_code: r.is_stale for r in (await db.execute(sa.select(FinancialReport))).scalars()}


async def _seed_one(factory, *, project_formula="250"):
    async with factory() as db:
        await add_global_row(db, "BS-001", "100")
        await add_global_row(db, "BS-002", "ROW('BS-001')", row_number=2)
        pid = await add_project(db, "重算失败")
        await add_project_row(db, pid, "BS-001", project_formula, base_formula="100")
        await _seed_reports(db, pid, ["BS-001", "BS-002"])
        await db.commit()
    return pid


async def test_recalc_failure_keeps_stale_marks_and_logs_degraded(monkeypatch):
    """R8.2：重算整体失败（抛异常）时，闭包行的过期标记仍落库可见；记降级日志；不发 REPORTS_UPDATED。

    修复前标过期与重算同一事务，重算一抛整笔回滚 ⇒ 过期标记一起消失，报表看起来「已是最新」。
    """
    from app.services.event_bus import event_bus
    from app.services.report_engine import ReportEngine
    import app.services.stale_degraded_logger as sdl

    async def boom(self, *a, **kw):
        raise RuntimeError("注入：重算整体失败")

    published, degraded = [], []

    async def fake_publish(payload):
        published.append(payload)

    monkeypatch.setattr(ReportEngine, "recalculate_stale_rows", boom)
    monkeypatch.setattr(event_bus, "publish", fake_publish)
    monkeypatch.setattr(sdl, "log_stale_degraded", lambda **kw: degraded.append(kw))
    async with make_db() as factory:
        pid = await _seed_one(factory)
        propagation.set_session_factory(factory)
        try:
            out = await propagation.propagate_report(pid, 2025, ["balance_sheet:BS-001"])
        finally:
            propagation.set_session_factory(None)
        assert (out["marked"], out["recalculated"]) == (2, None) and "注入" in out["error"]
        assert await _stale_flags(factory) == {"BS-001": True, "BS-002": True}
    assert published == []
    assert [d["source"] for d in degraded] == ["formula_settings:report_recalc"]


async def test_row_level_recalc_failures_are_logged(monkeypatch):
    """单行重算失败：该行保留过期（引擎只清成功行），失败清单进降级日志可查。"""
    import app.services.stale_degraded_logger as sdl
    from app.services.event_bus import event_bus

    degraded = []

    async def fake_publish(payload):
        pass

    monkeypatch.setattr(event_bus, "publish", fake_publish)
    monkeypatch.setattr(sdl, "log_stale_degraded", lambda **kw: degraded.append(kw))
    async with make_db() as factory:
        pid = await _seed_one(factory, project_formula="ROW('BS-404') +")  # 语法错误 ⇒ 本行重算失败
        propagation.set_session_factory(factory)
        try:
            out = await propagation.propagate_report(pid, 2025, ["balance_sheet:BS-001"])
        finally:
            propagation.set_session_factory(None)
        failed = {r["row_code"] for r in out["recalculated"]["failed_rows"]}
        assert "BS-001" in failed
        flags = await _stale_flags(factory)
        assert flags["BS-001"] is True
    assert degraded and degraded[0]["source"] == "formula_settings:report_recalc_rows"
    assert {r["row_code"] for r in degraded[0]["context"]["failed_rows"]} == failed


async def test_propagate_wp_marks_prefill_stale_only_for_that_code():
    from app.models.workpaper_models import WorkingPaper, WpFormula, WpIndex

    from .test_domain_adapters import add_wp

    async with make_db(extra_models=(WpIndex, WorkingPaper, WpFormula)) as factory:
        async with factory() as db:
            pid = await add_project(db, "底稿传播")
            d2 = await add_wp(db, pid, "D2")
            e1 = await add_wp(db, pid, "E1")
            archived = await add_project(db, "归档底稿", status=ProjectStatus.archived)
            a_d2 = await add_wp(db, archived, "D2")
            await db.commit()
        propagation.set_session_factory(factory)
        try:
            out = await propagation.propagate_wp(pid, 2025, ["D2|审定表|C5", "D2|明细表|B3"])
            skipped = await propagation.propagate_wp(archived, 2025, ["D2|审定表|C5"])
        finally:
            propagation.set_session_factory(None)
        assert out == {"wp_codes": ["D2"], "marked": 1} and skipped == {"skipped": True}
        async with factory() as db:
            flags = {r.id: r.prefill_stale for r in (await db.execute(sa.select(WorkingPaper))).scalars()}
        assert (flags[d2], flags[e1], flags[a_d2]) == (True, False, False)


async def test_event_without_year_is_backfilled_and_reaches_consol_note_refill(monkeypatch):
    """端到端：publish_events 不带 year → 事件总线按项目审计年度补齐（FORMULA_CONFIG_CHANGED 在
    YEAR_SCOPED_EVENT_TYPES）→ 合并附注传播拿到年度并按章节重新填数（不是恒「no_year」跳过）。"""
    import app.core.database as database
    from app.models.audit_platform_schemas import EventType
    from app.services import consol_note_formula_service as cnfs
    from app.services import event_bus as event_bus_module

    fills = []

    async def fake_fill(db, project_id, year, sections):
        fills.append((project_id, year, list(sections)))
        return {"filled": len(sections)}

    monkeypatch.setattr(cnfs, "fill_note_sections", fake_fill)
    async with make_db() as factory:
        async with factory() as db:
            pid = await add_project(db, "合并附注传播", report_scope="consolidated")  # audit_year=2025
            await db.commit()
        bus = event_bus_module.EventBus(debounce_ms=0)
        bus._redis_available = False  # 不往本机共享 Redis Stream 写测试事件
        bus.subscribe(EventType.FORMULA_CONFIG_CHANGED, propagation.on_formula_config_changed)
        monkeypatch.setattr(event_bus_module, "event_bus", bus)
        monkeypatch.setattr(bus, "publish", bus.publish_immediate)
        monkeypatch.setattr(database, "async_session", factory)  # 年度补齐自开短会话
        propagation.set_session_factory(factory)
        try:
            sent = await propagation.publish_events(
                [{"project_id": str(pid), "slot_keys": ["五、1|2|3", "五、1|4|3", "五、7|1|1"]}],
                domain="consol_note", source="global_edit")
        finally:
            propagation.set_session_factory(None)
    assert sent == 1
    assert fills == [(pid, 2025, ["五、1", "五、7"])]
