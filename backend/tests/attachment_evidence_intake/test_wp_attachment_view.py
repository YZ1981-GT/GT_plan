"""底稿附件统一视图的证据链接来源、关联底稿数与「全部解除」（spec attachment-evidence-intake 需求 4.1、4.2、4.5）。

回归背景：统一视图只认整稿关联 / reference / 函证，行级证据不出现在底稿附件抽屉里，证据声明也算不到；
附件管理页「已关联底稿」按列表里不存在的 wp_code / wp_id 字段统计，恒为 0；解除整稿关联后行级链接还挂着。
"""
from __future__ import annotations

import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI

from app.models.attachment_models import AttachmentWorkingPaper
from app.models.wp_optimization_models import EvidenceLink
from app.routers.attachments import router as attachments_router
from app.services.attachment_service import AttachmentService
from tests.attachment_evidence_intake._helpers import count
from tests.attachment_security_baseline._world import add_attachment, add_wp, sqlite_attachment_world


@pytest_asyncio.fixture
async def world(monkeypatch):
    async with sqlite_attachment_world(monkeypatch) as w:
        yield w


async def _link(world, wp, att, *, sheet="F3-5", cell="item:1", creator=None):
    return await world._add(EvidenceLink(
        wp_id=wp.id, attachment_id=att.id, sheet_name=sheet, cell_ref=cell, evidence_type=att.attachment_type,
        created_by=creator,
    ))


def _by_name(view: dict) -> dict[str, dict]:
    return {item["file_name"]: item for item in view["items"]}


async def test_view_includes_row_evidence_with_positions(world):
    who = await world.edit_member()
    wp = await add_wp(world, world.target, wp_code="F3-5")
    other_wp = await add_wp(world, world.target, wp_code="F3-6")
    row_only = await add_attachment(world, world.target, file_name="行证据.pdf", attachment_type="note")
    both = await add_attachment(world, world.target, file_name="整稿与行.pdf")
    gone = await add_attachment(world, world.target, file_name="已删.pdf", is_deleted=True)
    await world._add(AttachmentWorkingPaper(attachment_id=both.id, wp_id=wp.id, association_type="evidence"))
    await world._add(AttachmentWorkingPaper(attachment_id=both.id, wp_id=other_wp.id, association_type="evidence"))
    link = await _link(world, wp, row_only, cell="item:2", creator=who.user.id)
    await _link(world, wp, both, cell="B12", creator=who.user.id)
    await _link(world, wp, gone, creator=who.user.id)

    view = await AttachmentService(world.db).get_wp_attachments(wp.id)
    items = _by_name(view)
    assert set(items) == {"行证据.pdf", "整稿与行.pdf"}
    row = items["行证据.pdf"]
    # 只挂在行上的证据也算出现在本底稿（行级上传只写证据链接，ADR-AEI-02）
    assert (row["source"], row["sources"], row["linked_wp_count"]) == ("evidence_link", ["evidence_link"], 1)
    # voucher_key：挂在抽样凭证上的证据才有值（spec attachment-voucher-evidence-binding 需求 1.4）
    assert row["evidence_positions"] == [{
        "link_id": str(link.id), "sheet_name": "F3-5", "cell_ref": "item:2", "page_ref": None, "evidence_type": "note",
        "voucher_key": None,
    }]
    mixed = items["整稿与行.pdf"]
    assert (mixed["source"], mixed["sources"], mixed["linked_wp_count"]) == ("associated", ["associated", "evidence_link"], 2)
    assert [p["cell_ref"] for p in mixed["evidence_positions"]] == ["B12"]
    # 行级证据也满足证据声明（F3 声明票据）
    assert view["evidence_requirements"] == [{"type": "note", "label": "票据影像", "satisfied": True}]


