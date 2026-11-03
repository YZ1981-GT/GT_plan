"""模板软删与回收站（advanced-query-linkage-closure 任务 25；R9.5，ADR-AQL-11，design §3.6；AQ-30）。

请求经 httpx 真发到生产注册的 custom_query / recycle_bin router（``tests/authz_world.py``），只 override 当前用户与会话。

- 删除模板 = 软删：行仍在、``is_deleted`` 为真；列表、详情、更新、删除、执行一律 404（变异 B8-d：改回硬删）。
- 回收站按作者可见：作者与 admin 看得到、能恢复、能彻底删除，他人（含合伙人）看不到、操作 403（变异 B8-e：去掉作者分支）；
  模板行带逐行能力 ``can_restore`` / ``can_purge``，其余类型不带（变异 B8-f：不下发能力）。
- 恢复后重新出现在模板列表（写后读回）；彻底删除后行不在了。
- 统计（真 PG 权限世界，回收站会逐类型计数，表须齐）：作者与 admin 计入模板类型，他人不计。
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.schema import sort_tables

from app.models.base import UserRole
from app.models.custom_query_models import CustomQueryTemplate
from app.routers import custom_query, recycle_bin
from tests.advanced_query_linkage.builder_tables import _foreign_key_closure
from tests.authz_world import TARGET_PROJECT_ID, AuthzWorld, pg_world, sqlite_world

X = TARGET_PROJECT_ID
CQ = "/api/custom-query"
RB = "/api/recycle-bin"
TYPE = "custom_query_template"


@pytest.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    async with sqlite_world(monkeypatch, extra_tables=(CustomQueryTemplate.__table__,)) as w:
        yield w


async def _row(world: AuthzWorld, template_id) -> CustomQueryTemplate | None:
    stmt = select(CustomQueryTemplate).where(CustomQueryTemplate.id == uuid.UUID(str(template_id)))
    return (await world.db.execute(stmt.execution_options(populate_existing=True))).scalar_one_or_none()


async def _create_and_delete(world: AuthzWorld, author) -> str:
    async with world.client(custom_query.router, user=author) as client:
        created = await client.post(f"{CQ}/templates", json={
            "name": "【测试】AQL-B8 回收站", "data_source": "tb_detail", "config": {"source": "tb_detail"},
            "scope": "private"})
        assert created.status_code == 201, created.text
        deleted = await client.delete(f"{CQ}/templates/{created.json()['id']}")
    assert deleted.status_code == 204, deleted.text
    return created.json()["id"]


async def _bin(world: AuthzWorld, user, **params) -> list[dict]:
    async with world.client(recycle_bin.router, user=user) as client:
        response = await client.get(RB, params=params)
    assert response.status_code == 200, response.text
    return response.json()["items"]


async def test_soft_deleted_template_is_gone_from_every_template_endpoint(world):
    author = await world.user(UserRole.auditor)
    tid = await _create_and_delete(world, author)
    row = await _row(world, tid)
    assert row is not None and row.is_deleted is True and row.deleted_at is not None, "删除应为软删（AQ-30 原先硬删）"
    async with world.client(custom_query.router, user=author) as client:
        listed = await client.get(f"{CQ}/templates")
        calls = [await client.get(f"{CQ}/templates/{tid}"),
                 await client.put(f"{CQ}/templates/{tid}", json={"name": "【测试】改名"}),
                 await client.post(f"{CQ}/templates/{tid}/execute", json={"project_id": str(X), "year": 2025}),
                 await client.delete(f"{CQ}/templates/{tid}")]
    assert tid not in {item["id"] for item in listed.json()["templates"]}
    for response in calls:  # 先比状态码：不是 404 时红在这里（带响应体），而不是取 detail 时 KeyError
        assert response.status_code == 404, f"{response.request.method} {response.request.url.path} ⇒ {response.text}"
        assert response.json()["detail"]["error_code"] == "TEMPLATE_NOT_FOUND", response.text
    assert (await _row(world, tid)).name == "【测试】AQL-B8 回收站"


async def test_recycle_bin_shows_templates_to_author_and_admin_only(world):
    author = await world.user(UserRole.auditor)
    admin = (await world.admin_non_member()).user
    others = [await world.user(UserRole.auditor), await world.user(UserRole.partner), await world.user(UserRole.manager)]
    tid = await _create_and_delete(world, author)
    for user in (author, admin):
        items = [item for item in await _bin(world, user, item_type=TYPE) if item["id"] == tid]
        assert len(items) == 1, items
        assert (items[0]["can_restore"], items[0]["can_purge"], items[0]["purgeable"]) == (True, True, True)
        assert (items[0]["name"], items[0]["deleted_by"], items[0]["type_label"]) == (
            "【测试】AQL-B8 回收站", str(author.id), "查询模板")
    for user in others:
        assert [item for item in await _bin(world, user, item_type=TYPE) if item["id"] == tid] == []


async def test_restore_and_purge_are_for_author_and_admin(world):
    author = await world.user(UserRole.auditor)
    admin = (await world.admin_non_member()).user
    partner = await world.user(UserRole.partner)
    tid = await _create_and_delete(world, author)
    async with world.client(recycle_bin.router, user=partner) as client:
        denied = [await client.post(f"{RB}/{TYPE}/{tid}/restore"), await client.delete(f"{RB}/{TYPE}/{tid}")]
    for response in denied:
        assert response.status_code == 403, response.text
    assert (await _row(world, tid)).is_deleted is True

    async with world.client(recycle_bin.router, user=author) as client:
        restored = await client.post(f"{RB}/{TYPE}/{tid}/restore")
    assert restored.status_code == 200, restored.text
    async with world.client(custom_query.router, user=author) as client:
        listed = await client.get(f"{CQ}/templates")  # 写后读回：恢复后重新出现在模板列表
        assert tid in {item["id"] for item in listed.json()["templates"]}
        assert (await client.delete(f"{CQ}/templates/{tid}")).status_code == 204
    async with world.client(recycle_bin.router, user=admin) as client:  # admin 可恢复他人的模板
        assert (await client.post(f"{RB}/{TYPE}/{tid}/restore")).status_code == 200
    async with world.client(custom_query.router, user=author) as client:
        assert (await client.delete(f"{CQ}/templates/{tid}")).status_code == 204
    async with world.client(recycle_bin.router, user=author) as client:
        purged = await client.delete(f"{RB}/{TYPE}/{tid}")
    assert purged.status_code == 200, purged.text
    assert await _row(world, tid) is None


async def test_only_owner_scoped_rows_carry_row_capabilities(world):
    author = await world.user(UserRole.auditor)
    admin = (await world.admin_non_member()).user
    tid = await _create_and_delete(world, author)
    gone = await world.project(name="【测试】AQL-B8 已删项目", is_deleted=True)
    items = {item["id"]: item for item in await _bin(world, admin)}
    assert "can_restore" not in items[str(gone.id)] and "can_purge" not in items[str(gone.id)]
    assert (items[tid]["can_restore"], items[tid]["can_purge"]) == (True, True)


def _recyclable_tables() -> tuple:
    models = [model for model, _label, _name in recycle_bin._get_recyclable_tables().values()]
    return tuple(sort_tables(_foreign_key_closure([model.__table__ for model in models])))


@pytest.mark.pg_only
async def test_stats_count_templates_for_author_and_admin_only(monkeypatch):
    async with pg_world(monkeypatch, extra_tables=_recyclable_tables()) as w:
        author = await w.user(UserRole.auditor)
        admin = (await w.admin_non_member()).user
        other = await w.user(UserRole.manager)
        await _create_and_delete(w, author)
        got = {}
        for label, user in (("author", author), ("admin", admin), ("other", other)):
            async with w.client(recycle_bin.router, user=user) as client:
                response = await client.get(f"{RB}/stats")
            assert response.status_code == 200, response.text
            got[label] = response.json()["by_type"].get(TYPE, {}).get("count", 0)
    assert got == {"author": 1, "admin": 1, "other": 0}
