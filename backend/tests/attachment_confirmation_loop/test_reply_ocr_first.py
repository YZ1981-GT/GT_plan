"""回函识别先识别再比对（spec attachment-confirmation-evidence-loop 需求 2.1、2.2，ADR-ACE-02）。

改造前：抽屉「OCR 识别」只读附件已有全文，回函件挂上后从不识别 ⇒ 恒「低置信度 · 请先完成 OCR 识别」。
经 HTTP 真发请求（生产门禁 + 真实挂载行）；识别引擎在识别前置函数的下一层打桩（``UnifiedOCRService.recognize`` /
``AttachmentService.get_paperless_ocr``），``ensure_reply_text`` 与比对走生产代码。
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.models.attachment_models import Attachment
from app.models.confirmation_models import Confirmation, ConfirmationAttachmentLink
from app.routers import confirmations as confirmations_router_module
from app.services.attachment_service import AttachmentService
from app.services.unified_ocr_service import OCRServiceUnavailableError, UnifiedOCRService
from tests.attachment_security_baseline._world import add_attachment, add_confirmation, sqlite_attachment_world

ROUTER = confirmations_router_module.router
REPLY_TEXT = "致：测试客户\n截至2025-12-31余额 100.00 元\n"


@pytest_asyncio.fixture
async def world(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # 「storage/ 相对路径」兜底只会落在临时目录
    async with sqlite_attachment_world(monkeypatch) as w:
        yield w


async def _reply(world, tmp_path: Path, **att_values):
    """一笔已发函（账面 100）+ 发函件 + 回函件（缺省本地原件存在、没有识别全文）。"""
    conf = await add_confirmation(world, world.target)
    original = tmp_path / "回函.pdf"
    original.write_bytes(b"%PDF-1.4 reply")
    outbound = await add_attachment(world, world.target, file_name="发函.pdf", attachment_type="confirmation")
    values = {"file_name": "回函.pdf", "file_path": str(original), "attachment_type": "confirmation",
              "ocr_status": "pending", **att_values}
    inbound = await add_attachment(world, world.target, **values)
    for att, role in ((outbound, "outbound"), (inbound, "inbound")):
        await world._add(ConfirmationAttachmentLink(
            confirmation_id=conf.id, attachment_id=att.id, role=role, match_status="manual",
            paired_outbound_attachment_id=outbound.id if role == "inbound" else None,
        ))
    return conf, inbound


async def _post(world, attachment_id):
    user = (await world.edit_member()).user
    async with world.client(ROUTER, user=user) as client:
        return await client.post(f"/api/projects/{world.target.id}/confirmations/attachments/{attachment_id}/extract-compare")


async def _reload(world, att_id) -> Attachment:
    world.db.expire_all()
    return (await world.db.execute(sa.select(Attachment).where(Attachment.id == att_id))).scalar_one()


def _data(resp) -> dict:
    body = resp.json()
    return body.get("data", body) if isinstance(body, dict) else body


async def test_no_text_recognizes_original_then_compares(world, tmp_path):
    conf, inbound = await _reply(world, tmp_path)
    conf_id = conf.id  # expire_all 之后再读属性会触发同步懒加载
    recognize = AsyncMock(return_value={"text": REPLY_TEXT})
    with patch.object(UnifiedOCRService, "recognize", recognize):
        resp = await _post(world, inbound.id)
    assert resp.status_code == 200, resp.text
    data = _data(resp)
    assert (data["match_verdict"], data["reply_amount"], data["counterparty_mismatch"]) == ("matched", 100.0, False)
    recognize.assert_awaited_once()
    assert Path(recognize.await_args.args[0]).resolve() == (tmp_path / "回函.pdf").resolve()  # 识别的就是原件
    att = await _reload(world, inbound.id)
    assert (att.ocr_text, att.ocr_status) == (REPLY_TEXT, "completed")
    status = (await world.db.execute(sa.select(Confirmation.status).where(Confirmation.id == conf_id))).scalar_one()
    assert status == "sent"  # 识别比对不改函证状态（需求 2.2）


async def test_existing_text_is_not_recognized_again(world, tmp_path):
    _, inbound = await _reply(world, tmp_path, ocr_text=REPLY_TEXT, ocr_status="completed")
    recognize = AsyncMock(return_value={"text": "不该被用到"})
    with patch.object(UnifiedOCRService, "recognize", recognize):
        resp = await _post(world, inbound.id)
    assert resp.status_code == 200, resp.text
    recognize.assert_not_awaited()
    assert _data(resp)["match_verdict"] == "matched"


@pytest.mark.parametrize(("case", "status", "message"), [
    ("unavailable", 503, "识别服务不可用"),
    ("empty", 422, "没有识别到文字"),
    ("missing_file", 422, "原件文件不存在"),
])
async def test_failure_reports_and_gives_no_verdict(world, tmp_path, case, status, message):
    extra = {"file_path": str(tmp_path / "不存在.pdf")} if case == "missing_file" else {}
    _, inbound = await _reply(world, tmp_path, **extra)
    effect = OCRServiceUnavailableError("本机与服务器都连不上") if case == "unavailable" else None
    recognize = AsyncMock(return_value={"text": "   "}, side_effect=effect)
    with patch.object(UnifiedOCRService, "recognize", recognize):
        resp = await _post(world, inbound.id)
    assert resp.status_code == status, resp.text
    assert message in resp.text
    assert "match_verdict" not in resp.text  # 不出任何比对结论（尤其不出「相符」）
    att = await _reload(world, inbound.id)
    assert att.ocr_status == "failed"
    assert not (att.ocr_text or "").strip()
    assert att.ocr_fields_cache is None  # 比对没跑，缓存没写
    if case == "missing_file":
        recognize.assert_not_awaited()


@pytest.mark.parametrize(("paperless_text", "status"), [(REPLY_TEXT, 200), (None, 503)])
async def test_paperless_original_uses_paperless_text(world, tmp_path, paperless_text, status):
    _, inbound = await _reply(world, tmp_path, storage_type="paperless", paperless_document_id=42,
                              file_path="paperless://documents/42")
    fetch = AsyncMock(return_value=paperless_text)
    recognize = AsyncMock(return_value={"text": "不该被用到"})
    with patch.object(AttachmentService, "get_paperless_ocr", fetch), patch.object(UnifiedOCRService, "recognize", recognize):
        resp = await _post(world, inbound.id)
    assert resp.status_code == status, resp.text
    fetch.assert_awaited_once_with(42)
    recognize.assert_not_awaited()
    att = await _reload(world, inbound.id)
    assert att.ocr_status == ("completed" if status == 200 else "failed")
