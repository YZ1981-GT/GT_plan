"""共享配置模板端点补鉴权（tasks 7.6，R14.1 / R14.2）：真实鉴权链（只替换身份与数据库）。"""
from __future__ import annotations

import uuid

import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.deps import get_current_user
from app.models.shared_config_models import ConfigReference, SharedConfigTemplate
from app.routers import shared_config

from ._env import add_member, add_project, add_user, make_db

EXTRA = [SharedConfigTemplate, ConfigReference]


@pytest_asyncio.fixture
async def api():
    async with make_db(EXTRA) as factory:
        async with factory() as db:
            users = {n: await add_user(db, n, r) for n, r in (
                ("admin", "admin"), ("owner", "auditor"), ("peer", "auditor"), ("outsider", "auditor"))}
            root = await add_project(db, "集团")
            child = await add_project(db, "子公司", parent=root)
            sibling = await add_project(db, "兄弟公司", parent=root)
            await add_member(db, child, users["owner"], "edit")
            await add_member(db, sibling, users["peer"], "readonly")
            await db.commit()
        app = FastAPI()
        app.include_router(shared_config.router)
        who = {"u": users["owner"]}

        async def _db():
            async with factory() as s:
                yield s

        async def _user():
            return who["u"]

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = _user
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            yield {"c": client, "f": factory, "as": lambda n: who.update(u=users[n]),
                   "p": {"root": root, "child": child, "sibling": sibling}}


def _body(owner_type: str, owner_project_id=None, config_type: str = "report_mapping", name: str = "模板") -> dict:
    return {"name": name, "config_type": config_type, "owner_type": owner_type,
            "owner_project_id": str(owner_project_id) if owner_project_id else None, "config_data": {"k": 1}}


async def test_create_rules_and_retired_type(api):
    c, p = api["c"], api["p"]
    api["as"]("owner")
    assert (await c.post("/api/shared-config/templates", json=_body("system"))).status_code == 403
    assert (await c.post("/api/shared-config/templates", json=_body("group"))).status_code == 400
    assert (await c.post("/api/shared-config/templates", json=_body("group", p["sibling"]))).status_code == 403
    assert (await c.post("/api/shared-config/templates", json=_body("personal", config_type="formula_config"))
            ).status_code == 410, "formula_config 入口下线"
    async with api["f"]() as db:
        assert await db.scalar(sa.select(sa.func.count()).select_from(SharedConfigTemplate)) == 0, "拒绝零写入"
    assert (await c.post("/api/shared-config/templates", json=_body("group", p["child"]))).status_code == 200
    assert (await c.get("/api/shared-config/templates", params={"config_type": "formula_config"})).json() == []
    api["as"]("admin")
    assert (await c.post("/api/shared-config/templates", json=_body("system", name="事务所"))).status_code == 200


async def test_view_manage_apply_permissions(api):
    c, p = api["c"], api["p"]
    api["as"]("owner")
    personal = (await c.post("/api/shared-config/templates", json=_body("personal", name="个人"))).json()["id"]
    group = (await c.post("/api/shared-config/templates", json=_body("group", p["child"], name="集团"))).json()["id"]
    api["as"]("peer")  # 兄弟公司成员：同一集团根 ⇒ 集团模板可见；个人模板不可见
    assert (await c.get(f"/api/shared-config/templates/{group}")).status_code == 200
    assert (await c.get(f"/api/shared-config/templates/{personal}")).status_code == 404
    assert (await c.put(f"/api/shared-config/templates/{group}", json={"name": "改"})).status_code == 403
    assert (await c.delete(f"/api/shared-config/templates/{group}")).status_code == 403
    apply = {"template_id": group, "project_id": str(p["sibling"])}
    assert (await c.post("/api/shared-config/apply", json=apply)).status_code == 403, "只读不能引用到项目"
    assert (await c.get(f"/api/shared-config/references/{p['sibling']}")).status_code == 200
    assert (await c.get("/api/shared-config/templates", params={"config_type": "report_mapping",
                                                                 "project_id": str(p["child"])})).status_code == 403
    api["as"]("outsider")
    assert (await c.get(f"/api/shared-config/templates/{group}")).status_code == 404
    assert (await c.get(f"/api/shared-config/references/{p['child']}")).status_code == 403
    api["as"]("owner")
    assert (await c.post("/api/shared-config/apply", json={"template_id": group, "project_id": str(p["child"])})
            ).status_code == 200
    assert (await c.put(f"/api/shared-config/templates/{personal}", json={"name": "新名"})).status_code == 200
    api["as"]("admin")
    assert (await c.delete(f"/api/shared-config/templates/{group}")).status_code == 200
    async with api["f"]() as db:
        tpl = await db.get(SharedConfigTemplate, uuid.UUID(group))
        assert tpl.is_deleted


async def test_admin_can_delete_others_personal_template(api):
    """R14.1：admin 能删他人的个人模板（修复前 service 二次做所有者判断，admin 被转 403）。"""
    c = api["c"]
    api["as"]("owner")
    personal = (await c.post("/api/shared-config/templates", json=_body("personal", name="owner的个人"))).json()["id"]
    api["as"]("peer")  # 他人删 ⇒ 不可见 404（can_view 对个人模板只认所有者）
    assert (await c.delete(f"/api/shared-config/templates/{personal}")).status_code == 404
    api["as"]("admin")
    assert (await c.delete(f"/api/shared-config/templates/{personal}")).status_code == 200
    async with api["f"]() as db:
        assert (await db.get(SharedConfigTemplate, uuid.UUID(personal))).is_deleted


async def test_list_and_detail_visibility_agree(api):
    """R14.1：列表与详情同一可见性口径。个人模板只对所有者；集团模板对同集团根项目成员，
    不传 project_id 时集团模板也应出现在有权成员的列表里（旧 list_available_templates 会漏）。"""
    c, p = api["c"], api["p"]
    api["as"]("owner")
    personal = (await c.post("/api/shared-config/templates", json=_body("personal", name="个人P"))).json()["id"]
    group = (await c.post("/api/shared-config/templates", json=_body("group", p["child"], name="集团G"))).json()["id"]

    def ids(resp):
        return {t["id"] for t in resp.json()}

    # 所有者：列表含两者，详情都可见
    lst = await c.get("/api/shared-config/templates", params={"config_type": "report_mapping"})
    assert {personal, group} <= ids(lst)
    for tid in (personal, group):
        assert (await c.get(f"/api/shared-config/templates/{tid}")).status_code == 200

    # 同集团根的兄弟公司成员（peer）：不传 project_id 也能在列表看到集团模板、看不到他人个人模板，
    # 且列表与详情一致
    api["as"]("peer")
    lst = await c.get("/api/shared-config/templates", params={"config_type": "report_mapping"})
    assert group in ids(lst) and personal not in ids(lst)
    assert (await c.get(f"/api/shared-config/templates/{group}")).status_code == 200
    assert (await c.get(f"/api/shared-config/templates/{personal}")).status_code == 404

    # 无关的人：列表与详情都看不到
    api["as"]("outsider")
    lst = await c.get("/api/shared-config/templates", params={"config_type": "report_mapping"})
    assert group not in ids(lst) and personal not in ids(lst)
    assert (await c.get(f"/api/shared-config/templates/{group}")).status_code == 404
