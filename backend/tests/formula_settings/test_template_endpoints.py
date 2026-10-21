"""公式模板端点（tasks 7.5）：可见性矩阵（四种共享范围 × 所有者 / 成员 / 非成员 / admin）+ 管理 / 订阅权限。

只替换身份（``get_current_user``）与数据库（``get_db``）；项目权限照常查 project_users（真实鉴权链）。
"""
from __future__ import annotations

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.deps import get_current_user
from app.models.formula_setting_models import FormulaTemplate, FormulaTemplateSubscription
from app.routers import formula_templates as ft_router

from ._env import STD, add_global_row, add_member, add_project, add_user, make_db

SLOT = "balance_sheet:BS-001"


def _manual(name: str, share_scope: str, owner_project_id=None) -> dict:
    return {"name": name, "share_scope": share_scope, "owner_project_id": owner_project_id, "source": "manual",
            "applicable_scope": STD, "domains": ["report"],
            "items": [{"domain": "report", "slot_key": SLOT, "definition": {"formula": f"TB('1001','期末余额')*{len(name)}"}}]}


@pytest_asyncio.fixture
async def api(monkeypatch):
    async with make_db() as factory:
        async with factory() as db:
            await add_global_row(db, "BS-001", "TB('1001','期末余额')")
            users = {n: await add_user(db, n, r) for n, r in (
                ("admin", "admin"), ("owner", "auditor"), ("member", "auditor"), ("outsider", "auditor"))}
            root = await add_project(db, "集团", report_scope="standalone")
            child = await add_project(db, "子公司甲", parent=root)
            sibling = await add_project(db, "子公司乙", parent=root)
            team = await add_project(db, "项目组")
            await add_member(db, team, users["owner"], "edit")
            await add_member(db, child, users["owner"], "edit")
            await add_member(db, team, users["member"], "readonly")
            await add_member(db, sibling, users["member"], "readonly")
            await db.commit()
        events: list = []

        async def fake_publish_events(evs, **kw):
            events.extend(evs)
            return len(evs)

        monkeypatch.setattr(ft_router, "publish_events", fake_publish_events)
        app = FastAPI()
        app.include_router(ft_router.router)
        app.include_router(ft_router.project_router)
        who = {"u": users["owner"]}

        async def _db():
            async with factory() as s:
                yield s

        async def _user():
            return who["u"]

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = _user
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            yield {"c": client, "f": factory, "events": events, "as": lambda n: who.update(u=users[n]),
                   "p": {"root": root, "child": child, "sibling": sibling, "team": team}}


