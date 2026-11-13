"""真实模板发布的受控双 Session 竞争；仅内存 SQLite，不声称实测 PG 锁阻塞。"""
from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest
import sqlalchemy as sa

from app.models.formula_setting_models import (
    FormulaPublish, FormulaSetting, FormulaTemplate, FormulaTemplateSubscription, FormulaTemplateVersion,
)
from app.models.report_models import ReportConfig
from app.services.formula_settings import project_ops, template_service, template_sync
from app.services.formula_settings.effective import effective_slots
from app.services.formula_settings.engine import Decisions
from app.services.formula_settings.errors import VersionConflict
from app.services.formula_settings.stores import get_store
from app.services.formula_settings.template_access import Viewer

from ._env import STD, add_global_row, add_project, add_user, make_db, pending_items

SLOTS = ("balance_sheet:BS-001", "balance_sheet:BS-002", "balance_sheet:BS-003")


def slot(domain, index=0):
    return SLOTS[index] if domain == "report" else str(1001 + index)


async def template(db, admin, *, domains=("report",), count=2, name="【测试】完整性模板"):
    return await template_service.create_template(
        db, viewer=await Viewer.load(db, admin), name=name, description=None, share_scope="personal",
        owner_project_id=None, applicable_scope=STD, source="manual", domains=list(domains),
        items=[{"domain": domain, "slot_key": slot(domain, i), "definition": {"formula": "10"}}
               for domain in domains for i in range(count)],
    )


async def subscription(db, pid, domain="report"):
    return (await db.execute(sa.select(FormulaTemplateSubscription).where(
        FormulaTemplateSubscription.project_id == pid, FormulaTemplateSubscription.domain == domain,
        FormulaTemplateSubscription.is_active == sa.true(),
    ))).scalar_one()


async def orm_local(db, domain, pid):
    if domain == "report":
        query = sa.select(ReportConfig).where(ReportConfig.applicable_standard == f"project:{pid}",
                                             ReportConfig.row_code == "BS-001")
    else:
        query = sa.select(FormulaSetting).where(FormulaSetting.domain == domain, FormulaSetting.layer == "project",
                                               FormulaSetting.project_id == pid, FormulaSetting.slot_key == slot(domain))
    return (await db.execute(query)).scalar_one()


@pytest.mark.parametrize("domain", ["report", "tb_detail"])
@pytest.mark.parametrize("choice", ["adopt", "keep"])
async def test_publish_rejects_local_commit_between_plan_and_project_lock(monkeypatch, domain, choice):
    async with make_db() as factory, factory() as publisher:
        admin = await add_user(publisher, "integrity_admin", "admin")
        pid = await add_project(publisher, "【测试】模板竞争")
        tpl = await template(publisher, admin, domains=(domain,), count=1)
        await template_sync.subscribe(publisher, project_id=pid, tpl=tpl, domain=domain,
                                      decisions=None, user_id=admin.id)
        await publisher.commit()
        held = await orm_local(publisher, domain, pid)
        original_lock = template_sync.lock_project
        local_saved = asyncio.Event()
        pause_at_lock = asyncio.Event()
        changes = [{"domain": domain, "slot_key": slot(domain), "definition": {"formula": "20"}}]
        decisions = Decisions(conflict_choices={f"{domain}|{pid}|{slot(domain)}": choice})
        initial_preview = await template_sync.publish_preview(publisher, tpl, changes=changes, expected_version=1)

        async def controlled_lock(db, seen_domain, seen_pid):
            assert db is publisher and (seen_domain, seen_pid) == (domain, pid)
            pause_at_lock.set()
            await asyncio.wait_for(local_saved.wait(), timeout=5)
            await original_lock(db, seen_domain, seen_pid)

        async def real_local_save():
            await asyncio.wait_for(pause_at_lock.wait(), timeout=5)
            async with factory() as editor:
                local = (await get_store(domain).list_project(editor, pid))[slot(domain)]
                await project_ops.save_overrides(editor, domain=domain, project_id=pid, user_id=None, items=[{
                    "slot_key": slot(domain), "definition": {"formula": "99"}, "expected_version": local.version}])
                await editor.commit()
            # 发布 Session 故意保留旧 ORM，验证取锁后的 SELECT 确实刷新了它。
            assert (held.formula if domain == "report" else held.definition["formula"]) == "10"
            local_saved.set()

        with monkeypatch.context() as timing:
            timing.setattr(template_sync, "lock_project", controlled_lock)
            publishing = asyncio.create_task(template_sync.publish_template(
                publisher, tpl, changes=changes, expected_version=1, decisions=decisions, user_id=None,
                preview_fingerprint=initial_preview["preview_fingerprint"]))
            editing = asyncio.create_task(real_local_save())
            result, edit_result = await asyncio.wait_for(
                asyncio.gather(publishing, editing, return_exceptions=True), timeout=15)
        assert edit_result is None
        assert isinstance(result, VersionConflict), repr(result)
        assert result.status_code == 409 and "重新预览" in str(result)
        assert tpl.version == 1
        assert (held.formula if domain == "report" else held.definition["formula"]) == "99"
        assert await publisher.scalar(sa.select(sa.func.count()).select_from(FormulaPublish)) == 0
        assert (await publisher.execute(sa.select(FormulaTemplateVersion.version))).scalars().all() == [1]
        stored = await publisher.scalar(sa.select(FormulaSetting).where(
            FormulaSetting.layer == "template", FormulaSetting.template_id == tpl.id,
            FormulaSetting.domain == domain, FormulaSetting.slot_key == slot(domain)))
        assert stored.definition["formula"] == "10"
        assert await pending_items(publisher, pid) == []
        preview = await template_sync.publish_preview(publisher, tpl, changes=changes, expected_version=1)
        assert [(i["local_formula"], i["category"]) for i in preview["items"]] == [("99", "conflict")]
        await publish_previewed(publisher, tpl, changes=changes, expected_version=1,
                                             decisions=decisions, user_id=None)
        assert (await get_store(domain).list_project(publisher, pid))[slot(domain)].definition["formula"] == (
            "20" if choice == "adopt" else "99")
        assert tpl.version == 2


