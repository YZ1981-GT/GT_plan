"""证据类型登记表、缺省规则，以及入口上传不进旧的同名自动建版本（spec attachment-evidence-intake 需求 1.2、1.5）。

回归背景：旧版本模型按（项目、文件名、reference）归链。同一底稿两行各传一份「扫描件.pdf」会被串成 v1 / v2，
并对 v1 发替换信号、把它的下游标为失效；底稿内上传又一律记成 ``evidence``，证据声明「缺 XX 证据」上传后仍提示缺。
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import HTTPException

from app.core.config import settings
from app.models.attachment_models import Attachment
from app.services.attachment_service import AttachmentService
from app.services.attachment_upload_policy import ATTACHMENT_TYPES
from app.services.workpaper_evidence_intake import (
    EVIDENCE_TYPES,
    build_position,
    default_evidence_type,
    resolve_evidence_type,
    validate_evidence_type,
)
from app.services.workpaper_evidence_requirements import load_evidence_requirements_config
from tests.attachment_security_baseline._world import sqlite_attachment_world

PDF = b"%PDF-1.4\n%test\n"


def test_evidence_types_are_registered_attachment_types():
    assert EVIDENCE_TYPES <= ATTACHMENT_TYPES
    assert not EVIDENCE_TYPES & {"general", "workpaper_item"}


def test_every_declared_type_is_an_evidence_type():
    declared = {req["type"] for reqs in load_evidence_requirements_config().values() for req in reqs}
    assert declared, "证据声明为空，判据空转"
    assert declared <= EVIDENCE_TYPES


@pytest.mark.parametrize("value", ["voucher", " contract ", "stocktake", "note", "bank_statement"])
def test_validate_accepts_registered(value):
    assert validate_evidence_type(value) == value.strip()


@pytest.mark.parametrize("value", ["general", "workpaper_item", "statement", "other", "../x"])
def test_validate_rejects_unregistered(value):
    with pytest.raises(HTTPException) as exc:
        validate_evidence_type(value)
    assert exc.value.status_code == 422
    assert exc.value.detail["error_code"] == "EVIDENCE_TYPE_NOT_ALLOWED"


@pytest.mark.parametrize("value", [None, "", "  "])
def test_validate_empty_defers_to_default(value):
    assert validate_evidence_type(value) is None


@pytest.mark.parametrize(
    ("wp_code", "native", "expected"),
    [
        ("F3-5", None, "note"),            # F3 只声明票据
        ("H1-10", None, "stocktake"),      # H1 只声明盘点
        ("F2-24", None, "evidence"),       # F2 声明两类 ⇒ 不猜
        ("A1", None, "evidence"),          # 无声明
        (None, None, "evidence"),
        ("D4-2", ("contract", "D4"), "contract"),
        ("C23-2", ("contract", "D4"), "evidence"),   # d4/contract-ocr 被 C 类借用
        ("D40-1", ("contract", "D4"), "evidence"),   # 前缀不跨编号（D4 ≠ D40）
        ("E1-31", ("bank_statement", "E1"), "bank_statement"),
        ("F3-5", ("contract", "D4"), "note"),        # 借用时回到声明规则
    ],
)
def test_default_evidence_type(wp_code, native, expected):
    native_type, native_prefix = native or (None, None)
    assert default_evidence_type(wp_code, native_type=native_type, native_prefix=native_prefix) == expected


def test_requested_type_wins():
    assert resolve_evidence_type("voucher", "F3-5") == "voucher"
    assert resolve_evidence_type(None, "F3-5") == "note"


def test_position_limits():
    assert build_position(" F3-5 ", "item:3").cell_ref == "item:3"
    assert not build_position(None, "  ").is_row_level
    with pytest.raises(HTTPException) as exc:
        build_position("x" * 101, None)
    assert exc.value.status_code == 400


# ── 入口上传不进旧版本链 ──


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


@pytest.fixture
def replaced_signals(monkeypatch) -> list[dict]:
    calls: list[dict] = []

    async def _record(self, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(AttachmentService, "_emit_version_replaced_signal", _record)
    return calls


async def _upload_twice(world, *, version_chain: bool) -> list[Attachment]:
    svc = AttachmentService(world.db)
    meta = {"attachment_type": "evidence", "reference_type": "working_paper", "reference_id": uuid.uuid4()}
    ids = []
    for _ in range(2):
        row = await svc.upload_attachment_file(
            world.target.id, "扫描件.pdf", PDF, metadata=dict(meta), version_chain=version_chain,
        )
        ids.append(uuid.UUID(row["id"]))
    rows = (await world.db.execute(sa.select(Attachment).where(Attachment.id.in_(ids)))).scalars().all()
    return sorted(rows, key=lambda r: ids.index(r.id))


async def test_intake_uploads_are_independent_attachments(world, storage_root, replaced_signals):
    first, second = await _upload_twice(world, version_chain=False)
    assert (first.version, second.version) == (1, 1)
    assert first.previous_version_id is None and second.previous_version_id is None
    assert replaced_signals == []


async def test_legacy_upload_still_chains_by_name(world, storage_root, replaced_signals):
    """对照：默认参数下仍按旧模型归链（附件管理页「同名上传 = 新版本」不变）。"""
    first, second = await _upload_twice(world, version_chain=True)
    assert (first.version, second.version) == (1, 2)
    assert second.previous_version_id == first.id
    assert len(replaced_signals) == 1
