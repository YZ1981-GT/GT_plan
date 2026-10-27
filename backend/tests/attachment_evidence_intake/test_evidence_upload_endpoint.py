"""底稿证据入口上传（spec attachment-evidence-intake 需求 1.1、1.3、1.5）。

回归背景：底稿里的上传点走项目级旧上传端点，再调 associate；associate 只登记给 lead，编制人上传后关联失败被吞，
侧栏拖放留下孤儿附件并报「上传失败」；行级组件按 ``title`` 伪绑定，后端不回 ``title`` ⇒ 列表恒空。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.models.attachment_models import Attachment
from app.models.wp_optimization_models import EvidenceLink
from app.services import workpaper_evidence_intake
from tests.attachment_evidence_intake._helpers import (
    attachment_rows,
    count,
    evidence_app,
    files_under,
    links_of,
    pdf,
    use_local_storage,
)
from tests.attachment_security_baseline._world import add_wp, sqlite_attachment_world


@pytest_asyncio.fixture
async def world(monkeypatch):
    async with sqlite_attachment_world(monkeypatch) as w:
        yield w


@pytest.fixture
def storage_root(tmp_path, monkeypatch):
    return use_local_storage(tmp_path, monkeypatch)


def _url(project_id, wp_id, suffix: str = "upload") -> str:
    return f"/api/projects/{project_id}/workpapers/{wp_id}/evidence/{suffix}"


async def _post(world, user, wp, *, files=None, data=None, project=None):
    project = project or world.target
    async with world.client_for_app(evidence_app(), user=user) as client:
        return await client.post(_url(project.id, wp.id), files=files or pdf(), data=data or {})


async def test_wp_level_upload_writes_only_wp_link(world, storage_root):
    who = await world.edit_member()
    wp = await add_wp(world, world.target, wp_code="F3-5")
    resp = await _post(world, who.user, wp)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["evidence_link"] is None
    att = await world.db.get(Attachment, uuid.UUID(body["attachment"]["id"]))
    assert att.attachment_type == "note"  # F3 只声明票据 ⇒ 缺省
    assert (att.reference_type, att.reference_id, att.created_by) == ("working_paper", wp.id, who.user.id)
    wp_links, ev_links = await links_of(world.db, att.id)
    assert [(link.wp_id, link.association_type) for link in wp_links] == [(wp.id, "note")]
    assert ev_links == []
    assert len(files_under(storage_root)) == 1


async def test_row_level_upload_writes_only_evidence_link(world, storage_root):
    who = await world.edit_member()
    wp = await add_wp(world, world.target, wp_code="F3-5")
    resp = await _post(world, who.user, wp, data={
        "sheet_name": "F3-5", "cell_ref": "item:2", "evidence_type": "voucher", "page_ref": "P1",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    att = await world.db.get(Attachment, uuid.UUID(body["attachment"]["id"]))
    assert (att.attachment_type, att.reference_type) == ("voucher", "workpaper_item")
    wp_links, ev_links = await links_of(world.db, att.id)
    assert wp_links == []
    assert [(e.wp_id, e.sheet_name, e.cell_ref, e.page_ref, e.evidence_type, e.created_by) for e in ev_links] == [
        (wp.id, "F3-5", "item:2", "P1", "voucher", who.user.id)
    ]
    assert body["evidence_link"]["id"] == str(ev_links[0].id)


async def test_same_name_twice_are_two_attachments(world, storage_root):
    who = await world.edit_member()
    wp = await add_wp(world, world.target, wp_code="F3-5")
    for slot in ("item:1", "item:2"):
        resp = await _post(world, who.user, wp, files=pdf("扫描件.pdf"), data={"sheet_name": "F3-5", "cell_ref": slot})
        assert resp.status_code == 200, resp.text
    rows = await attachment_rows(world.db)
    assert sorted((r.file_name, r.version, r.previous_version_id) for r in rows) == [
        ("扫描件.pdf", 1, None), ("扫描件.pdf", 1, None),
    ]


@pytest.mark.parametrize(
    ("files", "data", "status"),
    [
        (None, {"evidence_type": "statement"}, 422),          # 不在证据类型登记表
        (None, {"evidence_type": "general"}, 422),
        (pdf("run.exe", b"MZ\x90\x00"), None, 422),           # 上传策略：扩展名
        (None, {"sheet_name": "x" * 101}, 400),               # 位置超长
    ],
)
async def test_rejected_before_any_write(world, storage_root, files, data, status):
    who = await world.edit_member()
    wp = await add_wp(world, world.target, wp_code="F3-5")
    resp = await _post(world, who.user, wp, files=files, data=data)
    assert resp.status_code == status, resp.text
    assert await attachment_rows(world.db) == []
    assert await count(world.db, EvidenceLink) == 0
    assert files_under(storage_root) == []


async def test_too_large_is_413(world, storage_root, monkeypatch):
    monkeypatch.setattr(workpaper_evidence_intake, "max_upload_bytes", lambda: 4)
    who = await world.edit_member()
    wp = await add_wp(world, world.target)
    resp = await _post(world, who.user, wp)
    assert resp.status_code == 413, resp.text
    assert await attachment_rows(world.db) == []


async def test_wp_of_other_project_is_404(world, storage_root):
    who = await world.edit_member()
    other = await world.project(name="【测试】另一项目")
    foreign_wp = await add_wp(world, other)
    resp = await _post(world, who.user, foreign_wp)  # 路径项目 = 本人有权的目标项目，底稿属于别的项目
    assert resp.status_code == 404, resp.text
    assert await attachment_rows(world.db) == []
    assert files_under(storage_root) == []


async def test_readonly_member_forbidden(world, storage_root):
    who = await world.readonly_member()
    wp = await add_wp(world, world.target)
    resp = await _post(world, who.user, wp)
    assert resp.status_code == 403, resp.text
    assert await attachment_rows(world.db) == []


async def test_archived_project_is_423(world, storage_root):
    who = await world.archived_edit_member()
    wp = await add_wp(world, world.target)
    resp = await _post(world, who.user, wp)
    assert resp.status_code == 423, resp.text
    assert await attachment_rows(world.db) == []