async def test_publish_locks_only_effective_subscription_domains_once_in_stable_order(monkeypatch):
    async with make_db() as factory, factory() as db:
        admin = await add_user(db, "lock_admin", "admin")
        tpl = await template(db, admin, domains=("tb_detail", "report"))
        other = await template(db, admin, domains=("report", "tb_detail"), name="【测试】无关模板")
        both, reports, details, unrelated = [await add_project(db, name) for name in (
            "【测试】双域", "【测试】只报表", "【测试】只明细", "【测试】无关订阅")]
        pairs = [("tb_detail", both), ("report", reports), ("tb_detail", details), ("report", both)]
        for domain, pid in pairs:
            await template_sync.subscribe(db, project_id=pid, tpl=tpl, domain=domain, decisions=None, user_id=None)
        for domain in ("report", "tb_detail"):
            await template_sync.subscribe(db, project_id=unrelated, tpl=other, domain=domain,
                                          decisions=None, user_id=None)
        await db.commit()
        locks = []
        original_lock = template_sync.lock_project

        async def record_lock(session, domain, pid):
            locks.append((domain, str(pid)))
            await original_lock(session, domain, pid)

        monkeypatch.setattr(template_sync, "lock_project", record_lock)
        await publish_previewed(db, tpl, expected_version=1, user_id=None, changes=[
            {"domain": domain, "slot_key": slot(domain, i), "definition": {"formula": "20"}}
            for domain in ("tb_detail", "report") for i in range(2)])
        assert locks == sorted((domain, str(pid)) for domain, pid in pairs)
        assert len(locks) == 4, "两个公式位仍只锁一次项目/域，不锁无关模板的订阅项目"
        locks.clear()
        await publish_previewed(db, tpl, expected_version=2, user_id=None, changes=[
            {"domain": "report", "slot_key": slot("report"), "definition": {"formula": "30"}}])
        assert locks == sorted(("report", str(pid)) for pid in (both, reports))
        assert other.version == 1
        for domain in ("report", "tb_detail"):
            assert (await subscription(db, unrelated, domain)).template_version == 1
            assert (await effective_slots(db, domain, unrelated))[slot(domain)].definition["formula"] == "10"


async def publish_previewed(db, tpl, **kwargs):
    preview = await template_sync.publish_preview(db, tpl, changes=kwargs["changes"],
                                                  expected_version=kwargs["expected_version"])
    return await template_sync.publish_template(
        db, tpl, preview_fingerprint=preview["preview_fingerprint"], **kwargs)


