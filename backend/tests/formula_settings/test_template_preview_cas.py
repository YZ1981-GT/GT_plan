"""模板预览证据的跨请求契约；仅独立内存 SQLite，outbox 不代表传播实测。"""
from __future__ import annotations

import json
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.deps import get_current_user
from app.models.audit_log_models import AuditChainHead, AuditLogEntry
from app.models.formula_setting_models import (
    FormulaPublish, FormulaSetting, FormulaSyncItem, FormulaTemplate,
    FormulaTemplateSubscription, FormulaTemplateVersion,
)
from app.models.report_models import ReportConfig
from app.routers import formula_templates as router
from app.services.formula_settings import project_ops, template_sync
from app.services.formula_settings.stores import get_store
from app.services.formula_settings.template_service import global_scope

from ._env import STD, add_global_row, add_member, add_project, add_user, make_db

SLOT = "balance_sheet:BS-001"
SLOT2 = "balance_sheet:BS-002"
SNAPSHOT_MODELS = (FormulaTemplate, FormulaSetting, ReportConfig, FormulaPublish,
                   FormulaTemplateVersion, FormulaTemplateSubscription, FormulaSyncItem,
                   AuditLogEntry, AuditChainHead)


def changes(domain="report", slot=SLOT, formula="20"):
    return [{"domain": domain, "slot_key": slot, "definition": {"formula": formula}}]


async def snapshot(factory):
    async with factory() as db:
        result = {}
        for model in SNAPSHOT_MODELS:
            rows = (await db.execute(sa.select(model.__table__))).mappings().all()
            result[model.__tablename__] = sorted(
                json.dumps(dict(row), sort_keys=True, default=str, ensure_ascii=False) for row in rows)
        return result


@pytest_asyncio.fixture
async def api(monkeypatch):
    async with make_db() as factory:
        async with factory() as db:
            users = {name: await add_user(db, name, role) for name, role in (
                ("owner", "auditor"), ("admin", "admin"),
                ("readonly", "auditor"), ("outsider", "auditor"))}
            pid = await add_project(db, "【测试】跨请求 CAS")
            await add_member(db, pid, users["owner"], "edit")
            await add_member(db, pid, users["readonly"], "readonly")
            await add_global_row(db, "BS-001", "5")
            await add_global_row(db, "BS-002", "5", row_number=2)
            await db.commit()
        events = []

        async def local_record(db, *, events=(), **kwargs):
            recorded.extend(events)

        async def local_outbox(db):
            return {"queued": 0}

        recorded = events
        monkeypatch.setattr(router, "record_changes", local_record)
        monkeypatch.setattr(router, "publish_pending", local_outbox)
        app = FastAPI()
        app.include_router(router.router)
        app.include_router(router.project_router)
        sessions, who = [], {"user": users["owner"]}

        async def database():
            async with factory() as db:
                sessions.append(db)
                yield db

        async def identity():
            return who["user"]

        app.dependency_overrides[get_db] = database
        app.dependency_overrides[get_current_user] = identity
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://template-cas") as client:
            yield {"c": client, "f": factory, "p": pid, "events": events, "sessions": sessions,
                   "as": lambda name: who.update(user=users[name])}


async def create(api, *, domains=("report", "tb_detail"), scope=STD, subscribe=True):
    body = {"name": "【测试】预览证据", "share_scope": "team", "owner_project_id": str(api["p"]),
            "source": "manual", "applicable_scope": scope, "domains": list(domains),
            "items": [item for domain in domains for item in changes(
                domain, SLOT if domain == "report" else "1001", "10")]}
    response = await api["c"].post("/api/formula-templates", json=body)
    assert response.status_code == 201, response.text
    tid = response.json()["id"]
    if subscribe:
        for domain in domains:
            response = await api["c"].post(f"/api/projects/{api['p']}/formula-templates/subscribe",
                                           json={"template_id": tid, "domain": domain})
            assert response.status_code == 200, response.text
    return tid


