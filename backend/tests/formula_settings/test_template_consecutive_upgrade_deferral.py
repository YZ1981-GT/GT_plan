"""模板连续升级保留原版本暂缓项（spec formula-integrity-and-propagation-closure 任务 4，反例 6）。

v2 暂缓项目后，v3 只改另一个公式位：v2 暂缓的公式位待确认不得丢，订阅也不得提前跟上新版本；
全部逐位结案后才解除固定并跟上当前版本。
"""
from __future__ import annotations

import pytest

from app.services.formula_settings import template_sync as sync
from app.services.formula_settings.engine import Decisions
from app.services.formula_settings.project_ops import resolve_items

from .test_templates import (  # noqa: F401  (world 夹具复用)
    MINE, OLD, SLOT, SLOT2, V2, _formula, _publish_previewed, _sub, _template, rdef, world,
)
from ._env import pending_items

V3_B = "ROW('BS-001')+1"


async def test_v3_changing_only_b_keeps_v2_deferred_a_pending(world):
    w = world
    db = w["db"]
    tpl = await _template(w)
    await sync.subscribe(db, project_id=w["deferrer"], tpl=tpl, domain="report", decisions=None, user_id=w["owner"].id)

    # v2：A、B 一起改，项目暂缓 ⇒ 订阅固定在 v1，A、B 各一条待确认
    defer = Decisions.parse({"project_choices": {str(w["deferrer"]): "defer"}})
    await _publish_previewed(db, tpl, expected_version=1, user_id=w["owner"].id, decisions=defer, changes=[
        {"domain": "report", "slot_key": SLOT, "definition": rdef(V2)},
        {"domain": "report", "slot_key": SLOT2, "definition": rdef("ROW('BS-001')")}])
    sub = await _sub(db, w["deferrer"])
    assert sub.pinned and sub.template_version == 1
    assert {i.slot_key for i in await pending_items(db, w["deferrer"])} == {SLOT, SLOT2}

    # v3：只改 B（不暂缓）⇒ A 的待确认仍在且仍指向 v2 定义；订阅仍固定；本项目有效公式仍是旧值
    await _publish_previewed(db, tpl, expected_version=2, user_id=w["owner"].id, decisions=None, changes=[
        {"domain": "report", "slot_key": SLOT2, "definition": rdef(V3_B)}])
    assert tpl.version == 3
    sub = await _sub(db, w["deferrer"])
    assert sub.pinned and sub.template_version == 1, "仍有未结案待确认，订阅不得提前跟上新版本"
    items = {i.slot_key: i for i in await pending_items(db, w["deferrer"])}
    assert set(items) == {SLOT, SLOT2}, "只改 B 不得丢 A 的暂缓待确认"
    assert items[SLOT].upstream_definition["formula"] == V2, "A 仍指向 v2 暂缓时的上游定义"
    assert items[SLOT2].upstream_definition["formula"] == V3_B, "B 的待确认跟到最新定义"
    assert await _formula(db, w["deferrer"]) == MINE, "未采用前有效公式仍是旧定义"

    # 逐位结案后才解除固定并跟上当前版本 v3
    await resolve_items(db, project_id=w["deferrer"], user_id=w["owner"].id, resolutions=[
        {"item_id": str(i.id), "choice": "adopt", "revision": i.revision} for i in items.values()])
    sub = await _sub(db, w["deferrer"])
    assert (sub.pinned, sub.template_version) == (False, 3)
    assert await _formula(db, w["deferrer"]) == V2
    assert await _formula(db, w["deferrer"], "BS-002") == V3_B
    assert not await pending_items(db, w["deferrer"])


async def test_resolving_only_a_after_v3_keeps_subscription_pinned_until_b_done(world):
    w = world
    db = w["db"]
    tpl = await _template(w)
    await sync.subscribe(db, project_id=w["deferrer"], tpl=tpl, domain="report", decisions=None, user_id=w["owner"].id)
    defer = Decisions.parse({"project_choices": {str(w["deferrer"]): "defer"}})
    await _publish_previewed(db, tpl, expected_version=1, user_id=w["owner"].id, decisions=defer, changes=[
        {"domain": "report", "slot_key": SLOT, "definition": rdef(V2)},
        {"domain": "report", "slot_key": SLOT2, "definition": rdef("ROW('BS-001')")}])
    await _publish_previewed(db, tpl, expected_version=2, user_id=w["owner"].id, decisions=None, changes=[
        {"domain": "report", "slot_key": SLOT2, "definition": rdef(V3_B)}])
    items = {i.slot_key: i for i in await pending_items(db, w["deferrer"])}
    await resolve_items(db, project_id=w["deferrer"], user_id=w["owner"].id, resolutions=[
        {"item_id": str(items[SLOT].id), "choice": "adopt", "revision": items[SLOT].revision}])
    sub = await _sub(db, w["deferrer"])
    assert sub.pinned, "B 仍待确认，订阅保持固定"
    assert [i.slot_key for i in await pending_items(db, w["deferrer"])] == [SLOT2]
    assert await _formula(db, w["deferrer"]) == V2 and OLD != V2
