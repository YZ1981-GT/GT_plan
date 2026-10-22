"""公式设置端点：TestClient 真发请求（R11 / R12.2）。

只替换身份（``get_current_user``）与数据库（``get_db``）；``require_project_access`` / ``assert_project_permission``
照常查 project_users，无权限走真 403。拒绝时断言零写入。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.deps import get_current_user
from app.models.formula_setting_models import FormulaPublish, FormulaSyncItem
from app.models.report_models import ReportConfig
from app.routers import formula_settings as fs_router

from ._env import STD, add_global_row, add_member, add_project, add_project_row, add_user, make_db

SLOT = "balance_sheet:BS-001"
OLD, NEW, MINE = "TB('1001','期末余额')", "TB('1001','期末余额')*2", "ROW('BS-009')"


@pytest_asyncio.fixture
async def api(monkeypatch):
    async with make_db() as factory:
        async with factory() as db:
            await add_global_row(db, "BS-001", OLD)
            users = {name: await add_user(db, name, role) for name, role in (
                ("admin", "admin"), ("editor", "auditor"), ("reader", "auditor"), ("outsider", "auditor"))}
            a = await add_project(db, "项目A")
            b = await add_project(db, "项目B")
            c = await add_project(db, "项目C")
            await add_member(db, a, users["editor"], "edit")
            await add_member(db, a, users["reader"], "readonly")
            await add_member(db, b, users["editor"], "edit")
            await add_member(db, b, users["reader"], "readonly")
            await add_project_row(db, b, "BS-001", MINE, base_formula=OLD)
            await db.commit()
        events: list = []

        async def fake_publish_events(evs, **kw):
            events.extend(evs)
            return len(evs)

        monkeypatch.setattr(fs_router, "publish_events", fake_publish_events)
        app = FastAPI()
        app.include_router(fs_router.router)
        app.include_router(fs_router.project_router)
        who = {"u": users["admin"]}

        async def _db():
            async with factory() as s:
                yield s

        async def _user():
            return who["u"]

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = _user
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            yield {"c": client, "f": factory, "p": {"A": a, "B": b, "C": c}, "events": events,
                   "as": lambda name: who.update(u=users[name])}


async def _global_formula(f):
    async with f() as db:
        g = (await db.execute(sa.select(ReportConfig).where(ReportConfig.applicable_standard == STD))).scalar_one()
        return g.formula, g.formula_version


async def _count(f, model):
    async with f() as db:
        return await db.scalar(sa.select(sa.func.count()).select_from(model))


def _publish_body(version=1, **kw):
    return {"scope": STD, "changes": [{"slot_key": SLOT, "definition": {"formula": NEW},
                                       "expected_version": version}], **kw}


async def test_domains_and_global_read_for_any_logged_in_user(api):
    api["as"]("outsider")
    r = await api["c"].get("/api/formula-settings/domains")
    assert r.status_code == 200 and {d["key"] for d in r.json()["domains"]} >= {"report", "tb_detail", "wp"}
    assert r.json()["is_admin"] is False
    # 界面默认选第一个作用范围：须是常用准则；enterprise 是兜底口径（没有公式行），只能排最后
    report_scopes = [s["value"] for s in next(d for d in r.json()["domains"] if d["key"] == "report")["scopes"]]
    from app.services.formula_settings.projects import VALID_STANDARDS
    assert set(report_scopes) == set(VALID_STANDARDS)
    assert report_scopes[0] == "soe_standalone" and report_scopes[-1] == "enterprise"
    g = await api["c"].get("/api/formula-settings/report/global", params={"scope": STD})
    assert g.status_code == 200 and g.json()["slots"][0]["definition"]["formula"] == OLD
    assert g.json()["can_edit"] is False
    assert (await api["c"].get("/api/formula-settings/nope/global", params={"scope": STD})).status_code == 404


@pytest.mark.parametrize("path", ["preview", "publish"])
async def test_non_admin_global_write_is_403_with_zero_writes(api, path):
    api["as"]("editor")
    r = await api["c"].post(f"/api/formula-settings/report/global/{path}", json=_publish_body())
    assert r.status_code == 403 and r.json()["detail"]["error_code"] == "FORMULA_SETTING_FORBIDDEN"
    assert await _global_formula(api["f"]) == (OLD, 1)
    assert await _count(api["f"], FormulaPublish) == 0 and api["events"] == []


async def test_admin_publish_cas_and_conflict_pending(api):
    c = api["c"]
    r = await c.post("/api/formula-settings/report/global/publish", json=_publish_body(version=None))
    assert r.status_code == 428 and r.json()["detail"]["error_code"] == "FORMULA_VERSION_REQUIRED"
    r = await c.post("/api/formula-settings/report/global/publish", json=_publish_body(version=9))
    assert r.status_code == 409 and r.json()["detail"]["error_code"] == "FORMULA_VERSION_CONFLICT"
    assert await _global_formula(api["f"]) == (OLD, 1)
    pv = await c.post("/api/formula-settings/report/global/preview", json=_publish_body())
    assert pv.status_code == 200 and pv.json()["summary"]["conflict_count"] == 1
    r = await c.post("/api/formula-settings/report/global/publish", json=_publish_body(request_id="r1"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary"]["pending_total"] == 1 and await _global_formula(api["f"]) == (NEW, 2)
    changed = {e["project_id"] for e in api["events"]}
    assert str(api["p"]["A"]) in changed and str(api["p"]["B"]) not in changed
    again = await c.post("/api/formula-settings/report/global/publish", json=_publish_body(request_id="r1"))
    assert again.status_code == 200 and again.json()["idempotent"] is True
    pubs = await c.get("/api/formula-settings/publishes", params={"domain": "report"})
    assert len(pubs.json()["items"]) == 1


async def test_project_effective_and_overrides_permissions(api):
    c, a = api["c"], api["p"]["A"]
    base = f"/api/projects/{a}/formula-settings/report"
    api["as"]("outsider")
    assert (await c.get(f"{base}/effective")).status_code == 403
    api["as"]("reader")
    eff = await c.get(f"{base}/effective")
    assert eff.status_code == 200 and eff.json()["slots"][0]["layer"] == "global"
    body = {"items": [{"slot_key": SLOT, "definition": {"formula": MINE}}]}
    assert (await c.put(f"{base}/overrides", json=body)).status_code == 403
    api["as"]("outsider")
    assert (await c.put(f"{base}/overrides", json=body)).status_code == 403
    async with api["f"]() as db:
        assert (await db.execute(sa.select(ReportConfig).where(
            ReportConfig.applicable_standard == f"project:{a}"))).first() is None
    assert api["events"] == []
    api["as"]("editor")
    r = await c.put(f"{base}/overrides", json=body)
    assert r.status_code == 200, r.text
    assert api["events"] == [{"project_id": str(a), "slot_keys": [SLOT]}]
    eff = await c.get(f"{base}/effective")
    assert eff.json()["slots"][0]["layer"] == "project"
    r = await c.delete(f"{base}/overrides", params={"slot_key": SLOT})
    assert r.status_code == 200 and r.json()["restored"] == [SLOT]
    assert (await c.get(f"{base}/effective")).json()["slots"][0]["layer"] == "global"


async def test_pending_read_resolve_permissions(api):
    c, b = api["c"], api["p"]["B"]
    assert (await c.post("/api/formula-settings/report/global/publish", json=_publish_body())).status_code == 200
    api["as"]("reader")
    pend = await c.get(f"/api/projects/{b}/formula-settings/pending")
    assert pend.status_code == 200 and pend.json()["count"] == 1
    item = pend.json()["items"][0]
    assert (item["base_formula"], item["upstream_formula"], item["local_formula"]) == (OLD, NEW, MINE)
    body = {"resolutions": [{"item_id": item["id"], "choice": "adopt", "upstream_version": item["upstream_version"]}]}
    assert (await c.post(f"/api/projects/{b}/formula-settings/pending/resolve", json=body)).status_code == 403
    async with api["f"]() as db:
        assert (await db.get(FormulaSyncItem, uuid.UUID(item["id"]))).status == "pending"
    api["as"]("editor")
    r = await c.post(f"/api/projects/{b}/formula-settings/pending/resolve", json=body)
    assert r.status_code == 200 and r.json()["resolved"] == [item["id"]]
    assert r.json()["recalc_domains"] == ["report"], "采用新定义 ⇒ 有效定义变了，要重算"
    stale = await c.post(f"/api/projects/{b}/formula-settings/pending/resolve", json=body)
    assert stale.status_code == 409 and stale.json()["detail"]["error_code"] == "FORMULA_SYNC_ITEM_STALE"


async def test_pending_resolve_keep_reports_no_recalc(api):
    """全选「保留本项目」：有效定义不变 ⇒ recalc_domains 为空、不发重算事件（R5 走查：前端原先一律提示「会按新定义重算」）。"""
    c, b = api["c"], api["p"]["B"]
    assert (await c.post("/api/formula-settings/report/global/publish", json=_publish_body())).status_code == 200
    api["as"]("editor")
    item = (await c.get(f"/api/projects/{b}/formula-settings/pending")).json()["items"][0]
    before = list(api["events"])
    body = {"resolutions": [{"item_id": item["id"], "choice": "keep", "upstream_version": item["upstream_version"]}]}
    r = await c.post(f"/api/projects/{b}/formula-settings/pending/resolve", json=body)
    assert r.status_code == 200 and r.json()["resolved"] == [item["id"]]
    assert r.json()["recalc_domains"] == []
    assert api["events"] == before, "保留本项目不发重算事件"


async def test_apply_to_projects_requires_edit_on_every_target(api):
    c, a, b, cc = api["c"], api["p"]["A"], api["p"]["B"], api["p"]["C"]
    api["as"]("editor")
    base = f"/api/projects/{a}/formula-settings"
    targets = await c.get(f"{base}/apply-targets", params={"domain": "report"})
    assert [t["project_id"] for t in targets.json()["items"]] == [str(b)]
    body = {"target": "projects", "slot_keys": [SLOT], "project_ids": [str(b), str(cc)]}
    r = await c.post(f"{base}/report/apply", json=body)
    assert r.status_code == 403 and r.json()["detail"]["project_id"] == str(cc)
    assert await _count(api["f"], FormulaSyncItem) == 0
    r = await c.post(f"{base}/report/apply-preview", json={**body, "project_ids": [str(b)]})
    assert r.status_code == 200 and r.json()["items"][0]["category"] == "conflict"
    r = await c.post(f"{base}/report/apply", json={**body, "project_ids": [str(b)]})
    assert r.status_code == 200 and r.json()["summary"]["pending_total"] == 1


async def test_promote_global_is_admin_only_candidate_for_members(api):
    c, b = api["c"], api["p"]["B"]
    api["as"]("editor")
    base = f"/api/projects/{b}/formula-settings/report"
    r = await c.post(f"{base}/apply", json={"target": "global", "slot_keys": [SLOT]})
    assert r.status_code == 403 and await _global_formula(api["f"]) == (OLD, 1)
    r = await c.post(f"{base}/apply", json={"target": "candidate", "slot_keys": [SLOT], "note": "建议采用"})
    assert r.status_code == 200, r.text
    cid = r.json()["candidate"]["id"]
    assert (await c.post(f"/api/formula-settings/candidates/{cid}/review", json={"approve": True})).status_code == 403
    api["as"]("admin")
    pv = await c.post(f"/api/formula-settings/candidates/{cid}/preview")
    assert pv.status_code == 200 and pv.json()["candidate"]["status"] == "pending"
    r = await c.post(f"/api/formula-settings/candidates/{cid}/review", json={"approve": True})
    assert r.status_code == 200 and await _global_formula(api["f"]) == (MINE, 2)


async def test_delete_overrides_and_pending_read_auth_matrix(api):
    """补齐鉴权矩阵剩余格：DELETE overrides 的 readonly / 非成员，GET pending 的非成员。"""
    c, a = api["c"], api["p"]["A"]
    base = f"/api/projects/{a}/formula-settings/report"
    api["as"]("reader")
    assert (await c.delete(f"{base}/overrides", params={"slot_key": SLOT})).status_code == 403
    assert (await c.get(f"/api/projects/{a}/formula-settings/pending")).status_code == 200  # readonly 可读
    api["as"]("outsider")
    assert (await c.delete(f"{base}/overrides", params={"slot_key": SLOT})).status_code == 403
    assert (await c.get(f"/api/projects/{a}/formula-settings/pending")).status_code == 403  # 非成员读也 403
    assert (await c.post(f"{base}/apply-preview",
                         json={"target": "candidate", "slot_keys": [SLOT]})).status_code == 403


async def test_candidate_preview_is_admin_only(api):
    c, b = api["c"], api["p"]["B"]
    api["as"]("editor")
    r = await c.post(f"/api/projects/{b}/formula-settings/report/apply",
                     json={"target": "candidate", "slot_keys": [SLOT]})
    cid = r.json()["candidate"]["id"]
    assert (await c.post(f"/api/formula-settings/candidates/{cid}/preview")).status_code == 403  # 非 admin 预览候选


@pytest.mark.parametrize("domain", ["tb_detail", "cross_check", "wp", "note", "consol_note"])
async def test_effective_read_non_member_is_403_every_domain(api, domain):
    """六个域共用同一鉴权链：非成员读有效定义一律 403（鉴权在取数之前，与报表域同口径）。"""
    c, a = api["c"], api["p"]["A"]
    api["as"]("outsider")
    assert (await c.get(f"/api/projects/{a}/formula-settings/{domain}/effective")).status_code == 403


@pytest.mark.parametrize("domain", ["tb_detail", "cross_check", "note"])
async def test_effective_read_member_ok_for_formula_setting_domains(api, domain):
    """formula_setting 支撑的域：成员（readonly）读有效定义 200（wp / consol_note 读各自底稿 / 合并表，
    其取数在 test_domain_adapters.py 的域用例覆盖，这里不建那些表）。"""
    c, a = api["c"], api["p"]["A"]
    api["as"]("reader")
    assert (await c.get(f"/api/projects/{a}/formula-settings/{domain}/effective")).status_code == 200
