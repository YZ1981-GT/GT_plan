"""回收站彻底删除附件同步删本地文件（spec attachment-archive-and-a-class-evidence 需求 9，ADR-AE-12）。

回归背景：三条彻底删除路径只删附件行，文件留在磁盘（Spec C 走查留下的文件至今仍在），归档完整性检查的
「孤儿文件」大多由此而来。删文件必须查引用：版本行、复制出的附件可能共用同一文件。
"""
from __future__ import annotations

from pathlib import Path

import pytest_asyncio

from app.core.config import settings
from app.models.attachment_models import AttachmentWorkingPaper
from app.models.evidence_governance_models import AttachmentVersion
from app.routers import recycle_bin as recycle_bin_module
from tests.attachment_security_baseline._world import add_attachment, add_wp, sqlite_attachment_world

RB_ROUTER = recycle_bin_module.router


@pytest_asyncio.fixture
async def world(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "ATTACHMENT_LOCAL_STORAGE_ROOT", str(tmp_path / "attachments"))
    async with sqlite_attachment_world(monkeypatch) as w:
        yield w


def _stored(world, name: str, data: bytes = b"x") -> Path:
    p = Path(settings.ATTACHMENT_LOCAL_STORAGE_ROOT) / str(world.target.id) / "evidence" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


async def _editor(world):
    return (await world.member("edit", "auditor")).user


async def test_single_purge_unlinks_unreferenced_file(world):
    path = _stored(world, "回函.pdf")
    att = await add_attachment(world, world.target, file_path=path.as_posix(), is_deleted=True)
    async with world.client(RB_ROUTER, user=await _editor(world)) as c:
        resp = await c.delete(f"/api/recycle-bin/attachment/{att.id}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["file_cleanup"] == {"deleted": 1, "kept_referenced": 0, "skipped_outside_root": 0, "failed": 0}
    assert not path.exists()


async def test_shared_file_and_version_reference_are_kept(world):
    shared = _stored(world, "共用.pdf")
    versioned = _stored(world, "版本.pdf")
    a = await add_attachment(world, world.target, file_path=shared.as_posix(), is_deleted=True)
    await add_attachment(world, world.target, file_path=shared.as_posix())  # 另一行仍在用
    b = await add_attachment(world, world.target, file_path=versioned.as_posix(), is_deleted=True)
    user = await _editor(world)
    await world._add(AttachmentVersion(attachment_id=b.id, project_id=world.target.id, version_no=1,
                                       storage_type="local", storage_key=versioned.as_posix(), actor_type="user",
                                       actor_user_id=user.id))
    async with world.client(RB_ROUTER, user=user) as c:
        r1 = await c.delete(f"/api/recycle-bin/attachment/{a.id}")
        r2 = await c.delete(f"/api/recycle-bin/attachment/{b.id}")
    assert (r1.status_code, r2.status_code) == (200, 200), (r1.text, r2.text)
    assert r1.json()["file_cleanup"]["kept_referenced"] == 1
    assert r2.json()["file_cleanup"]["kept_referenced"] == 1
    assert shared.exists() and versioned.exists()


async def test_outside_root_and_paperless_untouched(world, tmp_path):
    outside = tmp_path / "elsewhere" / "外部.pdf"
    outside.parent.mkdir()
    outside.write_bytes(b"o")
    a = await add_attachment(world, world.target, file_path=outside.as_posix(), is_deleted=True)
    p = await add_attachment(world, world.target, file_path="paperless://documents/7", storage_type="paperless",
                             is_deleted=True)
    async with world.client(RB_ROUTER, user=await _editor(world)) as c:
        r1 = await c.delete(f"/api/recycle-bin/attachment/{a.id}")
        r2 = await c.delete(f"/api/recycle-bin/attachment/{p.id}")
    assert r1.json()["file_cleanup"]["skipped_outside_root"] == 1 and outside.exists()
    assert r2.json()["file_cleanup"] == {"deleted": 0, "kept_referenced": 0, "skipped_outside_root": 0, "failed": 0}


async def test_batch_purge_keeps_files_of_skipped_rows(world):
    ok_path, ref_path = _stored(world, "可删.pdf"), _stored(world, "仍被引用.pdf")
    ok = await add_attachment(world, world.target, file_path=ok_path.as_posix(), is_deleted=True)
    ref = await add_attachment(world, world.target, file_path=ref_path.as_posix(), is_deleted=True)
    wp = await add_wp(world, world.target)
    await world._add(AttachmentWorkingPaper(attachment_id=ref.id, wp_id=wp.id, association_type="evidence"))
    async with world.client(RB_ROUTER, user=await _editor(world)) as c:
        resp = await c.post("/api/recycle-bin/batch-delete", params={"item_type": "attachment"},
                            json={"ids": [str(ok.id), str(ref.id)]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["file_cleanup"]["deleted"] == 1
    assert not ok_path.exists() and ref_path.exists()


async def test_empty_purges_files(world):
    paths = [_stored(world, f"清空{i}.pdf") for i in range(2)]
    for p in paths:
        await add_attachment(world, world.target, file_path=p.as_posix(), is_deleted=True)
    admin = (await world.admin_non_member()).user
    async with world.client(RB_ROUTER, user=admin) as c:
        resp = await c.post("/api/recycle-bin/empty", params={"item_type": "attachment"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["file_cleanup"]["deleted"] == 2
    assert not any(p.exists() for p in paths)


async def test_unlink_failure_is_reported_not_rolled_back(world, monkeypatch):
    path = _stored(world, "锁住.pdf")
    att = await add_attachment(world, world.target, file_path=path.as_posix(), is_deleted=True)
    real_unlink = Path.unlink

    def locked(self, *a, **kw):
        if self.name == "锁住.pdf":
            raise PermissionError("文件被占用")
        return real_unlink(self, *a, **kw)

    monkeypatch.setattr(Path, "unlink", locked)
    async with world.client(RB_ROUTER, user=await _editor(world)) as c:
        resp = await c.delete(f"/api/recycle-bin/attachment/{att.id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["file_cleanup"]["failed"] == 1
    assert "1 个附件文件未能从磁盘删除" in body["message"]
    assert path.exists()
    from app.models.attachment_models import Attachment
    import sqlalchemy as sa

    assert (await world.db.execute(sa.select(Attachment.id).where(Attachment.id == att.id))).first() is None
