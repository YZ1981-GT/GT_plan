# Feature: procedure-chain-hardening-and-java-contracts — R3 模板复制来源可见性（真实 PG）
"""模板复制只复制当前用户在来源项目里看得见的底稿（与底稿列表同一可见性口径；每例事务回滚）。

原先 ``_load_source_wp`` / ``_load_source_cycle`` 不校验来源项目：在任一项目有编辑权的人能把任何项目的底稿内容拷进自己的项目。
"""
from __future__ import annotations

import pytest

from app.models.core import PermissionLevel
from app.services import wp_template_init_service

from ._factories import (
    IS_PG, mk_assignment, mk_project, mk_project_user, mk_staff, mk_user, mk_working_paper, mk_wp_index,
)
from .test_task15_full_entry_integration import _Ctx

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not IS_PG, reason="need PostgreSQL (visibility query is PG SQL)"),
]


def _url(pid) -> str:
    return f"/api/projects/{pid}/workpapers/template-copy"


async def _world(s):
    target, source = await mk_project(s), await mk_project(s)
    editor = await mk_user(s)
    pu = await mk_project_user(s, target.id, editor.id, scope_cycles="G")
    pu.permission_level = PermissionLevel.edit
    papers = {}
    for code in ("G1", "G2"):
        wi = await mk_wp_index(s, source.id, wp_code=code, audit_cycle="G")
        papers[code] = await mk_working_paper(s, source.id, wi.id)
    await s.flush()
    return {"target": target.id, "source": source.id, "editor": editor, "papers": papers,
            "ids": {k: v.id for k, v in papers.items()}}


async def _restricted_lead_on_g1(s, w):
    await mk_project_user(s, w["source"], w["editor"].id, scope_cycles="G")
    w["papers"]["G1"].assigned_to = w["editor"].id
    await s.flush()


async def _supervisor(s, w):
    staff = await mk_staff(s, user_id=w["editor"].id)
    await mk_assignment(s, w["source"], staff.id, role="manager")
    await mk_project_user(s, w["source"], w["editor"].id)
    await s.flush()


@pytest.fixture(autouse=True)
def _storage(tmp_path, monkeypatch):
    monkeypatch.setattr(wp_template_init_service, "STORAGE_DIR", tmp_path / "wp_storage")


async def _post(ctx, w, body):
    async with ctx.bind_app(w["editor"]) as c:
        return await c.post(_url(w["target"]), json=body)


def _items(r) -> list[dict]:
    """真实 app 的 ResponseWrapperMiddleware 把 2xx 包成 {code, message, data}。"""
    body = r.json()
    return body["data"] if isinstance(body, dict) and "data" in body else body


async def test_single_copy_from_project_you_are_not_in_is_404():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    s.sync_session.expire_on_commit = False
    try:
        w = await _world(s)
        r = await _post(ctx, w, {"source_wp_id": str(w["ids"]["G1"])})
        assert r.status_code == 404, r.text
    finally:
        await ctx.__aexit__()


async def test_restricted_member_copies_only_delegated_paper():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    s.sync_session.expire_on_commit = False
    try:
        w = await _world(s)
        await _restricted_lead_on_g1(s, w)
        r = await _post(ctx, w, {"source_wp_id": str(w["ids"]["G2"])})
        assert r.status_code == 404, r.text  # G2 没委派给他
        r = await _post(ctx, w, {"source_project_id": str(w["source"]), "audit_cycle": "G"})
        assert r.status_code == 200, r.text
        by_code = {it["source_wp_code"]: it["status"] for it in _items(r)}
        assert by_code == {"G1": "copied", "G2": "skipped"}
    finally:
        await ctx.__aexit__()


async def test_supervisor_copies_whole_cycle():
    ctx = _Ctx()
    s = await ctx.__aenter__()
    s.sync_session.expire_on_commit = False
    try:
        w = await _world(s)
        await _supervisor(s, w)
        r = await _post(ctx, w, {"source_project_id": str(w["source"]), "audit_cycle": "G"})
        assert r.status_code == 200, r.text
        assert sorted(it["status"] for it in _items(r)) == ["copied", "copied"]
    finally:
        await ctx.__aexit__()
