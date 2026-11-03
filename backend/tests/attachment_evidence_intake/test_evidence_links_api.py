"""证据链接接口（spec attachment-evidence-intake 需求 3.1–3.4）。

回归背景：侧栏「证据」页签手填附件 UUID；``created_by`` 取请求体、缺省全零 UUID；路径底稿、请求体附件、
删除的链接都不校是否属于路径项目 / 底稿。
"""
from __future__ import annotations

import uuid

import pytest_asyncio
import sqlalchemy as sa

from app.models.attachment_models import AttachmentWorkingPaper
from app.models.wp_optimization_models import EvidenceLink
from tests.attachment_evidence_intake._helpers import count, evidence_app
from tests.attachment_security_baseline._world import add_attachment, add_wp, sqlite_attachment_world

FAKE_CREATOR = "00000000-0000-0000-0000-000000000000"


@pytest_asyncio.fixture
async def world(monkeypatch):
    async with sqlite_attachment_world(monkeypatch) as w:
        yield w


def _base(project, wp) -> str:
    return f"/api/projects/{project.id}/workpapers/{wp.id}/evidence"


async def _wp_with_attachment(world, *, wp_code: str = "F3-5"):
    wp = await add_wp(world, world.target, wp_code=wp_code)
    att = await add_attachment(world, world.target)
    await world._add(AttachmentWorkingPaper(attachment_id=att.id, wp_id=wp.id, association_type="evidence"))
    return wp, att


async def test_create_link_takes_creator_from_session(world):
    who = await world.edit_member()
    wp, att = await _wp_with_attachment(world)
    async with world.client_for_app(evidence_app(), user=who.user) as client:
        resp = await client.post(f"{_base(world.target, wp)}/link", json={
            "attachment_id": str(att.id), "sheet_name": "F3-5", "cell_ref": "B12",
            "evidence_type": "note", "created_by": FAKE_CREATOR,
        })
    assert resp.status_code == 200, resp.text
    link = (await world.db.execute(sa.select(EvidenceLink))).scalar_one()
    assert link.created_by == who.user.id
    assert (link.sheet_name, link.cell_ref, link.evidence_type) == ("F3-5", "B12", "note")


async def test_create_link_rejects_attachment_outside_wp(world):
    who = await world.edit_member()
    wp, _att = await _wp_with_attachment(world)
    loose = await add_attachment(world, world.target, file_name="未关联.pdf")      # 同项目、不在本底稿
    other = await world.project(name="【测试】另一项目")
    foreign = await add_attachment(world, other, file_name="他项目.pdf")          # 他项目
    async with world.client_for_app(evidence_app(), user=who.user) as client:
        for att in (loose, foreign):
            resp = await client.post(f"{_base(world.target, wp)}/link", json={"attachment_id": str(att.id)})
            assert resp.status_code == 404, resp.text
        bad_type = await client.post(f"{_base(world.target, wp)}/link", json={
            "attachment_id": str(_att.id), "evidence_type": "statement",
        })
        assert bad_type.status_code == 422, bad_type.text
    assert await count(world.db, EvidenceLink) == 0


async def test_batch_link_is_all_or_nothing(world):
    who = await world.edit_member()
    wp, att = await _wp_with_attachment(world)
    loose = await add_attachment(world, world.target, file_name="未关联.pdf")
    async with world.client_for_app(evidence_app(), user=who.user) as client:
        resp = await client.post(f"{_base(world.target, wp)}/batch-link", json={"links": [
            {"attachment_id": str(att.id), "cell_ref": "B1"},
            {"attachment_id": str(loose.id), "cell_ref": "B2"},
        ]})
    assert resp.status_code == 404, resp.text
    assert await count(world.db, EvidenceLink) == 0


async def test_delete_link_scoped_to_path_wp(world):
    who = await world.edit_member()
    wp, att = await _wp_with_attachment(world)
    other_wp = await add_wp(world, world.target, wp_code="F3-6")
    link = await world._add(EvidenceLink(wp_id=wp.id, attachment_id=att.id, cell_ref="B1", created_by=who.user.id))
    async with world.client_for_app(evidence_app(), user=who.user) as client:
        wrong = await client.delete(f"{_base(world.target, other_wp)}/{link.id}")
        assert wrong.status_code == 404, wrong.text
        assert await count(world.db, EvidenceLink) == 1
        right = await client.delete(f"{_base(world.target, wp)}/{link.id}")
    assert right.status_code == 200, right.text
    assert await count(world.db, EvidenceLink) == 0
    assert await world.db.get(type(att), att.id) is not None  # 只删链接，不删附件


async def test_list_has_attachment_meta_and_hides_deleted(world):
    who = await world.edit_member()
    wp, att = await _wp_with_attachment(world)
    gone = await add_attachment(world, world.target, file_name="已删.pdf", is_deleted=True)
    await world._add(EvidenceLink(wp_id=wp.id, attachment_id=att.id, sheet_name="F3-5", cell_ref="item:1",
                                  created_by=who.user.id))
    await world._add(EvidenceLink(wp_id=wp.id, attachment_id=gone.id, sheet_name="F3-5", cell_ref="item:1",
                                  created_by=who.user.id))
    await world._add(EvidenceLink(wp_id=wp.id, attachment_id=att.id, sheet_name="F3-5", cell_ref="item:2",
                                  created_by=who.user.id))
    async with world.client_for_app(evidence_app(), user=who.user) as client:
        all_items = (await client.get(_base(world.target, wp))).json()["items"]
        slot = (await client.get(_base(world.target, wp), params={"sheet_name": "F3-5", "cell_ref": "item:1"})).json()
    assert len(all_items) == 2
    assert slot["total"] == 1
    assert slot["items"][0]["attachment"]["file_name"] == att.file_name
    assert slot["items"][0]["attachment"]["id"] == str(att.id)


async def test_wp_of_other_project_is_404(world):
    who = await world.edit_member()
    other = await world.project(name="【测试】另一项目")
    foreign_wp = await add_wp(world, other)
    async with world.client_for_app(evidence_app(), user=who.user) as client:
        listed = await client.get(_base(world.target, foreign_wp))
        linked = await client.post(f"{_base(world.target, foreign_wp)}/link", json={"attachment_id": str(uuid.uuid4())})
    assert (listed.status_code, linked.status_code) == (404, 404)
