"""冲突决策键带域（spec formula-hub-integrity-closure 需求 8.4；ADR-FHIC-11；F15）。

决策键 = ``{域}|{项目 id}|{公式位}``，解析 ``split('|', 2)``（公式位可含 ``|``）；首段不是已知域的旧两段键
``{项目 id}|{公式位}`` 仍识别、对当前域生效；同一身份两种键都有时三段键优先。生产函数一律不 mock
（SQLite 真 ORM，``tests/formula_settings/_env``）。

一、键：7 个域 × 5 种公式位（含 0~3 个 ``|``、以域名开头）拼接与解析往返；旧键；格式不全 ⇒ None。
二、``Decisions``（路由入口 ``Decisions.parse``）：三段键只对本域生效；旧键对任一当前域生效；三段键优先。
三、模板发布新版本（多域）：试算表明细与附注两个域都有公式位 ``五、1|4:1``，甲乙两个项目都订阅了两个域且都改过
   ⇒ 4 处冲突，预览 4 个 key 互不相同且解析回条目身份。甲：明细「采用」、附注「交项目确认」（三段键，默认「保留」）；
   乙：只给旧键「采用」⇒ 两个域都采用。落地：甲明细换新、附注不变且只有这一条待确认；乙两个域都换新；
   摘要 pending_total = 1（甲 1 / 乙 0），changed_projects 含甲乙，事件按域列出。
四、应用到指定项目（附注域）：预览 key 三段；本域三段键、旧键生效，他域三段键不生效（按默认交确认）。
五、全局发布（试算表明细，公式位含两个 ``|``）：同四。
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from app.models.formula_setting_models import FormulaSyncItem
from app.services.formula_settings import template_service as tpl_service
from app.services.formula_settings import template_sync
from app.services.formula_settings.apply_ops import apply_preview, apply_to_projects
from app.services.formula_settings.definitions import DOMAINS
from app.services.formula_settings.engine import KNOWN_DOMAINS, Decisions, decision_key, parse_decision_key
from app.services.formula_settings.publish import preview_global, publish_global
from app.services.formula_settings.stores import get_store
from app.services.formula_settings.sync import ConflictChoice
from app.services.formula_settings.template_access import Viewer
from tests.formula_settings._env import add_project, add_user, make_db

SLOT = "五、1|4:1"  # 附注公式位格式「章节|目标单元格」；试算表明细域（通用存储）同名
WP_LIKE = "FH-T7|审定表|B5"
SLOT_SHAPES = ["1001", SLOT, "D1|审定表|B5", "S|1|2|3", "report|x"]
TB, NOTE = "tb_detail", "note"


def _def(domain: str, formula: str) -> dict:
    return {"formula": formula, ("formula_category" if domain == TB else "category"): "auto_calc"}


# ─── 一、键 ─────────────────────────────────────────────────────────────────


def test_known_domains_are_the_registry_and_never_look_like_project_ids() -> None:
    assert KNOWN_DOMAINS == set(DOMAINS) == {"report", "tb_detail", "cross_check", "wp", "note", "consol_note",
                                             "push"}
    for domain in KNOWN_DOMAINS:  # 旧键识别的前提：项目 id（UUID）不可能是域名，域名也不含分隔符
        assert "|" not in domain
        with pytest.raises(ValueError):
            uuid.UUID(domain)


@pytest.mark.parametrize("slot", SLOT_SHAPES)
@pytest.mark.parametrize("domain", sorted(KNOWN_DOMAINS))
def test_three_part_key_round_trip(domain: str, slot: str) -> None:
    pid = uuid.uuid4()
    key = decision_key(domain, pid, slot)
    assert key == f"{domain}|{pid}|{slot}"
    assert parse_decision_key(key) == (domain, str(pid), slot)


@pytest.mark.parametrize("slot", SLOT_SHAPES)
def test_legacy_two_part_key_has_no_domain(slot: str) -> None:
    pid = uuid.uuid4()
    assert parse_decision_key(f"{pid}|{slot}") == (None, str(pid), slot)


@pytest.mark.parametrize("key", ["", "1001", "|1001", "{pid}|", "report|{pid}", "report||1001", "report|{pid}|"])
def test_incomplete_keys_parse_to_none(key: str) -> None:
    assert parse_decision_key(key.format(pid=uuid.uuid4())) is None


# ─── 二、Decisions ──────────────────────────────────────────────────────────


def test_decisions_scope_three_part_keys_to_their_domain_and_fall_back_to_legacy() -> None:
    pid, other = uuid.uuid4(), uuid.uuid4()
    raw = {decision_key(NOTE, pid, SLOT): "adopt", f"{pid}|{SLOT}": "keep", decision_key(TB, other, SLOT): "adopt"}
    for decisions in (Decisions.parse({"conflict_choices": raw, "default_conflict": "ask"}),
                      Decisions(conflict_choices=raw)):
        assert decisions.conflict_for(NOTE, pid, SLOT) is ConflictChoice.ADOPT, "三段键优先于同一身份的旧键"
        assert decisions.conflict_for(TB, pid, SLOT) is ConflictChoice.KEEP, "本域没有三段键 ⇒ 旧键"
        assert decisions.conflict_for("wp", pid, SLOT) is ConflictChoice.KEEP, "旧键对任一当前域生效"
        assert decisions.conflict_for(TB, other, SLOT) is ConflictChoice.ADOPT
        assert decisions.conflict_for(NOTE, other, SLOT) is ConflictChoice.ASK, "他域三段键不生效"
        assert decisions.conflict_for(TB, other, "五、1") is ConflictChoice.ASK, "公式位按全文比较（含 |）"


# ─── 三、模板发布新版本（多域） ──────────────────────────────────────────────


async def _rewrite_local(db, project_id: uuid.UUID, domain: str, definition: dict) -> None:
    """项目改过：只换本项目定义，基线 / 来源（模板）不动。"""
    store = get_store(domain)
    lo = (await store.list_project(db, project_id))[SLOT]
    await store.write_project(db, project_id, SLOT, definition=definition, base_definition=lo.base_definition,
                              base_version=lo.base_version, pinned=False, base_origin=lo.base_origin,
                              base_template_id=lo.base_template_id, user_id=None, label=lo.label)


async def _formula(db, project_id: uuid.UUID, domain: str, slot: str = SLOT) -> str:
    return (await get_store(domain).list_project(db, project_id))[slot].definition["formula"]


async def _pending(db) -> list[tuple]:
    rows = (await db.execute(sa.select(FormulaSyncItem).where(FormulaSyncItem.status == "pending"))).scalars()
    return sorted((str(r.project_id), r.domain, r.slot_key, r.reason) for r in rows)


def _identities(items: list[dict]) -> list[tuple]:
    return sorted((i["domain"], i["project_id"], i["slot_key"]) for i in items)


async def test_template_publish_two_domains_same_slot_decide_separately() -> None:
    async with make_db() as factory, factory() as db:
        admin = await add_user(db, "adm", "admin")
        jia, yi = await add_project(db, "甲"), await add_project(db, "乙")
        tpl = await tpl_service.create_template(
            db, viewer=await Viewer.load(db, admin), name="两域同名", description=None, share_scope="firm",
            owner_project_id=None, applicable_scope="", source="manual", domains=[TB, NOTE],
            items=[{"domain": d, "slot_key": SLOT, "definition": _def(d, "ROW(1)")} for d in (TB, NOTE)])
        for pid in (jia, yi):
            for domain in (TB, NOTE):
                await template_sync.subscribe(db, project_id=pid, tpl=tpl, domain=domain, decisions=None,
                                              user_id=admin.id)
                await _rewrite_local(db, pid, domain, _def(domain, "ROW(2)"))
        await db.commit()
        changes = [{"domain": d, "slot_key": SLOT, "definition": _def(d, "ROW(3)")} for d in (TB, NOTE)]

        preview = await template_sync.publish_preview(db, tpl, changes=changes, expected_version=1)
        assert [i["category"] for i in preview["items"]] == ["conflict"] * 4

        decisions = Decisions.parse({"default_conflict": "keep", "conflict_choices": {
            decision_key(TB, jia, SLOT): "adopt", decision_key(NOTE, jia, SLOT): "ask", f"{yi}|{SLOT}": "adopt"}})
        res = await template_sync.publish_template(db, tpl, changes=changes, expected_version=1, user_id=admin.id,
                                                   decisions=decisions)
        await db.commit()
        assert [await _formula(db, jia, d) for d in (TB, NOTE)] == ["ROW(3)", "ROW(2)"], "甲：明细采用、附注交确认"
        assert [await _formula(db, yi, d) for d in (TB, NOTE)] == ["ROW(3)", "ROW(3)"], "乙：旧键对两个域都生效"
        assert await _pending(db) == [(str(jia), NOTE, SLOT, "conflict")]
        # 摘要按条目自己的结果计数（outcomes 键带域；共用「项目|公式位」时后一个域会盖掉前一个）
        summary = res["summary"]
        assert (summary["counts"]["conflict"], summary["pending_total"]) == (4, 1)
        assert {p["project_id"]: p["pending"] for p in summary["projects"]} == {str(jia): 1, str(yi): 0}
        assert set(summary["changed_projects"]) == {str(jia), str(yi)}
        assert sorted((e["project_id"], e["domain"], tuple(e["slot_keys"])) for e in res["events"]) == sorted(
            [(str(jia), TB, (SLOT,)), (str(yi), TB, (SLOT,)), (str(yi), NOTE, (SLOT,))])
        # 预览 key：4 条互不相同，解析回条目自己的（域, 项目, 公式位）
        keys = [i["key"] for i in preview["items"]]
        assert len(set(keys)) == 4, f"两个域同名公式位的决策键撞了：{keys}"
        assert sorted(parse_decision_key(k) for k in keys) == _identities(preview["items"])
        assert sorted(keys) == sorted(decision_key(d, p, SLOT) for d in (TB, NOTE) for p in (jia, yi))


# ─── 四、应用到指定项目 / 五、全局发布 ────────────────────────────────────────


async def test_apply_to_projects_keys_carry_domain_and_legacy_still_works() -> None:
    async with make_db() as factory, factory() as db:
        store = get_store(NOTE)
        source, *targets = [await add_project(db, name) for name in ("来源", "目标一", "目标二", "目标三")]
        for pid, formula in ((source, "ROW(9)"), *((t, "ROW(2)") for t in targets)):
            await store.write_project(db, pid, SLOT, definition=_def(NOTE, formula), base_definition=None,
                                      base_version=None, pinned=False, base_origin=None, base_template_id=None,
                                      user_id=None, label="章节")
        await db.commit()
        preview = await apply_preview(db, domain=NOTE, project_id=source, slot_keys=[SLOT], target_ids=targets)
        assert [i["category"] for i in preview["items"]] == ["conflict"] * 3
        assert sorted(parse_decision_key(i["key"]) for i in preview["items"]) == _identities(preview["items"])
        one, two, three = targets
        decisions = Decisions.parse({"conflict_choices": {
            decision_key(NOTE, one, SLOT): "adopt", f"{two}|{SLOT}": "adopt", decision_key(TB, three, SLOT): "adopt"}})
        out = await apply_to_projects(db, domain=NOTE, project_id=source, slot_keys=[SLOT], target_ids=targets,
                                      decisions=decisions, user_id=None)
        await db.commit()
        assert [await _formula(db, t, NOTE) for t in targets] == ["ROW(9)", "ROW(9)", "ROW(2)"]
        assert await _pending(db) == [(str(three), NOTE, SLOT, "conflict")] and out["summary"]["pending_total"] == 1


async def test_publish_global_keys_carry_domain_and_legacy_still_works() -> None:
    async with make_db() as factory, factory() as db:
        store = get_store(TB)
        await publish_global(db, domain=TB, scope="*", user_id=None,
                             changes=[{"slot_key": WP_LIKE, "definition": _def(TB, "ROW(1)")}])
        projects = [await add_project(db, name) for name in ("一", "二", "三")]
        for pid in projects:
            await store.write_project(db, pid, WP_LIKE, definition=_def(TB, "ROW(2)"),
                                      base_definition=_def(TB, "ROW(1)"), base_version=1, pinned=False,
                                      base_origin="global", base_template_id=None, user_id=None, label="明细")
        await db.commit()
        change = [{"slot_key": WP_LIKE, "definition": _def(TB, "ROW(3)"), "expected_version": 1}]
        preview = await preview_global(db, domain=TB, scope="*", changes=change)
        assert [i["category"] for i in preview["items"]] == ["conflict"] * 3
        assert sorted(parse_decision_key(i["key"]) for i in preview["items"]) == _identities(preview["items"])
        one, two, three = projects
        decisions = Decisions.parse({"conflict_choices": {
            decision_key(TB, one, WP_LIKE): "adopt", f"{two}|{WP_LIKE}": "adopt",
            decision_key(NOTE, three, WP_LIKE): "adopt"}})
        res = await publish_global(db, domain=TB, scope="*", changes=change, user_id=None, decisions=decisions)
        await db.commit()
        assert [await _formula(db, p, TB, WP_LIKE) for p in projects] == ["ROW(3)", "ROW(3)", "ROW(2)"]
        assert await _pending(db) == [(str(three), TB, WP_LIKE, "conflict")]
        assert res["summary"]["pending_total"] == 1
