"""模板「全局已变」提示分类 + 保留模板（spec formula-management-repair-closure R6）。

- 分类：模板没改过（follow，可一键同步）/ 模板与新全局相同（same，只需更新基线）/ 真冲突（conflict）/ 全局删了（deleted）。
  修复前：全局删除不提示；模板与新全局相同时只能「并入」⇒ 发布报「模板没有任何改动」。
- 保留模板：只把基线换成当前全局 —— 不升模板版本、不写版本记录、订阅项目不动；模板版本 + 全局版本双重校验、全部或全不。
SQLite 真 ORM：真实存储落库再读回；HTTP 用例只替换身份与数据库（真实 get_managed 判定）。
"""
from __future__ import annotations

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.deps import get_current_user
from app.models.formula_setting_models import FormulaTemplateVersion
from app.routers import formula_templates as ft_router
from app.services.formula_settings import template_service as svc
from app.services.formula_settings import template_sync as sync
from app.services.formula_settings.errors import NotFound, VersionConflict, VersionRequired
from app.services.formula_settings.publish import publish_global
from app.services.formula_settings.template_access import Viewer

from ._env import STD, add_global_row, add_user, audit_actions, make_db

S = {n: f"balance_sheet:BS-00{n}" for n in range(1, 6)}
OLD = {n: f"TB('100{n}','期末余额')" for n in range(1, 6)}
MINE2, X3, X5 = "ROW('BS-009')", "TB('1003','期末余额')*2", "TB('1005','期末余额')*3"
NEW1, NEW3, NEW2B = "TB('1001','审定数')", "TB('1003','审定数')", "TB('1002','审定数')"


def rd(formula: str) -> dict:
    """报表定义带上类别（与全局行同口径：类别是报表域的执行字段，缺了就算不同）。"""
    return {"formula": formula, "formula_category": "auto_calc"}


async def _world(db):
    admin = await add_user(db, "hint_admin", "admin")
    owner = await add_user(db, "hint_owner", "auditor")
    for n in range(1, 6):
        await add_global_row(db, f"BS-00{n}", OLD[n], row_number=n)
    tpl = await svc.create_template(
        db, viewer=await Viewer.load(db, owner), name="提示分类", description=None, share_scope="personal",
        owner_project_id=None, applicable_scope=STD, source="manual", domains=["report"],
        items=[{"domain": "report", "slot_key": S[1], "definition": rd(OLD[1])},   # 没改过
               {"domain": "report", "slot_key": S[2], "definition": rd(MINE2)},    # 改过，全局随后改成同样
               {"domain": "report", "slot_key": S[3], "definition": rd(X3)},       # 改过，全局改成别的
               {"domain": "report", "slot_key": S[4], "definition": rd(OLD[4])},   # 全局随后删除
               {"domain": "report", "slot_key": S[5], "definition": rd(X5)}])      # 全局没变
    await publish_global(db, domain="report", scope=STD, user_id=admin.id, changes=[
        {"slot_key": S[1], "definition": rd(NEW1), "expected_version": 1},
        {"slot_key": S[2], "definition": rd(MINE2), "expected_version": 1},
        {"slot_key": S[3], "definition": rd(NEW3), "expected_version": 1},
        {"slot_key": S[4], "definition": None, "expected_version": 1}])
    await db.commit()
    return admin, owner, tpl


async def _hints(db, tpl, user) -> dict[str, dict]:
    detail = await svc.template_detail(db, tpl, viewer=await Viewer.load(db, user))
    return {h["slot_key"]: h for h in detail["global_hints"]}


async def test_hints_are_classified_and_global_deletion_is_reported():
    async with make_db() as factory, factory() as db:
        _admin, owner, tpl = await _world(db)
        hints = await _hints(db, tpl, owner)
    assert {s: h["kind"] for s, h in hints.items()} == {
        S[1]: "follow", S[2]: "same", S[3]: "conflict", S[4]: "deleted"}, "全局没变的 BS-005 不提示"
    assert (hints[S[1]]["base_version"], hints[S[1]]["global_version"]) == (1, 2)
    assert hints[S[4]]["global_definition"] is None and hints[S[4]]["global_version"] is None
    assert hints[S[2]]["same_as_template"] is True and hints[S[3]]["same_as_template"] is False


