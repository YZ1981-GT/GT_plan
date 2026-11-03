"""归档路由鉴权与归档包下载（spec attachment-archive-and-a-class-evidence 需求 1.4、3.2）。

真发请求、真实判定链（只替换当前用户与会话）。改造前：作业查询 / 重试只要登录，跨项目也能查；没有下载端点，
向导里的「下载归档包」指向从不写入的 output_url。
"""
from __future__ import annotations

import hashlib
import uuid

import pytest_asyncio

from app.models.archive_models import ArchiveJob
from app.models.phase16_models import EvidenceHashCheck
from app.routers.archive import router as archive_router
from tests.attachment_security_baseline._world import sqlite_attachment_world


@pytest_asyncio.fixture
async def world(monkeypatch):
    async with sqlite_attachment_world(monkeypatch) as w:
        def _create(sync_session):
            conn = sync_session.connection()
            ArchiveJob.__table__.create(conn)
            EvidenceHashCheck.__table__.create(conn)
        await w.db.run_sync(_create)
        yield w


async def _job(world, tmp_path, *, status="succeeded", project=None, record=True, content=b"PK\x03\x04zip"):
    project = project or world.target
    job_id = uuid.uuid4()
    path = tmp_path / f"{job_id}.zip"
    path.write_bytes(content)
    sha = hashlib.sha256(content).hexdigest()
    job = await world._add(ArchiveJob(
        id=job_id, project_id=project.id, scope="final", status=status, push_to_cloud=False, purge_local=False,
        section_progress={"package": {"status": "succeeded", "path": str(path.resolve()), "sha256": sha}},
    ))
    if record:
        await world._add(EvidenceHashCheck(id=uuid.uuid4(), export_id=str(job_id), file_path=str(path.resolve()),
                                           sha256=sha, check_status="passed"))
    return job, path


def _url(project_id, job_id, tail=""):
    return f"/api/projects/{project_id}/archive/jobs/{job_id}{tail}"


async def test_readonly_member_downloads_package(world, tmp_path):
    job, path = await _job(world, tmp_path)
    who = await world.readonly_member()
    async with world.client(archive_router, user=who.user) as c:
        resp = await c.get(_url(world.target.id, job.id, "/package"))
    assert resp.status_code == 200, resp.text
    assert resp.content == path.read_bytes()
    assert resp.headers["content-type"] == "application/zip"
    assert "filename*=UTF-8''" in resp.headers["content-disposition"]
    assert "%E5%BD%92%E6%A1%A3%E5%8C%85" in resp.headers["content-disposition"]  # 「归档包」


async def test_non_member_cannot_read_job_or_package(world, tmp_path):
    job, _ = await _job(world, tmp_path)
    who = await world.non_member()
    async with world.client(archive_router, user=who.user) as c:
        assert (await c.get(_url(world.target.id, job.id))).status_code == 403
        assert (await c.get(_url(world.target.id, job.id, "/package"))).status_code == 403


async def test_unauthenticated_is_401(world, tmp_path):
    job, _ = await _job(world, tmp_path)
    async with world.client(archive_router, user=None) as c:
        assert (await c.get(_url(world.target.id, job.id))).status_code == 401


async def test_job_bound_to_path_project(world, tmp_path):
    other = await world.other_project()
    job, _ = await _job(world, tmp_path, project=other)
    who = await world.readonly_member()
    async with world.client(archive_router, user=who.user) as c:
        assert (await c.get(_url(world.target.id, job.id))).status_code == 404
        assert (await c.get(_url(world.target.id, job.id, "/package"))).status_code == 404


async def test_package_unavailable_states(world, tmp_path):
    who = await world.readonly_member()
    failed, _ = await _job(world, tmp_path, status="failed")
    tampered, tampered_path = await _job(world, tmp_path)
    tampered_path.write_bytes(b"changed")
    unrecorded, _ = await _job(world, tmp_path, record=False)
    gone, gone_path = await _job(world, tmp_path)
    gone_path.unlink()
    async with world.client(archive_router, user=who.user) as c:
        assert (await c.get(_url(world.target.id, failed.id, "/package"))).status_code == 404
        for job in (tampered, unrecorded, gone):
            resp = await c.get(_url(world.target.id, job.id, "/package"))
            assert resp.status_code == 409, job.id
            assert "指纹不符" in resp.text


async def test_retry_needs_archive_manage(world, tmp_path):
    job, _ = await _job(world, tmp_path, status="failed")
    who = await world.readonly_member()
    async with world.client(archive_router, user=who.user) as c:
        resp = await c.post(_url(world.target.id, job.id, "/retry"))
    assert resp.status_code == 403
