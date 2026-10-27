"""OCR 字段与任务端点按附件所属项目判权限（spec attachment-security-baseline 需求 2.3）。

改造前两个端点只校验登录：``POST /api/attachments/{id}/ocr-fields`` 对未关联底稿的附件任何登录用户都能读识别字段、
触发识别（写库 + 后台识别）；``GET /api/ocr-jobs/{job_id}`` 任何人拿到任务号就能读识别结果。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.routers import ocr_fields as ocr_fields_router
from app.services import ocr_fields_service
from app.services.ocr_fields_service import OcrFieldsService
from tests.attachment_security_baseline._world import add_attachment, sqlite_attachment_world

ROUTER = ocr_fields_router.router
GATE = "app.deps.assert_project_permission"


@pytest_asyncio.fixture
async def world(monkeypatch):
    async with sqlite_attachment_world(monkeypatch) as w:
        yield w


async def _user(world, key: str):
    if key == "anonymous":
        return None
    if key == "non_member":
        return (await world.non_member()).user
    if key == "readonly":
        return (await world.member("readonly", "readonly")).user
    if key == "edit":
        return (await world.member("edit", "auditor")).user
    if key == "archived_edit":
        return (await world.archived_edit_member()).user
    if key == "admin":
        return (await world.admin_non_member()).user
    raise KeyError(key)


_CACHE = {"fields": [{"field_name": "amount", "field_value": "100"}], "document_type": "invoice"}


@pytest.mark.parametrize(("identity", "expected"), [
    ("anonymous", 401), ("non_member", 403), ("readonly", 200), ("edit", 200), ("admin", 200), ("archived_edit", 200),
])
async def test_reading_cached_fields_needs_readonly(world, identity, expected):
    att = await add_attachment(world, world.target, ocr_status="completed", ocr_fields_cache=_CACHE)
    user = await _user(world, identity)
    trigger = world.stub(OcrFieldsService, "_run_ocr_async", None)  # 读缓存不应调度识别
    async with world.client(ROUTER, user=user) as client:
        resp = await client.post(f"/api/attachments/{att.id}/ocr-fields")
    assert resp.status_code == expected, resp.text
    if expected == 200:
        assert resp.json()["fields"] == _CACHE
    assert trigger.count == 0


@pytest.mark.parametrize(("identity", "expected"), [
    ("anonymous", 401), ("non_member", 403), ("readonly", 403), ("edit", 202), ("admin", 202), ("archived_edit", 423),
])
async def test_triggering_recognition_needs_edit(world, identity, expected):
    att = await add_attachment(world, world.target, ocr_status="pending")
    user = await _user(world, identity)
    trigger = world.stub(OcrFieldsService, "get_or_trigger_ocr_fields",
                         ({"status": "processing", "attachment_id": str(att.id), "job_id": "j"}, 202))
    async with world.client(ROUTER, user=user) as client:
        resp = await client.post(f"/api/attachments/{att.id}/ocr-fields")
    assert resp.status_code == expected, resp.text
    assert trigger.count == (1 if expected == 202 else 0)
    if identity != "anonymous":
        client.assert_passed(GATE, times=1)


async def test_unknown_or_deleted_attachment_is_404(world):
    deleted = await add_attachment(world, world.target, is_deleted=True, ocr_status="pending")
    user = await _user(world, "edit")
    trigger = world.stub(OcrFieldsService, "get_or_trigger_ocr_fields", ({}, 202))
    async with world.client(ROUTER, user=user) as client:
        missing = await client.post(f"/api/attachments/{uuid.uuid4()}/ocr-fields")
        gone = await client.post(f"/api/attachments/{deleted.id}/ocr-fields")
    assert (missing.status_code, gone.status_code) == (404, 404)
    assert trigger.count == 0


@pytest.mark.parametrize(("identity", "expected"), [
    ("anonymous", 401), ("non_member", 403), ("readonly", 200), ("edit", 200), ("admin", 200),
])
async def test_job_status_needs_readonly_on_attachment_project(world, identity, expected):
    att = await add_attachment(world, world.target)
    job = {"status": "completed", "attachment_id": str(att.id), "result": {"fields": []}}
    world.monkeypatch.setitem(ocr_fields_service._ocr_jobs, "job-asb", job)
    user = await _user(world, identity)
    async with world.client(ROUTER, user=user) as client:
        resp = await client.get("/api/ocr-jobs/job-asb")
    assert resp.status_code == expected, resp.text
    if expected == 200:
        assert resp.json()["attachment_id"] == str(att.id)


async def test_job_of_other_project_is_403_and_orphan_job_is_404(world):
    other = await world.other_project()
    att_b = await add_attachment(world, other)
    world.monkeypatch.setitem(ocr_fields_service._ocr_jobs, "job-b", {"status": "completed", "attachment_id": str(att_b.id)})
    world.monkeypatch.setitem(ocr_fields_service._ocr_jobs, "job-orphan", {"status": "failed", "attachment_id": str(uuid.uuid4())})
    world.monkeypatch.setitem(ocr_fields_service._ocr_jobs, "job-bad", {"status": "failed", "attachment_id": "x"})
    user = await _user(world, "edit")  # 目标项目的 edit 成员，不是项目 B 成员
    async with world.client(ROUTER, user=user) as client:
        foreign = await client.get("/api/ocr-jobs/job-b")
        orphan = await client.get("/api/ocr-jobs/job-orphan")
        bad = await client.get("/api/ocr-jobs/job-bad")
        unknown = await client.get("/api/ocr-jobs/nope")
    assert [r.status_code for r in (foreign, orphan, bad, unknown)] == [403, 404, 404, 404]