async def preview(api, tid, body, *, rollback=False):
    endpoint = "rollback-preview" if rollback else "publish-preview"
    response = await api["c"].post(f"/api/formula-templates/{tid}/{endpoint}", json=body)
    assert response.status_code == 200, response.text
    fingerprint = response.json()["preview_fingerprint"]
    assert len(fingerprint) == 64 and all(ch in "0123456789abcdef" for ch in fingerprint)
    return {**body, "preview_fingerprint": fingerprint}, response.json()


async def local_save(api, domain, *, formula="99"):
    async with api["f"]() as editor:
        slot = SLOT if domain == "report" else "1001"
        current = (await get_store(domain).list_project(editor, api["p"]))[slot]
        await project_ops.save_overrides(editor, domain=domain, project_id=api["p"], user_id=None,
                                         items=[{"slot_key": slot, "definition": {"formula": formula},
                                                 "expected_version": current.version}])
        await editor.commit()
        assert all(editor is not request_session for request_session in api["sessions"])


async def local_row(api, domain):
    async with api["f"]() as db:
        return (await get_store(domain).list_project(db, api["p"]))[SLOT if domain == "report" else "1001"]


@pytest.mark.parametrize("domain", ["report", "tb_detail"])
@pytest.mark.parametrize("choice", ["adopt", "keep"])
async def test_cross_request_local_save_requires_new_preview(api, domain, choice):
    tid = await create(api)
    slot = SLOT if domain == "report" else "1001"
    body = {"expected_version": 1, "changes": changes(domain, slot)}
    before_preview = await snapshot(api["f"])
    old_body, old_preview = await preview(api, tid, body)
    assert old_preview["summary"]["conflict_count"] == 0
    assert await snapshot(api["f"]) == before_preview, "预览完成不得写入任何业务或审计行"
    preview_session = api["sessions"][-1]
    await local_save(api, domain)
    current = await local_row(api, domain)
    assert current.definition["formula"] == "99"
    before_rejection, event_count = await snapshot(api["f"]), len(api["events"])
    decision = {"conflict_choices": {f"{domain}|{api['p']}|{slot}": choice}}
    rejected = await api["c"].post(f"/api/formula-templates/{tid}/publish",
                                  json={**old_body, "decisions": decision})
    assert rejected.status_code == 409 and "重新预览" in rejected.text, rejected.text
    assert api["sessions"][-1] is not preview_session, "发布必须是真正独立请求 Session"
    assert await snapshot(api["f"]) == before_rejection
    assert len(api["events"]) == event_count
    fresh_body, fresh_preview = await preview(api, tid, body)
    assert fresh_body["preview_fingerprint"] != old_body["preview_fingerprint"]
    assert [(item["local_formula"], item["category"]) for item in fresh_preview["items"]] == [("99", "conflict")]
    published = await api["c"].post(f"/api/formula-templates/{tid}/publish",
                                   json={**fresh_body, "decisions": decision})
    assert published.status_code == 200 and published.json()["version"] == 2, published.text
    final = await local_row(api, domain)
    assert final.definition["formula"] == ("20" if choice == "adopt" else "99")
    assert final.base_definition["formula"] == "20" and final.base_version == 2
    assert final.base_origin == "template" and str(final.base_template_id) == tid
    async with api["f"]() as db:
        assert await db.scalar(sa.select(sa.func.count()).select_from(FormulaPublish)) == 1
        assert await db.scalar(sa.select(sa.func.count()).select_from(FormulaSyncItem)) == 0


async def prepare(api, *, rollback=False, domains=("report", "tb_detail"), subscribe=True):
    tid = await create(api, domains=domains, subscribe=subscribe)
    domain = domains[0]
    body = {"expected_version": 1,
            "changes": changes(domain, SLOT if domain == "report" else "1001")}
    if not rollback:
        return tid, "publish", body
    published_body, _ = await preview(api, tid, body)
    published = await api["c"].post(f"/api/formula-templates/{tid}/publish", json=published_body)
    assert published.status_code == 200 and published.json()["version"] == 2, published.text
    return tid, "rollback", {"expected_version": 2, "target_version": 1}