async def _create(api, user: str, body: dict) -> str:
    api["as"](user)
    r = await api["c"].post("/api/formula-templates", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _templates(api) -> dict[str, str]:
    p = api["p"]
    return {
        "personal": await _create(api, "owner", _manual("个人", "personal")),
        "team": await _create(api, "owner", _manual("项目组模板", "team", str(p["team"]))),
        "group": await _create(api, "owner", _manual("集团模板x", "group", str(p["child"]))),
        "firm": await _create(api, "admin", _manual("事务所模板xx", "firm")),
    }


VISIBLE = {  # 四种共享范围 × 所有者 / 成员 / 非成员 / admin
    "personal": {"owner": True, "member": False, "outsider": False, "admin": True},
    "team": {"owner": True, "member": True, "outsider": False, "admin": True},
    "group": {"owner": True, "member": True, "outsider": False, "admin": True},
    "firm": {"owner": True, "member": True, "outsider": True, "admin": True},
}


async def test_visibility_matrix_list_detail_versions_same_rule(api):
    ids = await _templates(api)
    for who in ("owner", "member", "outsider", "admin"):
        api["as"](who)
        listed = {t["id"] for t in (await api["c"].get("/api/formula-templates")).json()["items"]}
        for scope, tid in ids.items():
            expect = VISIBLE[scope][who]
            assert (tid in listed) is expect, (scope, who)
            detail = await api["c"].get(f"/api/formula-templates/{tid}")
            versions = await api["c"].get(f"/api/formula-templates/{tid}/versions")
            assert (detail.status_code, versions.status_code) == ((200, 200) if expect else (404, 404)), (scope, who)


async def test_create_rules(api):
    p = api["p"]
    api["as"]("owner")
    assert (await api["c"].post("/api/formula-templates", json=_manual("越权", "firm"))).status_code == 403
    api["as"]("outsider")
    assert (await api["c"].post("/api/formula-templates", json=_manual("非成员", "team", str(p["team"])))
            ).status_code == 403
    api["as"]("member")
    assert (await api["c"].post("/api/formula-templates", json=_manual("只读", "team", str(p["team"])))
            ).status_code == 403, "项目组模板需所属项目 edit"
    assert (await api["c"].post("/api/formula-templates", json={**_manual("缺项目", "group"), "owner_project_id": None})
            ).status_code == 400
    async with api["f"]() as db:
        assert await db.scalar(sa.select(sa.func.count()).select_from(FormulaTemplate)) == 0, "拒绝零写入"


async def test_manage_publish_subscribe_permissions(api):
    ids = await _templates(api)
    c, p = api["c"], api["p"]
    api["as"]("member")
    assert (await c.put(f"/api/formula-templates/{ids['team']}", json={"name": "改名"})).status_code == 403
    assert (await c.get(f"/api/formula-templates/{ids['team']}/subscribers")).status_code == 403
    body = {"expected_version": 1, "changes": [{"domain": "report", "slot_key": SLOT,
                                                "definition": {"formula": "TB('1001','审定数')"}}]}
    assert (await c.post(f"/api/formula-templates/{ids['group']}/publish", json=body)).status_code == 403
    sub = {"template_id": ids["group"], "domain": "report"}
    assert (await c.post(f"/api/projects/{p['sibling']}/formula-templates/subscribe", json=sub)).status_code == 403, \
        "订阅需目标项目 edit"
    api["as"]("outsider")
    assert (await c.delete(f"/api/formula-templates/{ids['personal']}")).status_code == 404

    api["as"]("owner")
    pre = await c.post(f"/api/projects/{p['child']}/formula-templates/subscribe-preview", json=sub)
    assert pre.status_code == 200 and pre.json()["summary"]["counts"]["inherit"] == 1
    assert (await c.post(f"/api/projects/{p['child']}/formula-templates/subscribe", json=sub)).status_code == 200
    assert api["events"] and api["events"][-1]["slot_keys"] == [SLOT]
    listed = (await c.get(f"/api/projects/{p['child']}/formula-templates/subscriptions")).json()["items"]
    assert [(s["template_id"], s["template_version"]) for s in listed] == [(ids["group"], 1)]
    assert (await c.post(f"/api/projects/{p['child']}/formula-templates/subscribe",
                         json={"template_id": ids["personal"], "domain": "report"})).status_code == 409, "每域只订阅一个"
    assert (await c.delete(f"/api/formula-templates/{ids['group']}")).status_code == 409, "有订阅不能删"
    assert (await c.post(f"/api/formula-templates/{ids['group']}/publish", json={**body, "expected_version": None})
            ).status_code == 428
    pub = await c.post(f"/api/formula-templates/{ids['group']}/publish", json=body)
    assert pub.status_code == 200 and pub.json()["version"] == 2
    subs = (await c.get(f"/api/formula-templates/{ids['group']}/subscribers")).json()["items"]
    assert [(s["project_id"], s["template_version"], s["local_modified"]) for s in subs] == [(str(p["child"]), 2, 0)]
    un = await c.post(f"/api/projects/{p['child']}/formula-templates/unsubscribe", json={"domain": "report"})
    assert un.status_code == 200
    async with api["f"]() as db:
        assert await db.scalar(sa.select(sa.func.count()).select_from(FormulaTemplateSubscription).where(
            FormulaTemplateSubscription.is_active == sa.true())) == 0
    assert (await c.delete(f"/api/formula-templates/{ids['group']}")).status_code == 200

    api["as"]("member")  # 可见但不是 admin：设为全局 = 提交候选；预览仅 admin
    assert (await c.post(f"/api/formula-templates/{ids['firm']}/promote-preview", json={"domain": "report"})
            ).status_code == 403
    cand = await c.post(f"/api/formula-templates/{ids['firm']}/promote", json={"domain": "report"})
    assert cand.status_code == 200 and cand.json()["candidate"]["status"] == "pending"