def pending_snapshot(item):
    return deepcopy({name: getattr(item, name) for name in (
        "id", "slot_key", "revision", "base_definition", "local_definition", "upstream_definition",
        "upstream_version", "upstream_template_id", "upstream_origin", "reason", "publish_id", "status")})


@pytest.mark.parametrize("choice", ["adopt", "keep"])
async def test_deferred_a_pending_survives_later_b_only_publish(choice):
    async with make_db() as factory, factory() as db:
        admin = await add_user(db, "defer_admin", "admin")
        pid = await add_project(db, "【测试】逐位暂缓")
        tpl = await template(db, admin)
        await template_sync.subscribe(db, project_id=pid, tpl=tpl, domain="report", decisions=None, user_id=None)
        await publish_previewed(db, tpl, expected_version=1, user_id=None,
                                             decisions=Decisions(project_choices={str(pid): "defer"}), changes=[
            {"domain": "report", "slot_key": SLOTS[0], "definition": {"formula": "20"}}])
        (item,) = await pending_items(db, pid)
        before = pending_snapshot(item)
        assert item.upstream_version == 2 and item.upstream_definition["formula"] == "20"
        sub = await subscription(db, pid)
        assert (sub.pinned, sub.template_version) == (True, 1)
        await publish_previewed(db, tpl, expected_version=2, user_id=None, changes=[
            {"domain": "report", "slot_key": SLOTS[1], "definition": {"formula": "30"}}])
        await db.commit()
        await db.refresh(item)
        assert pending_snapshot(item) == before, "模板总版本升级不能偷换未改动 A 的待确认上游或修订号"
        assert (sub.pinned, sub.template_version, tpl.version) == (True, 1, 3)
        effective = await effective_slots(db, "report", pid)
        assert (effective[SLOTS[0]].definition["formula"], effective[SLOTS[1]].definition["formula"]) == ("10", "30")
        await project_ops.resolve_items(db, project_id=pid, user_id=None, resolutions=[{
            "item_id": str(item.id), "revision": item.revision, "choice": choice}])
        await db.commit()
        assert await pending_items(db, pid) == []
        assert (sub.pinned, sub.template_version) == (False, 3)
        effective = await effective_slots(db, "report", pid)
        assert effective[SLOTS[0]].definition["formula"] == ("20" if choice == "adopt" else "10")
        assert effective[SLOTS[0]].local.base_version == 2, "逐位基线仍是 A 的版本，不强改成模板总版本 3"
        assert effective[SLOTS[1]].definition["formula"] == "30"