@pytest.mark.parametrize("rollback", [False, True], ids=["publish", "rollback"])
async def test_missing_preview_evidence_returns_428_without_writes(api, rollback):
    tid, endpoint, body = await prepare(api, rollback=rollback)
    before, event_count = await snapshot(api["f"]), len(api["events"])
    rejected = await api["c"].post(f"/api/formula-templates/{tid}/{endpoint}", json=body)
    assert rejected.status_code == 428 and "预览证据" in rejected.text, rejected.text
    assert await snapshot(api["f"]) == before
    assert len(api["events"]) == event_count


@pytest.mark.parametrize("dimension", ["template", "domain", "slot", "definition", "scope"])
async def test_preview_bound_to_template_and_exact_context_at_same_version(api, dimension):
    tid = await create(api, subscribe=False)
    body = {"expected_version": 1, "changes": changes()}
    old_body, _ = await preview(api, tid, body)
    target = tid
    if dimension == "template":
        target = await create(api, subscribe=False)
    elif dimension == "domain":
        body = {**body, "changes": changes("tb_detail", "1001")}
    elif dimension == "slot":
        body = {**body, "changes": changes(slot=SLOT2)}
    elif dimension == "definition":
        body = {**body, "changes": changes(formula="30")}
    elif dimension == "scope":
        updated = await api["c"].put(f"/api/formula-templates/{tid}", json={"applicable_scope": "listed_standalone"})
        assert updated.status_code == 200 and updated.json()["version"] == 1, updated.text
    target_preview_body, target_preview = await preview(api, target, body)
    assert target_preview["version"] == 1, "上下文变化不依赖模板总版本升级"
    assert target_preview_body["preview_fingerprint"] != old_body["preview_fingerprint"]
    before, event_count = await snapshot(api["f"]), len(api["events"])
    response = await api["c"].post(f"/api/formula-templates/{target}/publish",
                                  json={**body, "preview_fingerprint": old_body["preview_fingerprint"]})
    assert response.status_code == 409 and "重新预览" in response.text, response.text
    assert await snapshot(api["f"]) == before and len(api["events"]) == event_count
    published = await api["c"].post(f"/api/formula-templates/{target}/publish", json=target_preview_body)
    assert published.status_code == 200 and published.json()["version"] == 2, published.text


@pytest.mark.parametrize("role", ["owner", "admin"])
@pytest.mark.parametrize("rollback", [False, True], ids=["publish", "rollback"])
async def test_owner_and_admin_use_real_preview_and_write_routes(api, role, rollback):
    tid, endpoint, body = await prepare(api, rollback=rollback)
    api["as"](role)
    prepared, _ = await preview(api, tid, body, rollback=rollback)
    response = await api["c"].post(f"/api/formula-templates/{tid}/{endpoint}", json=prepared)
    assert response.status_code == 200, response.text
    expected = 3 if rollback else 2
    assert response.json()["version"] == expected
    assert (await local_row(api, "report")).definition["formula"] == ("10" if rollback else "20")


@pytest.mark.parametrize("role,status", [("readonly", 403), ("outsider", 404)])
@pytest.mark.parametrize("rollback", [False, True], ids=["publish", "rollback"])
async def test_non_managers_stay_denied_before_preview_and_write(api, role, status, rollback):
    tid, endpoint, body = await prepare(api, rollback=rollback)
    prepared, _ = await preview(api, tid, body, rollback=rollback)
    before, event_count = await snapshot(api["f"]), len(api["events"])
    api["as"](role)
    for action in (f"{endpoint}-preview", endpoint):
        response = await api["c"].post(f"/api/formula-templates/{tid}/{action}", json=prepared)
        assert response.status_code == status, response.text
    assert await snapshot(api["f"]) == before
    assert len(api["events"]) == event_count

async def global_save(api, domain="report", *, formula="7"):
    async with api["f"]() as editor:
        slot = SLOT if domain == "report" else "1001"
        version = await get_store(domain).write_global(
            editor, global_scope(domain, STD), slot, {"formula": formula}, user_id=None)
        await editor.commit()
        assert all(editor is not session for session in api["sessions"])
        return version


