"""跨底稿查询与引用凭证证据（spec attachment-voucher-evidence-binding 需求 2，ADR-AVE-02/07）。

SQLite 世界没有可见性表：统一门的静默判定在被测函数的下一层（``try_gate_wp``）按用例放行 / 拒绝；
真实统一门下的可见性见 ``test_voucher_evidence_pg.py``。
"""
from __future__ import annotations

import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI

from app.models.core import ProjectStatus
from app.models.wp_optimization_models import EvidenceLink
from tests.attachment_evidence_intake._helpers import count, evidence_app, unwrap
from tests.attachment_security_baseline._world import add_attachment, add_wp, sqlite_attachment_world
from tests.attachment_voucher_evidence._vk import visible_only, vk

VK = vk()
OTHER_VK = vk("0004")


@pytest_asyncio.fixture
async def world(monkeypatch):
    async with sqlite_attachment_world(monkeypatch) as w:
        yield w


def _apps() -> FastAPI:
    from app.routers.voucher_links import router as ledger_router

    api = evidence_app()
    api.include_router(ledger_router)
    return api


async def _scene(world):
    """甲底稿 D2-4 上传了凭证 FY 0003 的原件；乙底稿 F4-8 也抽到了这张凭证。"""
    a = await add_wp(world, world.target, wp_code="D2-4")
    b = await add_wp(world, world.target, wp_code="F4-8")
    att = await add_attachment(world, world.target, file_name="记-0003 凭证.pdf", attachment_type="voucher")
    who = await world.edit_member()
    await world._add(EvidenceLink(wp_id=a.id, attachment_id=att.id, sheet_name="D2-4", cell_ref="row:r1",
                                  evidence_type="voucher", voucher_key=VK, created_by=who.user.id))
    return who, a, b, att


async def _query(client, project, keys, year=2025):
    resp = await client.post(f"/api/projects/{project.id}/ledger/voucher-evidence/query", json={"year": year, "keys": keys})
    return resp, unwrap(resp.json()).get("evidence") if resp.status_code == 200 else None


async def test_query_lists_only_visible_workpapers(world):
    who, a, _b, att = await _scene(world)
    async with world.client_for_app(_apps(), user=who.user) as client:
        with visible_only(a.id):
            _r, seen = await _query(client, world.target, [VK, OTHER_VK])
            _r, wrong_year = await _query(client, world.target, [VK], year=2024)  # 键的年度与查询年度不符 ⇒ 丢弃
        with visible_only():
            _r, hidden = await _query(client, world.target, [VK])
    assert list(seen) == [VK]
    assert [(e["wp_code"], [x["id"] for x in e["attachments"]]) for e in seen[VK]] == [("D2-4", [str(att.id)])]
    assert hidden == {} and wrong_year == {}


async def test_query_skips_deleted_attachment_other_year_and_caps_keys(world):
    who, a, _b, att = await _scene(world)
    att.is_deleted = True
    await world.db.flush()
    async with world.client_for_app(_apps(), user=who.user) as client:
        with visible_only(a.id):
            _r, deleted = await _query(client, world.target, [VK])
            _r, other_year = await _query(client, world.target, [vk(year="2024")], year=2025)
            too_many, _ = await _query(client, world.target, [vk(str(n)) for n in range(501)])
    assert deleted == {} and other_year == {}
    assert too_many.status_code == 422


async def test_reuse_links_source_attachment_once(world):
    who, a, b, att = await _scene(world)
    url = f"/api/projects/{world.target.id}/workpapers/{b.id}/evidence/voucher-reuse"
    async with world.client_for_app(_apps(), user=who.user) as client:
        with visible_only(a.id, b.id):
            first = await client.post(url, json={"voucher_key": VK, "attachment_id": str(att.id)})
            again = await client.post(url, json={"voucher_key": VK, "attachment_id": str(att.id)})
    assert first.status_code == again.status_code == 200, first.text
    assert (unwrap(first.json())["existed"], unwrap(again.json())["existed"]) == (False, True)
    link = (await world.db.execute(sa.select(EvidenceLink).where(EvidenceLink.wp_id == b.id))).scalar_one()
    assert (link.voucher_key, link.attachment_id, link.sheet_name, link.cell_ref, link.evidence_type) == (
        VK, att.id, None, None, "voucher")
    assert link.created_by == who.user.id
    assert await count(world.db, EvidenceLink, EvidenceLink.wp_id == a.id) == 1  # 源底稿不动


async def test_reuse_requires_visible_source_with_same_voucher(world):
    who, a, b, att = await _scene(world)
    url = f"/api/projects/{world.target.id}/workpapers/{b.id}/evidence/voucher-reuse"
    async with world.client_for_app(_apps(), user=who.user) as client:
        with visible_only(b.id):  # 源底稿看不到
            hidden = await client.post(url, json={"voucher_key": VK, "attachment_id": str(att.id)})
        with visible_only(a.id, b.id):
            wrong_vk = await client.post(url, json={"voucher_key": OTHER_VK, "attachment_id": str(att.id)})
            self_wp = await client.post(  # 本底稿自己的链接不是「别的底稿」
                f"/api/projects/{world.target.id}/workpapers/{a.id}/evidence/voucher-reuse",
                json={"voucher_key": VK, "attachment_id": str(att.id)},
            )
    assert (hidden.status_code, wrong_vk.status_code, self_wp.status_code) == (404, 404, 404)
    assert await count(world.db, EvidenceLink) == 1


async def test_query_and_reuse_require_membership(world):
    """项目级鉴权（design §5）：非成员两个端点都 403；只读成员能查他稿、不能引用。"""
    _who, a, b, att = await _scene(world)
    reuse_url = f"/api/projects/{world.target.id}/workpapers/{b.id}/evidence/voucher-reuse"
    body = {"voucher_key": VK, "attachment_id": str(att.id)}
    results = {}
    for name in ("non_member", "readonly_member"):
        ident = await world.identity(name)
        async with world.client_for_app(_apps(), user=ident.user) as client:
            with visible_only(a.id, b.id):
                query, seen = await _query(client, world.target, [VK])
                reuse = await client.post(reuse_url, json=body)
        results[name] = (query.status_code, reuse.status_code, list(seen or {}))
    assert results == {"non_member": (403, 403, []), "readonly_member": (200, 403, [VK])}
    assert await count(world.db, EvidenceLink) == 1


async def test_reuse_on_archived_project_is_423(world):
    who, a, b, att = await _scene(world)
    world.target.status = ProjectStatus.archived
    await world.db.flush()
    async with world.client_for_app(_apps(), user=who.user) as client:
        with visible_only(a.id, b.id):
            resp = await client.post(f"/api/projects/{world.target.id}/workpapers/{b.id}/evidence/voucher-reuse",
                                     json={"voucher_key": VK, "attachment_id": str(att.id)})
    assert resp.status_code == 423, resp.text
    assert await count(world.db, EvidenceLink) == 1