@pytest.mark.parametrize("domain", ["report", "tb_detail"])
async def test_publish_refreshes_held_global_after_project_lock(monkeypatch, domain):
    async with make_db() as factory, factory() as publisher:
        admin = await add_user(publisher, "upstream_admin", "admin")
        pid = await add_project(publisher, "【测试】锁间全局变更")
        store = get_store(domain)
        scope = template_service.global_scope(domain, STD)
        if domain == "report":
            await add_global_row(publisher, "BS-001", "5")
        else:
            await store.write_global(publisher, scope, slot(domain), {"formula": "5"}, user_id=None)
        tpl = await template(publisher, admin, domains=(domain,), count=1)
        await template_sync.subscribe(publisher, project_id=pid, tpl=tpl, domain=domain,
                                      decisions=None, user_id=None)
        await publisher.commit()
        upstream = (await store.list_global(publisher, scope))[slot(domain)]
        model = ReportConfig if domain == "report" else FormulaSetting
        held = await publisher.get(model, upstream.row_id)
        changes = [{"domain": domain, "slot_key": slot(domain), "definition": {"formula": "20"}}]
        old = await template_sync.publish_preview(publisher, tpl, changes=changes, expected_version=1)
        original_lock = template_sync.lock_project
        lock_calls, versions = [], []

        async def commit_global_at_lock(db, seen_domain, seen_pid):
            assert db is publisher and (seen_domain, seen_pid) == (domain, pid)
            lock_calls.append((seen_domain, seen_pid))
            async with factory() as editor:
                versions.append(await store.write_global(
                    editor, scope, slot(domain), {"formula": "7"}, user_id=None))
                await editor.commit()
            assert (held.formula if domain == "report" else held.definition["formula"]) == "5"
            await original_lock(db, seen_domain, seen_pid)

        with monkeypatch.context() as timing:
            timing.setattr(template_sync, "lock_project", commit_global_at_lock)
            with pytest.raises(VersionConflict, match="重新预览") as rejected:
                await template_sync.publish_template(
                    publisher, tpl, changes=changes, expected_version=1, user_id=None,
                    preview_fingerprint=old["preview_fingerprint"])
        assert rejected.value.status_code == 409 and lock_calls == [(domain, pid)]
        assert (held.formula if domain == "report" else held.definition["formula"]) == "7"
        assert tpl.version == 1
        assert await publisher.scalar(sa.select(sa.func.count()).select_from(FormulaPublish)) == 0
        assert (await publisher.execute(sa.select(FormulaTemplateVersion.version))).scalars().all() == [1]
        stored = await publisher.scalar(sa.select(FormulaSetting).where(
            FormulaSetting.layer == "template", FormulaSetting.template_id == tpl.id,
            FormulaSetting.domain == domain, FormulaSetting.slot_key == slot(domain)))
        assert stored.definition["formula"] == "10" and stored.base_definition["formula"] == "5"
        assert await pending_items(publisher, pid) == []
        assert (await store.list_project(publisher, pid))[slot(domain)].definition["formula"] == "10"
        fresh = await template_sync.publish_preview(publisher, tpl, changes=changes, expected_version=1)
        assert fresh["preview_fingerprint"] != old["preview_fingerprint"]
        await template_sync.publish_template(
            publisher, tpl, changes=changes, expected_version=1, user_id=None,
            preview_fingerprint=fresh["preview_fingerprint"])
        assert tpl.version == 2 and stored.base_definition["formula"] == "7"
        assert stored.base_version == versions[0]
        assert (await store.list_project(publisher, pid))[slot(domain)].definition["formula"] == "20"

@pytest.mark.parametrize("domain", ["report", "tb_detail"])
async def test_unsubscribed_publish_refreshes_held_global_without_project_locks(monkeypatch, domain):
    async with make_db() as factory, factory() as publisher:
        admin = await add_user(publisher, "unsubscribed_admin", "admin")
        store, scope = get_store(domain), template_service.global_scope(domain, STD)
        if domain == "report":
            await add_global_row(publisher, "BS-001", "5")
        else:
            await store.write_global(publisher, scope, slot(domain), {"formula": "5"}, user_id=None)
        tpl = await template(publisher, admin, domains=(domain,), count=1)
        await publisher.commit()
        upstream = (await store.list_global(publisher, scope))[slot(domain)]
        held = await publisher.get(ReportConfig if domain == "report" else FormulaSetting, upstream.row_id)
        changes = [{"domain": domain, "slot_key": slot(domain), "definition": {"formula": "20"}}]
        old = await template_sync.publish_preview(publisher, tpl, changes=changes, expected_version=1)
        async with factory() as editor:
            version = await store.write_global(editor, scope, slot(domain), {"formula": "7"}, user_id=None)
            await editor.commit()
        assert (held.formula if domain == "report" else held.definition["formula"]) == "5"

        async def unexpected_project_lock(*args):
            pytest.fail("没有订阅者时不得额外获取项目锁")

        monkeypatch.setattr(template_sync, "lock_project", unexpected_project_lock)
        with pytest.raises(VersionConflict, match="重新预览"):
            await template_sync.publish_template(
                publisher, tpl, changes=changes, expected_version=1, user_id=None,
                preview_fingerprint=old["preview_fingerprint"])
        assert (held.formula if domain == "report" else held.definition["formula"]) == "7"
        assert tpl.version == 1
        assert await publisher.scalar(sa.select(sa.func.count()).select_from(FormulaPublish)) == 0
        await publish_previewed(publisher, tpl, changes=changes, expected_version=1, user_id=None)
        stored = await publisher.scalar(sa.select(FormulaSetting).where(
            FormulaSetting.layer == "template", FormulaSetting.template_id == tpl.id,
            FormulaSetting.domain == domain, FormulaSetting.slot_key == slot(domain)))
        assert tpl.version == 2 and stored.base_definition["formula"] == "7"
        assert stored.base_version == version
