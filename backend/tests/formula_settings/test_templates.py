"""公式模板端到端（服务层，tasks 7.1~7.4）：保存 → 订阅（含冲突）→ 全局发布跳过模板位 → 发布新版本（跟随 /
冲突 / 暂缓）→ 处理待确认后订阅跟上 → 退订两种方式 → 删除约束 → 与全局不一致提示 → 设为全局 / 全局候选。"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from app.models.formula_setting_models import (
    FormulaPublish,
    FormulaSetting,
    FormulaTemplateSubscription,
    FormulaTemplateVersion,
)
from app.services.formula_settings import template_service as svc
from app.services.formula_settings import template_sync as sync
from app.services.formula_settings.apply_ops import review_candidate
from app.services.formula_settings.effective import effective_slots
from app.services.formula_settings.effective_report import load_effective_report_configs
from app.services.formula_settings.engine import Decisions
from app.services.formula_settings.errors import FormulaSettingError, VersionConflict, VersionRequired
from app.services.formula_settings.project_ops import resolve_items
from app.services.formula_settings.publish import publish_global
from app.services.formula_settings.template_access import Viewer

from ._env import STD, add_global_row, add_project, add_project_row, add_user, make_db, pending_items, project_rows

SLOT, SLOT2 = "balance_sheet:BS-001", "balance_sheet:BS-002"
OLD, MINE, THEIRS, V2, G2 = ("TB('1001','期末余额')", "TB('1001','期末余额')*2", "TB('1002','期末余额')",
                             "TB('1001','期末余额')*3", "TB('1001','审定数')")


def rdef(f: str) -> dict:
    return {"formula": f}


async def _sub(db, project_id) -> FormulaTemplateSubscription | None:
    return (await db.execute(sa.select(FormulaTemplateSubscription).where(
        FormulaTemplateSubscription.project_id == project_id).order_by(
        FormulaTemplateSubscription.subscribed_at.desc()))).scalars().first()


async def _formula(db, project_id, code="BS-001") -> str | None:
    configs = await load_effective_report_configs(db, standard=STD, project_id=project_id)
    return next((c.formula for c in configs if c.row_code == code), None)


@pytest.fixture
async def world():
    async with make_db() as factory, factory() as db:
        admin, owner, other = await add_user(db, "adm", "admin"), await add_user(db, "own"), await add_user(db, "x")
        await add_global_row(db, "BS-001", OLD)
        await add_global_row(db, "BS-002", OLD, row_number=2)
        src = await add_project(db, "来源")
        await add_project_row(db, src, "BS-001", MINE, base_formula=OLD)
        follower, keeper, deferrer = [await add_project(db, n) for n in ("跟随", "自改", "暂缓")]
        await add_project_row(db, keeper, "BS-001", THEIRS, base_formula=OLD)
        yield {"db": db, "admin": admin, "owner": owner, "other": other, "src": src, "follower": follower,
               "keeper": keeper, "deferrer": deferrer}


async def _template(w, **kw):
    viewer = await Viewer.load(w["db"], w["owner"])
    return await svc.create_template(w["db"], viewer=viewer, name="集团报表口径", description=None,
                                     share_scope="personal", owner_project_id=None, applicable_scope="",
                                     source="project", domains=["report"], source_project_id=w["src"], **kw)


async def test_save_subscribe_publish_unsubscribe_end_to_end(world):
    w = world
    db = w["db"]
    tpl = await _template(w)
    assert tpl.applicable_scope == STD and tpl.version == 1, "来源项目的准则作为适用范围"
    rows = (await db.execute(sa.select(FormulaSetting).where(FormulaSetting.layer == "template"))).scalars().all()
    assert [(r.slot_key, r.definition["formula"], r.base_definition["formula"]) for r in rows] == [(SLOT, MINE, OLD)], \
        "未指定公式位：只取本项目自己的定义；基线记当时的全局"
    assert (await db.execute(sa.select(FormulaTemplateVersion.version))).scalars().all() == [1]

    # 订阅：直接生效（物化）/ 冲突（保留本项目）
    pre = await sync.subscribe_preview(db, project_id=w["follower"], tpl=tpl, domain="report")
    assert pre["summary"]["counts"]["inherit"] == 1 and len(pre["items"]) == 1
    await sync.subscribe(db, project_id=w["follower"], tpl=tpl, domain="report", decisions=None, user_id=w["owner"].id)
    row = (await project_rows(db, w["follower"]))["BS-001"]
    assert (row.formula, row.base_origin, row.base_template_id) == (MINE, "template", tpl.id)
    assert await _formula(db, w["follower"]) == MINE, "报表取数读到模板定义"
    assert (await effective_slots(db, "report", w["follower"]))[SLOT].layer == "template"
    keep = Decisions(conflict_choices={f"{w['keeper']}|{SLOT}": "keep"})
    out = await sync.subscribe(db, project_id=w["keeper"], tpl=tpl, domain="report", decisions=keep,
                               user_id=w["owner"].id)
    assert out["summary"]["counts"]["conflict"] == 1
    kept = (await project_rows(db, w["keeper"]))["BS-001"]
    assert (kept.formula, kept.base_definition["formula"], kept.base_origin) == (THEIRS, MINE, "template")
    await sync.subscribe(db, project_id=w["deferrer"], tpl=tpl, domain="report", decisions=None, user_id=w["owner"].id)
    with pytest.raises(FormulaSettingError):
        await sync.subscribe(db, project_id=w["follower"], tpl=tpl, domain="report", decisions=None, user_id=None)

    # 全局发布：模板定义的公式位在订阅项目里不变
    g = await publish_global(db, domain="report", scope=STD, user_id=w["admin"].id,
                             changes=[{"slot_key": SLOT, "definition": rdef(G2), "expected_version": 1}])
    assert g["summary"]["counts"]["template"] == 3 and await _formula(db, w["follower"]) == MINE
    hints = (await svc.template_detail(db, tpl, viewer=await Viewer.load(db, w["owner"])))["global_hints"]
    assert [(h["slot_key"], h["global_definition"]["formula"]) for h in hints] == [(SLOT, G2)], "模板与新全局不一致提示"

    # 发布新版本：跟随的自动更新、改过的冲突待确认、暂缓的固定旧版本
    with pytest.raises(VersionRequired):
        await sync.publish_template(db, tpl, changes=[{"domain": "report", "slot_key": SLOT, "definition": rdef(V2)}],
                                    expected_version=None, user_id=w["owner"].id)
    with pytest.raises(VersionConflict):
        await sync.publish_template(db, tpl, changes=[{"domain": "report", "slot_key": SLOT, "definition": rdef(V2)}],
                                    expected_version=9, user_id=w["owner"].id)
    preview = await sync.publish_preview(db, tpl, expected_version=1, changes=[
        {"domain": "report", "slot_key": SLOT, "definition": rdef(V2)},
        {"domain": "report", "slot_key": SLOT2, "definition": rdef("ROW('BS-001')")}])
    assert preview["next_version"] == 2 and preview["summary"]["conflict_count"] == 1
    defer = Decisions(project_choices={str(w["deferrer"]): "defer"})
    res = await sync.publish_template(db, tpl, expected_version=1, user_id=w["owner"].id, decisions=defer, changes=[
        {"domain": "report", "slot_key": SLOT, "definition": rdef(V2)},
        {"domain": "report", "slot_key": SLOT2, "definition": rdef("ROW('BS-001')")}])
    assert res["version"] == 2 and tpl.version == 2
    assert await _formula(db, w["follower"]) == V2 and await _formula(db, w["follower"], "BS-002") == "ROW('BS-001')"
    assert (await project_rows(db, w["keeper"]))["BS-001"].formula == THEIRS
    (kitem,) = await pending_items(db, w["keeper"])
    assert (kitem.upstream_origin, kitem.upstream_template_id, kitem.upstream_definition["formula"]) == (
        "template", tpl.id, V2)
    assert await _formula(db, w["deferrer"]) == MINE and (await _sub(db, w["deferrer"])).pinned
    assert (await _sub(db, w["follower"])).template_version == 2
    items = await pending_items(db, w["deferrer"])
    assert {i.reason for i in items} == {"deferred"} and len(items) == 2
    await resolve_items(db, project_id=w["deferrer"], user_id=w["owner"].id,
                        resolutions=[{"item_id": str(i.id), "choice": "adopt", "revision": i.revision} for i in items])
    sub = await _sub(db, w["deferrer"])
    assert (sub.pinned, sub.template_version) == (False, 2) and await _formula(db, w["deferrer"]) == V2

    # 删除：还有订阅 → 409
    with pytest.raises(FormulaSettingError) as exc:
        await svc.delete_template(db, tpl, user_id=w["owner"].id)
    assert exc.value.status_code == 409

    # 退订：回到全局（没改过 ⇒ 回到继承）/ 保留模板公式（改记为本项目适配，此后全局发布照常同步）
    await sync.unsubscribe(db, project_id=w["follower"], domain="report", mode="global", decisions=None,
                           user_id=w["owner"].id)
    assert "BS-001" not in await project_rows(db, w["follower"]) and await _formula(db, w["follower"]) == G2
    await sync.unsubscribe(db, project_id=w["keeper"], domain="report", mode="keep", decisions=None,
                           user_id=w["owner"].id)
    kept = (await project_rows(db, w["keeper"]))["BS-001"]
    assert (kept.formula, kept.base_origin, kept.base_template_id, kept.base_definition["formula"]) == (
        THEIRS, "global", None, G2)
    assert await pending_items(db, w["keeper"]) == [], "模板来的待确认事项退订后结案"
    g3 = await publish_global(db, domain="report", scope=STD, user_id=w["admin"].id,
                              changes=[{"slot_key": SLOT, "definition": rdef(OLD), "expected_version": 2}])
    per = {p["project_id"]: p["counts"] for p in g3["summary"]["projects"]}
    assert per[str(w["keeper"])]["conflict"] == 1, "退订后本项目适配参与全局同步（不再被当模板位跳过）"
    assert per[str(w["deferrer"])]["template"] == 1, "仍订阅的项目照旧跳过"
    await sync.unsubscribe(db, project_id=w["deferrer"], domain="report", mode="global", decisions=None, user_id=None)
    await svc.delete_template(db, tpl, user_id=w["owner"].id)
    assert tpl.is_deleted


async def test_pending_and_deferred_template_slots_stay_template_layer(world):
    """订阅冲突未决、发布新版本被暂缓的公式位：仍算模板层 —— 全局发布跳过它，不改写模板来的待确认。"""
    w = world
    db = w["db"]
    tpl = await _template(w)
    await sync.subscribe(db, project_id=w["keeper"], tpl=tpl, domain="report", decisions=None, user_id=None)
    (item,) = await pending_items(db, w["keeper"])
    assert (item.upstream_origin, (await project_rows(db, w["keeper"]))["BS-001"].base_origin) == ("template",
                                                                                                    "template")
    await sync.subscribe(db, project_id=w["deferrer"], tpl=tpl, domain="report", decisions=None, user_id=None)
    await sync.publish_template(db, tpl, expected_version=1, user_id=None,
                                decisions=Decisions.parse({"project_choices": {str(w["deferrer"]): "defer"}}),
                                changes=[{"domain": "report", "slot_key": SLOT2, "definition": rdef("ROW('BS-001')")}])
    pinned = (await project_rows(db, w["deferrer"]))["BS-002"]
    assert (pinned.pinned, pinned.base_origin, pinned.formula) == (True, "template", OLD)
    g = await publish_global(db, domain="report", scope=STD, user_id=w["admin"].id, changes=[
        {"slot_key": SLOT, "definition": rdef(G2), "expected_version": 1},
        {"slot_key": SLOT2, "definition": rdef(G2), "expected_version": 1}])
    per = {p["project_id"]: p["counts"] for p in g["summary"]["projects"]}
    # 自改项目：BS-001 冲突未决（改记模板层）+ BS-002 新版本物化；暂缓项目：BS-001 物化 + BS-002 固定
    assert per[str(w["keeper"])]["template"] == 2 and per[str(w["deferrer"])]["template"] == 2
    assert per[str(w["keeper"])]["conflict"] == 0 and per[str(w["deferrer"])]["pinned"] == 0
    (item,) = await pending_items(db, w["keeper"])
    assert (item.upstream_origin, item.upstream_definition["formula"]) == ("template", MINE)


async def test_unsubscribe_global_asks_for_modified_slots(world):
    w = world
    db = w["db"]
    tpl = await _template(w)
    await sync.subscribe(db, project_id=w["follower"], tpl=tpl, domain="report", decisions=None, user_id=None)
    lo = (await project_rows(db, w["follower"]))["BS-001"]
    lo.formula = "TB('9999','期末余额')"  # 订阅后本项目又改了（不经内核直接改值即可模拟）
    await db.flush()
    pre = await sync.unsubscribe_preview(db, project_id=w["follower"], domain="report", mode="global")
    assert pre["summary"]["conflict_count"] == 1
    await sync.unsubscribe(db, project_id=w["follower"], domain="report", mode="global", decisions=None, user_id=None)
    (item,) = await pending_items(db, w["follower"])
    row = (await project_rows(db, w["follower"]))["BS-001"]
    assert (item.upstream_origin, item.upstream_definition["formula"]) == ("global", OLD)
    assert (row.formula, row.base_origin, row.base_template_id) == ("TB('9999','期末余额')", "global", None)


async def test_template_from_global_and_manual_validation(world):
    w = world
    db = w["db"]
    viewer = await Viewer.load(db, w["admin"])
    tpl = await svc.create_template(db, viewer=viewer, name="全局副本", description="", share_scope="firm",
                                    owner_project_id=None, applicable_scope=STD, source="global", domains=["report"])
    assert sorted(r.slot_key for r in (await svc.template_definitions(db, tpl))["report"].values()) == [SLOT, SLOT2]
    with pytest.raises(FormulaSettingError):  # 事务所模板仅 admin
        await svc.create_template(db, viewer=await Viewer.load(db, w["owner"]), name="x", description=None,
                                  share_scope="firm", owner_project_id=None, applicable_scope=STD, source="global",
                                  domains=["report"])
    with pytest.raises(FormulaSettingError):  # 底稿公式按域校验
        await svc.create_template(db, viewer=viewer, name="坏", description=None, share_scope="personal",
                                  owner_project_id=None, applicable_scope="", source="manual", domains=["wp"],
                                  items=[{"domain": "wp", "slot_key": "D2|审定表|E8",
                                          "definition": {"expression": "eval('x')"}}])
    with pytest.raises(FormulaSettingError):
        await svc.create_template(db, viewer=viewer, name="空", description=None, share_scope="personal",
                                  owner_project_id=None, applicable_scope="", source="project", domains=["report"],
                                  source_project_id=w["follower"])


async def test_promote_admin_publishes_and_candidate_reviewed(world):
    w = world
    db = w["db"]
    tpl = await _template(w)
    pre = await svc.promote_preview(db, tpl, domain="report")
    assert [(c["slot_key"], c["new"]["formula"]) for c in pre["changes"]] == [(SLOT, MINE)]
    owner = await Viewer.load(db, w["owner"])
    cand = await svc.promote(db, tpl, viewer=owner, domain="report")
    row = await db.get(FormulaPublish, uuid.UUID(cand["candidate"]["id"]))
    assert (row.status, row.template_id, row.target) == ("pending", tpl.id, "global")
    assert await _formula(db, w["follower"]) == OLD, "提交候选不改全局"
    out = await review_candidate(db, publish_id=row.id, approve=True, user_id=w["admin"].id)
    assert out["candidate"]["status"] == "published" and await _formula(db, w["follower"]) == MINE
    admin = await Viewer.load(db, w["admin"])
    res = await svc.promote(db, tpl, viewer=admin, domain="report")
    assert res["template_id"] == str(tpl.id) and res["events"] == [], "已与全局相同：管理员设为全局不改动"


async def _audit(db):
    from ._env import audit_actions

    return await audit_actions(db)


async def test_update_meta_rename_share_scope_and_locked_applicable_scope(world):
    w = world
    db = w["db"]
    tpl = await _template(w)  # personal / 来源项目准则
    owner = await Viewer.load(db, w["owner"])
    admin = await Viewer.load(db, w["admin"])
    await svc.update_meta(db, tpl, viewer=owner, changes={"name": "改了名", "description": "说明"})
    assert (tpl.name, tpl.description) == ("改了名", "说明")
    with pytest.raises(FormulaSettingError):  # 名称不能空
        await svc.update_meta(db, tpl, viewer=owner, changes={"name": "  "})
    # 个人 → 事务所：仅 admin
    with pytest.raises(FormulaSettingError):
        await svc.update_meta(db, tpl, viewer=owner, changes={"share_scope": "firm"})
    await svc.update_meta(db, tpl, viewer=admin, changes={"share_scope": "firm"})
    assert (tpl.share_scope, tpl.owner_project_id) == ("firm", None)
    # 改共享范围为集团须带所属项目
    with pytest.raises(FormulaSettingError):
        await svc.update_meta(db, tpl, viewer=admin, changes={"share_scope": "group", "owner_project_id": None})
    await svc.update_meta(db, tpl, viewer=admin, changes={"share_scope": "group", "owner_project_id": w["src"]})
    assert (tpl.share_scope, tpl.owner_project_id) == ("group", w["src"])
    actions = [a for a, _ in await _audit(db)]
    assert actions.count("formula.template_updated") >= 3


async def test_update_meta_applicable_scope_locked_when_subscribed(world):
    w = world
    db = w["db"]
    tpl = await _template(w)
    owner = await Viewer.load(db, w["owner"])
    await sync.subscribe(db, project_id=w["follower"], tpl=tpl, domain="report", decisions=None, user_id=None)
    with pytest.raises(FormulaSettingError) as exc:  # 有订阅 ⇒ 改适用准则 409
        await svc.update_meta(db, tpl, viewer=owner, changes={"applicable_scope": "listed_standalone"})
    assert exc.value.status_code == 409
    # 没动适用准则的改名仍可
    await svc.update_meta(db, tpl, viewer=owner, changes={"name": "仍可改名"})
    assert tpl.name == "仍可改名"


async def test_candidate_reject_is_audited(world):
    w = world
    db = w["db"]
    tpl = await _template(w)
    owner = await Viewer.load(db, w["owner"])
    cand = await svc.promote(db, tpl, viewer=owner, domain="report")
    row = await db.get(FormulaPublish, uuid.UUID(cand["candidate"]["id"]))
    submitted = [a for a, _ in await _audit(db)]
    assert "formula.template_candidate" in submitted
    out = await review_candidate(db, publish_id=row.id, approve=False, user_id=w["admin"].id, note="口径不对")
    assert out["candidate"]["status"] == "rejected"
    assert await _formula(db, w["follower"]) == OLD  # 驳回不改全局
    rejected = [a for a, _ in await _audit(db)]
    assert "formula.candidate_rejected" in rejected


async def test_generic_domain_tb_detail_template_subscribe_and_publish():
    """通用域（tb_detail）也能保存模板、订阅、发布新版本（task 7.3「报表域与通用域」）。"""
    async with make_db() as factory, factory() as db:
        from app.services.formula_settings import tb_detail

        admin = await add_user(db, "a2", "admin")
        src = await add_project(db, "通用源")
        follower = await add_project(db, "通用订阅")
        # 全局 tb_detail + 来源项目自己的适配
        await publish_global(db, domain="tb_detail", scope="*", user_id=admin.id, changes=[
            {"slot_key": "1001", "definition": {"row_name": "库存现金", "formula": "TB('1001','期末余额')",
                                                "formula_category": "auto_calc"}}])
        await db.flush()
        from app.services.formula_settings.project_ops import save_overrides

        await save_overrides(db, domain="tb_detail", project_id=src, user_id=admin.id, items=[
            {"slot_key": "1001", "definition": {"row_name": "库存现金", "formula": "TB('1001','期末余额')*2",
                                                "formula_category": "auto_calc"}}])
        await db.flush()
        viewer = await Viewer.load(db, admin)
        tpl = await svc.create_template(db, viewer=viewer, name="现金口径", description=None, share_scope="firm",
                                        owner_project_id=None, applicable_scope="*", source="project",
                                        domains=["tb_detail"], source_project_id=src)
        await sync.subscribe(db, project_id=follower, tpl=tpl, domain="tb_detail", decisions=None, user_id=admin.id)
        assert (await tb_detail.load(db, follower))["overrides"]["1001"]["formula"] == "TB('1001','期末余额')*2"
        assert (await tb_detail.load(db, follower))["overrides"]["1001"]["layer"] == "template"
        # 发布模板新版本 → 订阅项目（跟随）自动更新
        await sync.publish_template(db, tpl, expected_version=1, user_id=admin.id, changes=[
            {"domain": "tb_detail", "slot_key": "1001",
             "definition": {"row_name": "库存现金", "formula": "TB('1001','期末余额')*3",
                            "formula_category": "auto_calc"}}])
        assert (await tb_detail.load(db, follower))["overrides"]["1001"]["formula"] == "TB('1001','期末余额')*3"