async def reject_stale_and_repreview(api, tid, endpoint, body, stale):
    before, event_count = await snapshot(api["f"]), len(api["events"])
    response = await api["c"].post(f"/api/formula-templates/{tid}/{endpoint}", json=stale)
    assert response.status_code == 409 and "重新预览" in response.text, response.text
    assert await snapshot(api["f"]) == before
    assert len(api["events"]) == event_count
    fresh, plan = await preview(api, tid, body, rollback=endpoint == "rollback")
    assert fresh["preview_fingerprint"] != stale["preview_fingerprint"]
    assert await snapshot(api["f"]) == before, "重新预览也不得产生写入"
    assert len(api["events"]) == event_count
    return fresh, plan


async def mutate_local_state(api, domain, *, pinned=False):
    """显式合成状态只写隔离 SQLite；正式 store 保留定义并更新版本。"""
    async with api["f"]() as editor:
        store = get_store(domain)
        slot = SLOT if domain == "report" else "1001"
        local = (await store.list_project(editor, api["p"]))[slot]
        await store.write_project(
            editor, api["p"], slot, definition=local.definition,
            base_definition=local.base_definition if pinned else {"formula": "9"},
            base_version=local.base_version if pinned else 0, pinned=pinned,
            base_origin=local.base_origin, base_template_id=local.base_template_id,
            user_id=None, label=local.label, structure=local.structure)
        await editor.commit()
        assert all(editor is not session for session in api["sessions"])


@pytest.mark.parametrize("domain", ["report", "tb_detail"])
@pytest.mark.parametrize("choice", ["adopt", "keep"])
async def test_rollback_cross_request_save_rejects_stale_preview(api, domain, choice):
    tid, endpoint, body = await prepare(api, rollback=True, domains=(domain,))
    before_preview = await snapshot(api["f"])
    stale, initial = await preview(api, tid, body, rollback=True)
    assert initial["summary"]["conflict_count"] == 0
    assert await snapshot(api["f"]) == before_preview
    preview_session = api["sessions"][-1]
    await local_save(api, domain)
    slot = SLOT if domain == "report" else "1001"
    decision = {"conflict_choices": {f"{domain}|{api['p']}|{slot}": choice}}
    fresh, plan = await reject_stale_and_repreview(api, tid, endpoint, body, stale)
    assert api["sessions"][-1] is not preview_session
    assert [(i["local_formula"], i["category"]) for i in plan["items"]] == [("99", "conflict")]
    response = await api["c"].post(f"/api/formula-templates/{tid}/rollback",
                                    json={**fresh, "decisions": decision})
    assert response.status_code == 200 and response.json()["version"] == 3, response.text
    local = await local_row(api, domain)
    assert local.definition["formula"] == ("10" if choice == "adopt" else "99")
    assert local.base_definition["formula"] == "10" and local.base_version == 3
    assert local.base_origin == "template" and str(local.base_template_id) == tid
    async with api["f"]() as db:
        assert await db.scalar(sa.select(sa.func.count()).select_from(FormulaPublish)) == 2
        assert await db.scalar(sa.select(sa.func.count()).select_from(FormulaSyncItem)) == 0
        assert (await db.get(FormulaTemplate, uuid.UUID(tid))).version == 3
        versions = (await db.execute(sa.select(FormulaTemplateVersion.version).order_by(
            FormulaTemplateVersion.version))).scalars().all()
        assert versions == [1, 2, 3]


@pytest.mark.parametrize("rollback", [False, True], ids=["publish", "rollback"])
@pytest.mark.parametrize("domain", ["report", "tb_detail"])
async def test_project_baseline_change_requires_new_preview(api, rollback, domain):
    tid, endpoint, body = await prepare(api, rollback=rollback, domains=(domain,))
    stale, _ = await preview(api, tid, body, rollback=rollback)
    old = await local_row(api, domain)
    await mutate_local_state(api, domain)
    altered = await local_row(api, domain)
    assert altered.definition == old.definition and altered.version == old.version + 1
    assert altered.base_definition == {"formula": "9"} and altered.base_version == 0
    fresh, plan = await reject_stale_and_repreview(api, tid, endpoint, body, stale)
    assert plan["version"] == body["expected_version"]
    assert [i["category"] for i in plan["items"]] == ["conflict"]
    slot = SLOT if domain == "report" else "1001"
    decisions = {"conflict_choices": {f"{domain}|{api['p']}|{slot}": "keep"}}
    response = await api["c"].post(f"/api/formula-templates/{tid}/{endpoint}",
                                    json={**fresh, "decisions": decisions})
    assert response.status_code == 200, response.text
    local = await local_row(api, domain)
    assert local.definition == old.definition and not local.pinned
    assert local.base_definition["formula"] == ("10" if rollback else "20")
    assert local.base_version == body["expected_version"] + 1