async def test_keep_updates_baseline_only_and_hint_disappears():
    async with make_db() as factory, factory() as db:
        _admin, owner, tpl = await _world(db)
        out = await sync.keep_template_baseline(db, tpl, expected_version=tpl.version, user_id=owner.id, items=[
            {"domain": "report", "slot_key": S[2], "expected_global_version": 2},
            {"domain": "report", "slot_key": S[4], "expected_global_version": None}])
        await db.commit()
        hints = await _hints(db, tpl, owner)
        versions = (await db.execute(sa.select(sa.func.count()).select_from(FormulaTemplateVersion).where(
            FormulaTemplateVersion.template_id == tpl.id))).scalar_one()
        rows = (await svc.template_definitions(db, tpl))["report"]
        actions = [a for a, _ in await audit_actions(db)]
    assert set(hints) == {S[1], S[3]}, "保留后这两处提示消失，其余不动"
    assert (out["version"], tpl.version, versions) == (1, 1, 1), "不升模板版本、不写版本记录"
    assert rows[S[2]].definition["formula"] == MINE2 and rows[S[4]].definition["formula"] == OLD[4], "模板定义不动"
    assert (rows[S[2]].base_version, rows[S[4]].base_definition) == (2, None)
    assert "formula.template_baseline_kept" in actions


async def test_after_keep_the_next_global_change_is_judged_against_the_new_baseline():
    """保留后基线 = 当时的全局：全局再变时模板「没改过」⇒ 可一键同步（follow）。"""
    async with make_db() as factory, factory() as db:
        admin, owner, tpl = await _world(db)
        await sync.keep_template_baseline(db, tpl, expected_version=1, user_id=owner.id,
                                          items=[{"domain": "report", "slot_key": S[2], "expected_global_version": 2}])
        await publish_global(db, domain="report", scope=STD, user_id=admin.id,
                             changes=[{"slot_key": S[2], "definition": rd(NEW2B), "expected_version": 2}])
        await db.commit()
        assert (await _hints(db, tpl, owner))[S[2]]["kind"] == "follow"


@pytest.mark.parametrize(("kw", "error"), [
    ({"expected_version": None, "items": [{"domain": "report", "slot_key": S[2], "expected_global_version": 2}]},
     VersionRequired),
    ({"expected_version": 9, "items": [{"domain": "report", "slot_key": S[2], "expected_global_version": 2}]},
     VersionConflict),
    ({"expected_version": 1, "items": [{"domain": "report", "slot_key": S[2], "expected_global_version": 2},
                                       {"domain": "report", "slot_key": S[3], "expected_global_version": 1}]},
     VersionConflict),
    ({"expected_version": 1, "items": [{"domain": "report", "slot_key": "balance_sheet:NOPE",
                                        "expected_global_version": 1}]}, NotFound),
])
async def test_keep_is_all_or_nothing_under_version_checks(kw, error):
    """模板版本、每个公式位看到的全局版本都要对上；任何一处不对，前面校验过的也不改。"""
    async with make_db() as factory, factory() as db:
        _admin, owner, tpl = await _world(db)
        with pytest.raises(error):
            await sync.keep_template_baseline(db, tpl, user_id=owner.id, **kw)
        rows = (await svc.template_definitions(db, tpl))["report"]
        assert rows[S[2]].base_version == 1 and rows[S[2]].base_definition["formula"] == OLD[2]


@pytest_asyncio.fixture
async def http():
    async with make_db() as factory:
        async with factory() as db:
            admin, owner, tpl = await _world(db)
            other = await add_user(db, "hint_other", "auditor")
            await db.commit()
            users = {"owner": owner, "other": other, "admin": admin}
            tid = str(tpl.id)
        app = FastAPI()
        app.include_router(ft_router.router)
        who = {"u": users["owner"]}

        async def _db():
            async with factory() as s:
                yield s

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = lambda: who["u"]
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            yield {"c": client, "tid": tid, "as": lambda n: who.update(u=users[n])}


async def test_keep_endpoint_permissions_and_cas(http):
    body = {"expected_version": 1, "items": [{"domain": "report", "slot_key": S[2], "expected_global_version": 2}]}
    url = f"/api/formula-templates/{http['tid']}/global-hints/keep"
    http["as"]("other")
    assert (await http["c"].post(url, json=body)).status_code == 404, "个人模板对他人不可见（按不存在）"
    http["as"]("owner")
    stale = await http["c"].post(url, json={**body, "expected_version": 5})
    assert stale.status_code == 409 and stale.json()["detail"]["error_code"]
    r = await http["c"].post(url, json=body)
    assert r.status_code == 200, r.text
    assert r.json() == {"template_id": http["tid"], "version": 1,
                        "kept": [{"domain": "report", "slot_key": S[2], "base_version": 2}]}
    kinds = {h["slot_key"]: h["kind"] for h in (await http["c"].get(f"/api/formula-templates/{http['tid']}")).json()[
        "global_hints"]}
    assert kinds == {S[1]: "follow", S[3]: "conflict", S[4]: "deleted"}
    assert (await http["c"].post(url, json={"expected_version": 1, "items": []})).status_code == 422
