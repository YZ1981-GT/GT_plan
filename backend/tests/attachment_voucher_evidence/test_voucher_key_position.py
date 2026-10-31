"""证据链接带凭证键（spec attachment-voucher-evidence-binding 需求 1，ADR-AVE-01/05）。

回归背景：证据链接只有表页 / 单元格 / 页码，同一张凭证在另一张底稿里查不到已取得的原件；借合同识别端点识别
凭证时，缺省证据类型按底稿声明取（F1 声明函证 ⇒ 凭证附件被记成函证）。
"""
from __future__ import annotations

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import HTTPException

from app.models.attachment_models import Attachment, AttachmentWorkingPaper
from app.models.wp_optimization_models import EvidenceLink
from app.services.voucher_evidence import normalize_voucher_key
from app.services.workpaper_evidence_intake import build_position, resolve_evidence_type
from tests.attachment_evidence_intake._helpers import count, evidence_app, pdf, unwrap, use_local_storage
from tests.attachment_security_baseline._world import add_attachment, add_wp, sqlite_attachment_world
from tests.attachment_voucher_evidence._vk import vk

VK = vk()


@pytest_asyncio.fixture
async def world(monkeypatch, tmp_path):
    use_local_storage(tmp_path, monkeypatch)
    async with sqlite_attachment_world(monkeypatch) as w:
        yield w


def _base(project, wp) -> str:
    return f"/api/projects/{project.id}/workpapers/{wp.id}/evidence"


def test_normalize_voucher_key():
    assert normalize_voucher_key(None) is None and normalize_voucher_key("  ") is None
    spaced = '["2025", "default", "2025-01-07", "记", "0003"]'  # 规范化成紧凑串
    assert normalize_voucher_key(spaced) == VK
    for bad in ("0003", '["2025","default","2025-13-40","记","0003"]', '["2025","default","2025-01-07","记",""]',
                '["2025","default"]', "[" + "1" * 700 + "]"):
        with pytest.raises(HTTPException) as exc:
            normalize_voucher_key(bad)
        assert exc.value.status_code == 400


def test_position_and_default_type():
    pos = build_position(None, None, voucher_key=VK)
    assert pos.is_row_level and pos.voucher_key == VK
    assert resolve_evidence_type(None, "F1-7", voucher_keyed=True) == "voucher"
    assert resolve_evidence_type(None, "F1-7") == "confirmation"   # 不带凭证键：照旧按声明
    assert resolve_evidence_type("contract", "F1-7", voucher_keyed=True) == "contract"  # 显式类型优先


async def test_upload_with_voucher_key_writes_only_voucher_link(world):
    who = await world.edit_member()
    wp = await add_wp(world, world.target, wp_code="F1-7")
    async with world.client_for_app(evidence_app(), user=who.user) as client:
        resp = await client.post(f"{_base(world.target, wp)}/upload", files=pdf("凭证.pdf"), data={"voucher_key": VK})
        listed = await client.get(_base(world.target, wp))
    assert resp.status_code == 200, resp.text
    body = unwrap(resp.json())
    assert body["evidence_link"]["voucher_key"] == VK
    att = (await world.db.execute(sa.select(Attachment))).scalar_one()
    assert att.attachment_type == "voucher"            # 不再按 F1 的「函证」声明取缺省
    assert await count(world.db, AttachmentWorkingPaper) == 0
    link = (await world.db.execute(sa.select(EvidenceLink))).scalar_one()
    assert (link.voucher_key, link.sheet_name, link.cell_ref, link.evidence_type) == (VK, None, None, "voucher")
    assert [item["voucher_key"] for item in unwrap(listed.json())["items"]] == [VK]


async def test_bad_voucher_key_is_400_and_writes_nothing(world):
    who = await world.edit_member()
    wp = await add_wp(world, world.target, wp_code="D2-4")
    async with world.client_for_app(evidence_app(), user=who.user) as client:
        resp = await client.post(f"{_base(world.target, wp)}/upload", files=pdf(), data={"voucher_key": "0003"})
    assert resp.status_code == 400, resp.text
    assert await count(world.db, Attachment) == 0 and await count(world.db, EvidenceLink) == 0


async def test_link_with_voucher_key_is_idempotent(world):
    who = await world.edit_member()
    wp = await add_wp(world, world.target, wp_code="D2-4")
    att = await add_attachment(world, world.target)
    await world._add(AttachmentWorkingPaper(attachment_id=att.id, wp_id=wp.id, association_type="evidence"))
    payload = {"attachment_id": str(att.id), "voucher_key": VK, "sheet_name": "D2-4", "cell_ref": "row:r1"}
    async with world.client_for_app(evidence_app(), user=who.user) as client:
        first = await client.post(f"{_base(world.target, wp)}/link", json=payload)
        second = await client.post(f"{_base(world.target, wp)}/link", json=payload)
        other_row = await client.post(f"{_base(world.target, wp)}/link", json={**payload, "cell_ref": "row:r2"})
    assert first.status_code == second.status_code == other_row.status_code == 200
    assert unwrap(first.json())["id"] == unwrap(second.json())["id"]
    links = (await world.db.execute(sa.select(EvidenceLink).order_by(EvidenceLink.cell_ref))).scalars().all()
    assert [(link.cell_ref, link.evidence_type) for link in links] == [("row:r1", "voucher"), ("row:r2", "voucher")]


async def test_ocr_with_voucher_key_links_by_voucher(monkeypatch, tmp_path):
    """识别端点经依赖 ``ocr_intake_options`` 收凭证键：只写凭证链接、类型记凭证（借 d4 识别 F1 的凭证）。"""
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.routers.wp_render_strategies import _d4_contract_ocr as module
    from tests.attachment_evidence_intake._helpers import ocr_world

    ocr = MagicMock()
    ocr.return_value.recognize = AsyncMock(return_value={"text": "记账凭证 记-0003"})
    async with ocr_world(monkeypatch, tmp_path, module.router, wp_code="F1-7") as w:
        with patch.object(module, "UnifiedOCRService", ocr), patch.object(module, "chat_completion", AsyncMock(return_value="{}")):
            resp = await w.client.post(
                f"/api/workpapers/{w.wp.id}/d4/contract-ocr", files=pdf("凭证.pdf"),
                data={"evidence_voucher_key": VK, "evidence_sheet": "F1-7-current", "evidence_cell": "row:r1"},
            )
        assert resp.status_code == 200, resp.text
        att = (await w.db.execute(sa.select(Attachment))).scalar_one()
        assert att.attachment_type == "voucher"
        assert await count(w.db, AttachmentWorkingPaper) == 0
        link = (await w.db.execute(sa.select(EvidenceLink))).scalar_one()
        assert (link.voucher_key, link.sheet_name, link.cell_ref) == (VK, "F1-7-current", "row:r1")