@pytest.mark.parametrize("rollback", [False, True], ids=["publish", "rollback"])
@pytest.mark.parametrize("domain", ["report", "tb_detail"])
async def test_local_pin_change_requires_new_preview_and_stays_deferred(api, rollback, domain):
    tid, endpoint, body = await prepare(api, rollback=rollback, domains=(domain,))
    stale, _ = await preview(api, tid, body, rollback=rollback)
    old = await local_row(api, domain)
    await mutate_local_state(api, domain, pinned=True)
    altered = await local_row(api, domain)
    assert altered.pinned and altered.definition == old.definition
    assert altered.base_definition == old.base_definition
    fresh, plan = await reject_stale_and_repreview(api, tid, endpoint, body, stale)
    assert plan["version"] == body["expected_version"]
    assert [i["category"] for i in plan["items"]] == ["pinned"]
    response = await api["c"].post(f"/api/formula-templates/{tid}/{endpoint}", json=fresh)
    assert response.status_code == 200, response.text
    local = await local_row(api, domain)
    assert local.pinned and local.definition == old.definition
    assert local.base_definition == old.base_definition and local.version == altered.version
    async with api["f"]() as db:
        pending = (await db.execute(sa.select(FormulaSyncItem))).scalar_one()
        assert pending.reason == "deferred" and pending.status == "pending"
        assert pending.upstream_definition["formula"] == ("10" if rollback else "20")
        assert pending.upstream_version == body["expected_version"] + 1


@pytest.mark.parametrize("rollback", [False, True], ids=["publish", "rollback"])
async def test_subscription_pin_change_requires_new_preview_at_same_template_version(api, rollback):
    tid, endpoint, body = await prepare(api, rollback=rollback, domains=("report",))
    stale, _ = await preview(api, tid, body, rollback=rollback)
    old = await local_row(api, "report")
    async with api["f"]() as editor:
        sub = (await editor.execute(sa.select(FormulaTemplateSubscription).where(
            FormulaTemplateSubscription.template_id == uuid.UUID(tid)))).scalar_one()
        assert not sub.pinned and sub.template_version == body["expected_version"]
        sub.pinned = True  # 明确隔离的合成状态：只切订阅固定，不改模板或项目公式。
        await editor.commit()
        assert all(editor is not session for session in api["sessions"])
    assert (await local_row(api, "report")) == old
    fresh, plan = await reject_stale_and_repreview(api, tid, endpoint, body, stale)
    assert plan["version"] == body["expected_version"]
    assert [i["category"] for i in plan["items"]] == ["follow"]
    response = await api["c"].post(f"/api/formula-templates/{tid}/{endpoint}", json=fresh)
    assert response.status_code == 200, response.text
    local = await local_row(api, "report")
    assert local.definition["formula"] == ("10" if rollback else "20")
    assert local.base_version == body["expected_version"] + 1
    async with api["f"]() as db:
        sub = (await db.execute(sa.select(FormulaTemplateSubscription))).scalar_one()
        assert not sub.pinned and sub.template_version == body["expected_version"] + 1
        assert await db.scalar(sa.select(sa.func.count()).select_from(FormulaSyncItem)) == 0


