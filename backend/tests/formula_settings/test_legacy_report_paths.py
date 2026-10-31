"""既有报表配置写路径收口（R9）：旧 PUT / POST / DELETE、物化、同步主模板、候选审核、历史回滚。"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.deps import get_current_user
from app.models.audit_log_models import AuditLogEntry
from app.models.report_models import ReportConfig, ReportConfigBaseline
from app.routers import formula_audit_log, report_config, report_config_baseline
from app.services.report_config_service import ReportConfigService

from ._env import STD, add_global_row, add_member, add_project, add_project_row, add_user, make_db, pending_items, \
    project_rows

OLD, NEW, MINE = "TB('1001','期末余额')", "TB('1001','期末余额')*2", "ROW('BS-009')"


@pytest_asyncio.fixture
async def api(monkeypatch):
    async with make_db(extra_models=(ReportConfigBaseline,)) as factory:
        async with factory() as db:
            g = await add_global_row(db, "BS-001", OLD)
            users = {n: await add_user(db, n, r) for n, r in (
                ("admin", "admin"), ("editor", "auditor"), ("manager", "manager"), ("outsider", "auditor"))}
            follow, conflict = await add_project(db, "跟随"), await add_project(db, "冲突")
            for p in (follow, conflict):
                await add_member(db, p, users["editor"], "edit")
                await add_member(db, p, users["manager"], "review")
            await add_project_row(db, follow, "BS-001", OLD, base_formula=OLD)
            pr = await add_project_row(db, conflict, "BS-001", MINE, base_formula=OLD)
            await db.commit()
            ids = {"global": g.id, "conflict_row": pr.id}
        events: list = []

        async def fake_publish_events(evs, **kw):
            events.extend(evs)
            return len(evs)

        for mod in (report_config, report_config_baseline):
            monkeypatch.setattr(mod, "publish_events", fake_publish_events)
        import app.services.formula_settings.propagation as prop

        monkeypatch.setattr(prop, "publish_events", fake_publish_events)
        app = FastAPI()
        for r in (report_config.router, report_config_baseline.router, formula_audit_log.router):
            app.include_router(r)
        who = {"u": users["admin"]}

        async def _db():
            async with factory() as s:
                yield s

        async def _user():
            return who["u"]

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = _user
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            yield {"c": client, "f": factory, "ids": ids, "p": {"follow": follow, "conflict": conflict},
                   "events": events, "as": lambda n: who.update(u=users[n])}


async def _global(f):
    async with f() as db:
        return (await db.execute(sa.select(ReportConfig).where(ReportConfig.applicable_standard == STD))).scalar_one()


async def test_put_global_row_is_a_publish_with_cas(api):
    c, gid = api["c"], api["ids"]["global"]
    r = await c.put(f"/api/report-config/{gid}", json={"formula": NEW})
    assert r.status_code == 428 and (await _global(api["f"])).formula == OLD
    r = await c.put(f"/api/report-config/{gid}", json={"formula": NEW, "expected_version": 5})
    assert r.status_code == 409
    r = await c.put(f"/api/report-config/{gid}", json={"formula": NEW, "expected_version": 1, "row_name": "货币资金"})
    assert r.status_code == 200, r.text
    assert (r.json()["formula"], r.json()["formula_version"], r.json()["row_name"]) == (NEW, 2, "货币资金")
    async with api["f"]() as db:
        assert (await project_rows(db, api["p"]["follow"]))["BS-001"].formula == NEW
        assert (await project_rows(db, api["p"]["conflict"]))["BS-001"].formula == MINE
        assert [i.project_id for i in await pending_items(db)] == [api["p"]["conflict"]]
    assert {e["project_id"] for e in api["events"]} == {str(api["p"]["follow"])}


async def test_put_global_structure_only_needs_no_version(api):
    r = await api["c"].put(f"/api/report-config/{api['ids']['global']}", json={"row_name": "改名"})
    assert r.status_code == 200 and r.json()["formula_version"] == 1 and api["events"] == []


async def test_put_project_row_saves_adaptation_with_project_audit(api):
    c, rid, pid = api["c"], api["ids"]["conflict_row"], api["p"]["conflict"]
    api["as"]("editor")
    assert (await c.put(f"/api/report-config/{rid}", json={"formula": "ROW('X')"})).status_code == 428
    r = await c.put(f"/api/report-config/{rid}", json={"formula": "ROW('X')", "expected_version": 1})
    assert r.status_code == 200 and r.json()["formula_version"] == 2
    async with api["f"]() as db:
        row = (await project_rows(db, pid))["BS-001"]
        assert (row.formula, row.base_definition["formula"]) == ("ROW('X')", OLD)
        entries = (await db.execute(sa.select(AuditLogEntry.payload))).scalars().all()
    hist = [e for e in entries if e.get("project_id") == str(pid)]
    assert hist and hist[-1]["row_code"] == "BS-001" and hist[-1]["new_formula"] == "ROW('X')"
    assert api["events"] == [{"project_id": str(pid), "slot_keys": ["balance_sheet:BS-001"]}]
    api["as"]("outsider")
    assert (await c.put(f"/api/report-config/{rid}", json={"formula": "1", "expected_version": 2})).status_code == 403


async def test_post_and_delete_route_through_kernel(api):
    c, pid = api["c"], api["p"]["follow"]
    r = await c.post("/api/report-config", json={"report_type": "balance_sheet", "row_code": "BS-050",
                                                 "row_name": "新增全局行", "row_number": 50,
                                                 "formula": "ROW('BS-001')", "applicable_standard": STD})
    assert r.status_code == 200 and r.json()["formula_version"] == 1
    api["as"]("editor")
    r = await c.post("/api/report-config", json={"report_type": "balance_sheet", "row_code": "BS-099",
                                                 "row_name": "本项目独有", "row_number": 99, "formula": "1",
                                                 "applicable_standard": f"project:{pid}"})
    assert r.status_code == 200 and r.json()["row_name"] == "本项目独有"
    row_id = r.json()["id"]
    r = await c.delete(f"/api/report-config/{row_id}")
    assert r.status_code == 200
    async with api["f"]() as db:
        assert "BS-099" not in await project_rows(db, pid)


async def test_materialize_writes_global_baseline(api):
    async with api["f"]() as db:
        pid = await add_project(db, "物化")
        await db.commit()
        out = await ReportConfigService(db).materialize_project_presets(pid, applicable_standard=STD)
        await db.commit()
        row = (await project_rows(db, pid))["BS-001"]
    assert out["created"] == 1
    assert (row.base_definition["formula"], row.base_version, row.base_origin) == (OLD, 1, "global")


async def test_apply_master_update_auth_and_pending(api):
    c, pid = api["c"], api["p"]["conflict"]
    body = {"project_id": str(pid), "standard": STD, "keep_local": True}
    api["as"]("outsider")
    assert (await c.post("/api/report-config/apply-master-update", json=body)).status_code == 403
    api["as"]("admin")
    await c.put(f"/api/report-config/{api['ids']['global']}", json={"formula": NEW, "expected_version": 1})
    async with api["f"]() as db:
        for item in await pending_items(db, pid):
            await db.delete(item)
        await db.commit()
    api["as"]("editor")
    r = await c.post("/api/report-config/apply-master-update", json=body)
    assert r.status_code == 200 and (r.json()["updated_count"], r.json()["pending_count"]) == (0, 1)
    stale = await c.get(f"/api/report-config/stale-status/{pid}")
    assert stale.json()["pending_count"] == 1 and stale.json()["is_stale"] is True
    api["as"]("outsider")
    assert (await c.get(f"/api/report-config/stale-status/{pid}")).status_code == 403
    assert (await c.get(f"/api/report-config/diff-vs-master/{pid}")).status_code == 403


async def test_baseline_candidate_review_publishes_globally(api):
    c, src = api["c"], api["p"]["conflict"]
    api["as"]("outsider")
    body = {"project_id": str(src), "row_code": "BS-001", "report_type": "balance_sheet", "standard": STD}
    assert (await c.post("/api/report-config/suggest-to-master", json=body)).status_code == 403
    api["as"]("editor")
    r = await c.post("/api/report-config/suggest-to-master", json=body)
    assert r.status_code == 200
    api["as"]("admin")
    r = await c.post("/api/report-config/review-candidate", json={"candidate_id": r.json()["candidate_id"],
                                                                  "approved": True})
    assert r.status_code == 200, r.text
    g = await _global(api["f"])
    assert (g.formula, g.formula_version) == (MINE, 2)
    async with api["f"]() as db:
        assert (await project_rows(db, api["p"]["follow"]))["BS-001"].formula == MINE  # 跟随项目自动更新
    assert {e["project_id"] for e in api["events"]} == {str(api["p"]["follow"])}


async def test_history_rollback_writes_project_adaptation_not_global(api):
    c, pid = api["c"], api["p"]["conflict"]
    api["as"]("editor")
    await c.put(f"/api/report-config/{api['ids']['conflict_row']}", json={"formula": "ROW('X')",
                                                                          "expected_version": 1})
    hist = (await c.get(f"/api/formula-audit-log/{pid}/2025", params={"legacy_without_year": "true"})).json()
    entry = next(e for e in hist if e["new_formula"] == "ROW('X')")
    # ADR-FHIC-10：不传 target_formula，目标由服务端从 old_definition 读取
    body = {"row_code": "BS-001", "source_log_id": entry["id"], "expected_version": 2}
    assert (await c.post(f"/api/formula-audit-log/{pid}/2025/rollback", json=body)).status_code == 403  # 角色门控
    api["as"]("manager")
    r = await c.post(f"/api/formula-audit-log/{pid}/2025/rollback", json=body)
    assert r.status_code == 200, r.text
    assert (r.json()["previous_formula"], r.json()["restored_formula"]) == ("ROW('X')", MINE)
    async with api["f"]() as db:
        assert (await project_rows(db, pid))["BS-001"].formula == MINE
    assert (await _global(api["f"])).formula == OLD  # 全局行不受影响
    other = api["p"]["follow"]
    r = await c.post(f"/api/formula-audit-log/{other}/2025/rollback", json=body)
    assert r.status_code == 404  # 别的项目的历史定位不到
    r = await c.post(f"/api/formula-audit-log/{pid}/2025/rollback",
                     json={**body, "source_log_id": str(uuid.uuid4())})
    assert r.status_code == 404


@pytest.mark.parametrize("payload_extra", [{}, {"module": "report"}])
async def test_rollback_locates_legacy_entry_by_unique_row_code(api, payload_extra):
    from app.services.audit_log_helper import append_audit_log

    pid = api["p"]["conflict"]
    async with api["f"]() as db:
        await append_audit_log(db, {"user_id": None, "project_id": pid, "action": "formula.changed",
                                    "resource_type": "report_config", "resource_id": "BS-001",
                                    "details": {"event_type": "formula_changed", "module": "report",
                                                "row_code": "BS-001", "action": "update", "old_formula": OLD,
                                                "new_formula": MINE, "result_value": "", **payload_extra}})
        await db.commit()
        log_id = (await db.execute(sa.select(AuditLogEntry.id))).scalars().all()[-1]
    api["as"]("manager")
    r = await api["c"].post(f"/api/formula-audit-log/{pid}/2025/rollback", json={
        "row_code": "BS-001", "source_log_id": str(log_id), "expected_version": 1})
    assert r.status_code == 200, r.text
    async with api["f"]() as db:
        assert (await project_rows(db, pid))["BS-001"].formula == OLD


async def test_fill_all_formulas_publishes_through_kernel():
    """R9.1：自动填公式（seed / fill-formulas / 模板库重建）= 一次全局发布，不再直改准则行。

    空公式全局行被填 → 版本 +1、留发布记录；跟随全局的本项目行（基线 = 空）随之更新；
    本项目改过的行不覆盖、生成待确认；有效定义变化的项目上报事件（调用方 commit 后发）。
    """
    from app.models.formula_setting_models import FormulaPublish
    from app.services.report_formula_service import ReportFormulaService

    async with make_db() as factory, factory() as db:
        await add_global_row(db, "BS-002", None, row_name="货币资金")
        follow = await add_project(db, "跟随空行")
        await add_project_row(db, follow, "BS-002", None, base_formula=None)
        follow_row = (await project_rows(db, follow))["BS-002"]
        empty = {"formula": None, "formula_category": "auto_calc"}  # 物化时的全局定义（空公式）
        follow_row.base_definition, follow_row.base_version, follow_row.base_origin = (dict(empty), 1, "global")
        mine = await add_project(db, "自填")
        await add_project_row(db, mine, "BS-002", "ROW('BS-009')", base_formula=None)
        mine_row = (await project_rows(db, mine))["BS-002"]
        mine_row.base_definition, mine_row.base_version, mine_row.base_origin = (dict(empty), 1, "global")
        inherit = await add_project(db, "继承")
        await db.commit()

        stats = await ReportFormulaService().fill_all_formulas(db, standard=STD)
        await db.commit()
        g = await _global(factory)
        assert stats["updated"] == 1 and g.formula and "TB('1001'" in g.formula and g.formula_version == 2
        assert (await db.scalar(sa.select(sa.func.count()).select_from(FormulaPublish))) == 1
        assert (await project_rows(db, follow))["BS-002"].formula == g.formula, "跟随全局的项目行随之更新"
        assert (await project_rows(db, mine))["BS-002"].formula == "ROW('BS-009')", "改过的行不覆盖"
        assert [i.project_id for i in await pending_items(db)] == [mine]
        changed = {e["project_id"] for e in stats["events"]}
        assert changed == {str(follow), str(inherit)}
        again = await ReportFormulaService().fill_all_formulas(db, standard=STD)
        assert again["updated"] == 0 and again["events"] == [], "幂等：已有公式的行跳过"


async def test_materialize_overwrite_adopts_global_and_closes_pending(api):
    """物化 overwrite = 本项目采用全局：项目行改回全局、该公式位待确认结案、写项目留痕、上报事件。"""
    c, pid = api["c"], api["p"]["conflict"]
    await c.put(f"/api/report-config/{api['ids']['global']}", json={"formula": NEW, "expected_version": 1})
    async with api["f"]() as db:
        assert [i.project_id for i in await pending_items(db, pid)] == [pid]
        out = await ReportConfigService(db).materialize_project_presets(pid, applicable_standard=STD,
                                                                         overwrite=True)
        await db.commit()
        row = (await project_rows(db, pid))["BS-001"]
        assert out["updated"] == 1 and row.formula == NEW and row.base_definition["formula"] == NEW
        assert await pending_items(db, pid) == [], "采用全局后待确认结案"
        assert out["events"] == [{"project_id": str(pid), "slot_keys": ["balance_sheet:BS-001"]}]
        hist = [p for p in (await db.execute(sa.select(AuditLogEntry.payload))).scalars().all()
                if p.get("project_id") == str(pid) and p.get("source") == "materialize_overwrite"]
        assert hist and hist[-1]["new_formula"] == NEW