async def test_unlink_removes_row_links_of_this_wp_only(world):
    who = await world.edit_member()
    wp = await add_wp(world, world.target, wp_code="F3-5")
    other_wp = await add_wp(world, world.target, wp_code="F3-6")
    att = await add_attachment(world, world.target)
    await world._add(AttachmentWorkingPaper(attachment_id=att.id, wp_id=wp.id, association_type="evidence"))
    await _link(world, wp, att, cell="item:1", creator=who.user.id)
    await _link(world, wp, att, cell="item:2", creator=who.user.id)
    await _link(world, other_wp, att, cell="item:1", creator=who.user.id)

    result = await AttachmentService(world.db).unlink_wp_attachment(wp.id, att.id)
    assert (result["link_removed"], result["evidence_links_removed"]) == (1, 2)
    assert await count(world.db, EvidenceLink, EvidenceLink.wp_id == wp.id) == 0
    assert await count(world.db, EvidenceLink, EvidenceLink.wp_id == other_wp.id) == 1
    assert (await AttachmentService(world.db).get_wp_attachments(wp.id))["items"] == []


async def test_project_list_carries_linked_wp_count(world):
    """出现的底稿数 = 整稿关联 ∪ 行级证据链接 ∪ reference（去重）；函证挂载不计。"""
    who = await world.edit_member()
    wp1 = await add_wp(world, world.target, wp_code="D4-1")
    wp2 = await add_wp(world, world.target, wp_code="D4-2")
    linked = await add_attachment(world, world.target, file_name="两张底稿.pdf")
    row_only = await add_attachment(world, world.target, file_name="行证据.pdf")
    referenced = await add_attachment(world, world.target, file_name="引用.pdf")
    await add_attachment(world, world.target, file_name="未关联.pdf")
    for wp in (wp1, wp2):
        await world._add(AttachmentWorkingPaper(attachment_id=linked.id, wp_id=wp.id, association_type="evidence"))
    await _link(world, wp1, linked, cell="B3", creator=who.user.id)       # 同一底稿不重复计
    await _link(world, wp2, row_only, cell="item:1", creator=who.user.id)
    referenced.reference_type, referenced.reference_id = "working_paper", wp1.id
    await world.db.flush()
    api = FastAPI()
    api.include_router(attachments_router)
    async with world.client_for_app(api, user=who.user) as client:
        resp = await client.get(f"/api/projects/{world.target.id}/attachments")
    assert resp.status_code == 200, resp.text
    counts = {item["file_name"]: item["linked_wp_count"] for item in resp.json()}
    assert counts == {"两张底稿.pdf": 2, "行证据.pdf": 1, "引用.pdf": 1, "未关联.pdf": 0}
    assert (await world.db.execute(sa.select(sa.func.count()).select_from(AttachmentWorkingPaper))).scalar_one() == 2


async def test_linked_workpapers_lists_union_same_project_sorted(world):
    """侧栏悬停清单：三类来源的底稿去重、只取同项目未删除底稿、按编码排序。"""
    from app.services.attachment_wp_view import linked_workpapers

    who = await world.edit_member()
    wp_d = await add_wp(world, world.target, wp_code="D4-2")
    wp_f = await add_wp(world, world.target, wp_code="F2-30")
    wp_gone = await add_wp(world, world.target, wp_code="A1")
    wp_gone.is_deleted = True
    other = await world.other_project()
    wp_other = await add_wp(world, other, wp_code="B1")
    att = await add_attachment(world, world.target)
    await world._add(AttachmentWorkingPaper(attachment_id=att.id, wp_id=wp_f.id, association_type="evidence"))
    await _link(world, wp_d, att, creator=who.user.id)
    await _link(world, wp_gone, att, creator=who.user.id)
    await _link(world, wp_other, att, creator=who.user.id)
    att.reference_type, att.reference_id = "working_paper", wp_d.id
    await world.db.flush()

    listed = await linked_workpapers(world.db, att.id)
    assert [(item["wp_id"], item["wp_code"]) for item in listed] == [(str(wp_d.id), "D4-2"), (str(wp_f.id), "F2-30")]
    assert listed[0]["wp_name"] == "D4-2 测试底稿"