@pytest.mark.parametrize("rollback", [False, True], ids=["publish", "rollback"])
@pytest.mark.parametrize("domain", ["report", "tb_detail"])
async def test_template_baseline_keep_invalidates_preview_without_version_bump(api, rollback, domain):
    tid, endpoint, body = await prepare(api, rollback=rollback, domains=(domain,))
    global_version = await global_save(api, domain)
    stale, _ = await preview(api, tid, body, rollback=rollback)
    local = await local_row(api, domain)
    slot = SLOT if domain == "report" else "1001"
    async with api["f"]() as editor:
        tpl = await editor.get(FormulaTemplate, uuid.UUID(tid))
        row = (await editor.execute(sa.select(FormulaSetting).where(
            FormulaSetting.template_id == tpl.id, FormulaSetting.domain == domain,
            FormulaSetting.layer == "template", FormulaSetting.slot_key == slot))).scalar_one()
        old_version, old_definition = row.version, dict(row.definition)
        kept = await template_sync.keep_template_baseline(
            editor, tpl, expected_version=body["expected_version"], user_id=None,
            items=[{"domain": domain, "slot_key": slot, "expected_global_version": global_version}])
        assert kept["version"] == body["expected_version"] and row.version == old_version
        assert row.definition == old_definition and row.base_definition["formula"] == "7"
        assert row.base_version == global_version
        await editor.commit()
        assert all(editor is not session for session in api["sessions"])
    assert await local_row(api, domain) == local, "保留模板基线不得改订阅项目"
    fresh, plan = await reject_stale_and_repreview(api, tid, endpoint, body, stale)
    assert plan["version"] == body["expected_version"]
    response = await api["c"].post(f"/api/formula-templates/{tid}/{endpoint}", json=fresh)
    assert response.status_code == 200, response.text
    assert (await local_row(api, domain)).definition["formula"] == ("10" if rollback else "20")

@pytest.mark.parametrize("rollback", [False, True], ids=["publish", "rollback"])
@pytest.mark.parametrize("domain", ["report", "tb_detail"])
async def test_current_global_change_requires_preview_even_when_template_still_has_slot(api, rollback, domain):
    tid, endpoint, body = await prepare(api, rollback=rollback, domains=(domain,))
    stale, _ = await preview(api, tid, body, rollback=rollback)
    before_global = await snapshot(api["f"])
    local = await local_row(api, domain)
    global_version = await global_save(api, domain)
    after_global = await snapshot(api["f"])
    for model in (FormulaTemplate, FormulaTemplateVersion, FormulaTemplateSubscription, FormulaSyncItem,
                  FormulaPublish, AuditLogEntry, AuditChainHead):
        assert after_global[model.__tablename__] == before_global[model.__tablename__]
    assert await local_row(api, domain) == local
    fresh, plan = await reject_stale_and_repreview(api, tid, endpoint, body, stale)
    assert plan["version"] == body["expected_version"]
    assert [i["category"] for i in plan["items"]] == ["follow"]
    response = await api["c"].post(f"/api/formula-templates/{tid}/{endpoint}", json=fresh)
    assert response.status_code == 200, response.text
    target = "10" if rollback else "20"
    assert (await local_row(api, domain)).definition["formula"] == target
    slot = SLOT if domain == "report" else "1001"
    async with api["f"]() as db:
        row = (await db.execute(sa.select(FormulaSetting).where(
            FormulaSetting.layer == "template", FormulaSetting.template_id == uuid.UUID(tid),
            FormulaSetting.domain == domain, FormulaSetting.slot_key == slot))).scalar_one()
        assert row.definition["formula"] == target
        assert row.base_definition["formula"] == "7" and row.base_version == global_version
        assert row.base_origin == "global"

@pytest.mark.parametrize("rollback", [False, True], ids=["publish", "rollback"])
@pytest.mark.parametrize("domain", ["report", "tb_detail"])
async def test_unsubscribed_template_still_binds_current_global(api, rollback, domain):
    tid, endpoint, body = await prepare(api, rollback=rollback, domains=(domain,), subscribe=False)
    stale, initial = await preview(api, tid, body, rollback=rollback)
    assert initial["items"] == []
    version = await global_save(api, domain)
    fresh, plan = await reject_stale_and_repreview(api, tid, endpoint, body, stale)
    assert plan["items"] == [] and plan["version"] == body["expected_version"]
    response = await api["c"].post(f"/api/formula-templates/{tid}/{endpoint}", json=fresh)
    assert response.status_code == 200, response.text
    slot = SLOT if domain == "report" else "1001"
    async with api["f"]() as db:
        row = (await db.execute(sa.select(FormulaSetting).where(
            FormulaSetting.layer == "template", FormulaSetting.template_id == uuid.UUID(tid),
            FormulaSetting.domain == domain, FormulaSetting.slot_key == slot))).scalar_one()
        assert row.definition["formula"] == ("10" if rollback else "20")
        assert row.base_definition["formula"] == "7" and row.base_version == version
        assert row.base_origin == "global"
        assert await db.scalar(sa.select(sa.func.count()).select_from(FormulaTemplateSubscription)) == 0

