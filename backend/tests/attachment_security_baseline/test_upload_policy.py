"""附件上传落盘安全（spec attachment-security-baseline 需求 1.1–1.5）。

回归背景：``AttachmentService._write_local_file`` 把表单里的 ``attachment_type`` 直接拼进
``{root}/{project_id}/{attachment_type}/``；评估时在沙箱里传 ``../../escaped``，文件写到了存储根之外。
上传端点也不校验扩展名与内容、不写上传人。
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.core.config import settings
from app.models.attachment_models import Attachment
from app.routers.attachments import router as attachments_router
from app.services.attachment_service import AttachmentService
from app.services.attachment_upload_policy import (
    ALLOWED_EXTENSIONS,
    ATTACHMENT_TYPES,
    UploadRejected,
    ensure_within_root,
)
from tests.attachment_security_baseline._world import sqlite_attachment_world

REPO = Path(__file__).resolve().parents[3]
FRONT = REPO / "audit-platform" / "frontend" / "src"
PDF = b"%PDF-1.4\n%test\n"


@pytest_asyncio.fixture
async def world(monkeypatch):
    async with sqlite_attachment_world(monkeypatch) as w:
        yield w


@pytest.fixture
def storage_root(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "root"
    monkeypatch.setattr(settings, "ATTACHMENT_LOCAL_STORAGE_ROOT", str(root))
    monkeypatch.setattr(settings, "ATTACHMENT_PRIMARY_STORAGE", "local")
    return root


def _files_under(base: Path) -> list[str]:
    return sorted(p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file())


async def _attachment_count(world) -> int:
    return (await world.db.execute(sa.select(sa.func.count()).select_from(Attachment))).scalar_one()


# ── 服务层 ──

async def test_traversal_type_rejected_before_any_write(world, storage_root, tmp_path):
    svc = AttachmentService(world.db)
    with pytest.raises(UploadRejected) as exc:
        await svc.upload_attachment_file(
            world.target.id, "a.pdf", PDF, metadata={"attachment_type": "../../escaped"},
        )
    assert exc.value.code == "ATTACHMENT_TYPE_NOT_ALLOWED"
    assert _files_under(tmp_path) == []
    assert not (tmp_path / "escaped").exists()
    assert await _attachment_count(world) == 0


async def test_json_create_rejects_unknown_type(world):
    svc = AttachmentService(world.db)
    with pytest.raises(UploadRejected):
        await svc.create_attachment(world.target.id, {
            "file_name": "a.pdf", "file_path": "x", "attachment_type": "../x",
        })
    assert await _attachment_count(world) == 0


def test_root_check_rejects_escape(tmp_path):
    root = tmp_path / "root"
    with pytest.raises(UploadRejected) as exc:
        ensure_within_root(root / "p" / ".." / ".." / "escaped", root)
    assert exc.value.code == "STORAGE_PATH_REJECTED"
    assert ensure_within_root(root / "p" / "evidence", root) == (root / "p" / "evidence").resolve()


async def test_actor_and_audit_year_written(world, storage_root, monkeypatch):
    import app.services.project_audit_year as pay

    async def _year(_db, _pid):
        return 2025

    monkeypatch.setattr(pay, "fetch_project_audit_year", _year)
    user = await world.user()
    created = await AttachmentService(world.db).upload_attachment_file(
        world.target.id, "回函.pdf", PDF, metadata={"attachment_type": "confirmation"}, created_by=user.id,
    )
    row = await world.db.get(Attachment, uuid.UUID(created["id"]))
    assert (row.created_by, row.actor_type, row.actor_user_id, row.audit_year) == (user.id, "user", user.id, 2025)
    assert _files_under(storage_root) == [f"{world.target.id}/confirmation/回函.pdf"]


# ── 端点 ──

@pytest.mark.parametrize(("file_name", "content", "attachment_type", "status", "error_code"), [
    ("a.pdf", PDF, "../../escaped", 422, "ATTACHMENT_TYPE_NOT_ALLOWED"),
    ("a.exe", PDF, "evidence", 422, "FILE_TYPE_NOT_ALLOWED"),
    ("a.pdf", b"MZ\x90\x00binary", "evidence", 422, "UNSAFE_CONTENT"),
    ("a.pdf", b"#!/bin/sh\nrm -rf /\n", "evidence", 422, "UNSAFE_CONTENT"),
    ("回函.eml", b"From: a@b.c\r\nSubject: x\r\n\r\nbody", "confirmation", 200, None),
    ("凭证.pdf", PDF, "evidence", 200, None),
    # 访谈录音 / 监盘录像（spec attachment-evidence-intake 需求 6.1：白名单原先漏了音视频，弹窗上传恒 422）
    ("访谈录音.m4a", b"\x00\x00\x00\x20ftypM4A \x00\x00\x00\x00", "evidence", 200, None),
    ("监盘录像.mp4", b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00", "stocktake", 200, None),
    ("伪装录音.mp3", b"MZ\x90\x00\x03\x00\x00\x00", "evidence", 422, "UNSAFE_CONTENT"),
])
async def test_upload_endpoint_policy(world, storage_root, tmp_path, file_name, content, attachment_type, status, error_code):
    identity = await world.member("edit", "auditor")
    async with world.client(attachments_router, user=identity.user) as client:
        resp = await client.post(
            f"/api/projects/{world.target.id}/attachments/upload",
            files={"file": (file_name, content, "application/octet-stream")},
            data={"attachment_type": attachment_type},
        )
    assert resp.status_code == status, resp.text
    if error_code:
        assert resp.json()["detail"]["error_code"] == error_code
        assert _files_under(tmp_path) == []
        assert await _attachment_count(world) == 0
    else:
        row = (await world.db.execute(sa.select(Attachment))).scalar_one()
        assert row.created_by == identity.user.id and row.actor_user_id == identity.user.id


# ── 单一事实守卫 ──

def test_extension_allowlist_matches_attachment_management_accept_types():
    text = (FRONT / "views" / "AttachmentManagement.vue").read_bytes().decode("utf-8")
    block = re.search(r"const ACCEPT_TYPES = \[(.*?)\]\.join", text, re.S)
    assert block, "AttachmentManagement.vue 里找不到 ACCEPT_TYPES 数组"
    front = set(re.findall(r"'(\.[a-z0-9]+)'", block.group(1)))
    assert len(front) >= 20, "ACCEPT_TYPES 解析结果过少，正则可能失效"
    assert front == set(ALLOWED_EXTENSIONS)


_FRONT_TYPE_PATTERNS = (
    re.compile(r"append\(\s*['\"]attachment_type['\"]\s*,\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"ATTACHMENT_TYPE\s*=\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"attachmentType\s*\|\|\s*['\"]([^'\"]+)['\"]"),
)
_BACK_TYPE_PATTERNS = (
    re.compile(r"attachment_type\s*=\s*\"([a-z_]+)\""),
    re.compile(r"[\"']attachment_type[\"']\s*:\s*\"([a-z_]+)\""),
    # 识别端点经证据入口建附件：native_type 即落库的附件类型（spec attachment-evidence-intake ADR-AEI-06）
    re.compile(r"native_type\s*=\s*\"([a-z_]+)\""),
)


def test_frontend_and_backend_attachment_type_literals_are_registered():
    found: dict[str, set[str]] = {}
    for f in FRONT.rglob("*"):
        if f.suffix in {".vue", ".ts"} and "__tests__" not in f.parts and ".spec." not in f.name:
            text = f.read_bytes().decode("utf-8", errors="replace")
            for p in _FRONT_TYPE_PATTERNS:
                for m in p.finditer(text):
                    found.setdefault(m.group(1), set()).add(f.name)
    for f in (REPO / "backend" / "app").rglob("*.py"):
        text = f.read_bytes().decode("utf-8", errors="replace")
        if "attachment_type" not in text and "native_type" not in text:
            continue
        for p in _BACK_TYPE_PATTERNS:
            for m in p.finditer(text):
                found.setdefault(m.group(1), set()).add(f.name)
    # workpaper_item 自 spec attachment-evidence-intake 起已无写入方（行级上传改写证据链接 + 证据类型），
    # 仍在登记表里供历史数据筛选
    known = {"evidence", "confirmation", "bank_statement", "support",
             "voucher", "contract", "stocktake", "note"}
    assert known <= set(found), f"扫描器漏掉了已知写入方：{sorted(known - set(found))}"
    unregistered = {k: sorted(v) for k, v in found.items() if k not in ATTACHMENT_TYPES}
    assert unregistered == {}


def test_evidence_requirement_types_are_registered():
    data = json.loads((REPO / "backend" / "data" / "workpaper_evidence_requirements.json").read_bytes().decode("utf-8"))
    types = {item["type"] for key, items in data.items() if not key.startswith("_") for item in items}
    assert types and types <= ATTACHMENT_TYPES