async def mutate_global_without_version(api, domain, mutation):
    """模拟既有写入方漏升版本；只在隔离 SQLite 中制造该边界。"""
    slot = SLOT if domain == "report" else "1001"
    async with api["f"]() as editor:
        store = get_store(domain)
        before = (await store.list_global(editor, global_scope(domain, STD)))[slot]
        model = ReportConfig if domain == "report" else FormulaSetting
        row = await editor.get(model, before.row_id)
        if domain == "report":
            setattr(row, "formula" if mutation == "definition" else "row_name", "8" if mutation == "definition" else "结构变更")
        else:
            patch = {"formula": "8"} if mutation == "definition" else {"_structure": {"row_name": "结构变更"}}
            row.definition = {**row.definition, **patch}
        await editor.commit()
        after = (await store.list_global(editor, global_scope(domain, STD)))[slot]
        assert before.version == after.version
        assert (before.definition, before.structure) != (after.definition, after.structure)
        return after


@pytest.mark.parametrize("rollback", [False, True], ids=["publish", "rollback"])
@pytest.mark.parametrize("domain", ["report", "tb_detail"])
@pytest.mark.parametrize("mutation", ["definition", "structure"])
@pytest.mark.parametrize("subscribe", [False, True], ids=["no-subscriber", "subscribed"])
async def test_same_version_global_content_change_invalidates_evidence(api, rollback, domain, mutation, subscribe):
    tid, endpoint, body = await prepare(api, rollback=rollback, domains=(domain,), subscribe=subscribe)
    await global_save(api, domain)
    stale, _ = await preview(api, tid, body, rollback=rollback)
    upstream = await mutate_global_without_version(api, domain, mutation)
    fresh, _ = await reject_stale_and_repreview(api, tid, endpoint, body, stale)
    response = await api["c"].post(f"/api/formula-templates/{tid}/{endpoint}", json=fresh)
    assert response.status_code == 200, response.text
    async with api["f"]() as db:
        row = (await db.execute(sa.select(FormulaSetting).where(
            FormulaSetting.layer == "template", FormulaSetting.template_id == uuid.UUID(tid),
            FormulaSetting.domain == domain, FormulaSetting.slot_key == upstream.slot_key))).scalar_one()
        expected_base = {key: value for key, value in upstream.definition.items() if key != "_structure"}
        assert row.base_definition == expected_base and row.base_version == upstream.version

@pytest.mark.parametrize("rollback", [False, True], ids=["publish", "rollback"])
@pytest.mark.parametrize("domain", ["report", "tb_detail"])
@pytest.mark.parametrize("unrelated", ["slot", "scope"])
async def test_unrelated_global_change_keeps_preview_valid(api, rollback, domain, unrelated):
    tid, endpoint, body = await prepare(api, rollback=rollback, domains=(domain,), subscribe=False)
    stale, _ = await preview(api, tid, body, rollback=rollback)
    slot = SLOT if domain == "report" else "1001"
    scope = global_scope(domain, STD)
    if unrelated == "slot":
        slot = SLOT2 if domain == "report" else "1002"
    else:
        scope = "listed_standalone" if scope != "listed_standalone" else "soe_standalone"
    async with api["f"]() as editor:
        await get_store(domain).write_global(editor, scope, slot, {"formula": "77"}, user_id=None)
        await editor.commit()
    fresh, _ = await preview(api, tid, body, rollback=rollback)
    assert fresh["preview_fingerprint"] == stale["preview_fingerprint"]
    response = await api["c"].post(f"/api/formula-templates/{tid}/{endpoint}", json=stale)
    assert response.status_code == 200, response.text
    assert response.json()["version"] == body["expected_version"] + 1
