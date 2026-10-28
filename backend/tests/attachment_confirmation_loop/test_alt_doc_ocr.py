"""函证替代程序按单据类型识别（spec attachment-confirmation-evidence-loop 需求 3.1、3.2，ADR-ACE-03）。

改造前：替代程序页借 ``d4/contract-ocr``（合同字段）识别回款单 / 发票 / 对账单，前端按 ``date`` / ``金额`` 这类键取值，
与合同识别回执的 ``contractNo`` / ``contractAmount`` 对不上 ⇒ 几乎从不填入；L0-5 的识别地址缺底稿 id。
识别引擎与大模型在被测路由模块的下一层打桩（``UnifiedOCRService`` / ``chat_completion``），入口与写回走生产代码。
本文件同时承担 ``test_ocr_intake.py`` 对每个识别路由的三组断言（先建附件并写回 / 失败标识别失败 / 行级位置）。
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import sqlalchemy as sa

from app.models.attachment_models import Attachment
from app.routers.wp_render_strategies import _confirmation_alt_doc_ocr as module
from tests.attachment_evidence_intake._helpers import count, links_of, ocr_world, pdf, unwrap

URL = "/api/workpapers/{wp}/confirmation-alternative/doc-ocr"
OCR_TEXT = "中国工商银行 电子回单 付款人：甲公司 收款人：乙公司 金额：12,345.60 2025-12-31"
ROW = {"evidence_sheet": "D0-5", "evidence_cell": "row:r1"}


@contextmanager
def _engines(*, text: str = OCR_TEXT, llm: object = None, ocr_error: Exception | None = None):
    ocr = MagicMock()
    ocr.return_value.recognize = AsyncMock(return_value={"text": text}, side_effect=ocr_error)
    with patch.object(module, "UnifiedOCRService", ocr), patch.object(
        module, "chat_completion", AsyncMock(return_value=llm if llm is not None else "{}"),
    ) as chat:
        yield ocr.return_value.recognize, chat


async def _only_attachment(db) -> Attachment:
    rows = (await db.execute(sa.select(Attachment))).scalars().all()
    assert len(rows) == 1, [r.file_name for r in rows]
    return rows[0]


@pytest.mark.parametrize("doc_type", sorted(module.DOCUMENT_SCHEMAS))
async def test_each_type_returns_its_own_schema_only(monkeypatch, tmp_path, doc_type):
    schema = module.DOCUMENT_SCHEMAS[doc_type]
    first = next(iter(schema))
    llm = json.dumps({first: "识别值", "contractNo": "不该出现", "unknown": 1}, ensure_ascii=False)
    async with ocr_world(monkeypatch, tmp_path, module.router, wp_code="D0-5") as w:
        with _engines(llm=llm) as (_, chat):
            resp = await w.client.post(URL.format(wp=w.wp.id), files=pdf("单据.pdf"),
                                       data={"document_type": doc_type, **ROW})
        assert resp.status_code == 200, resp.text
        body = unwrap(resp.json())
        assert body["document_type"] == doc_type
        assert set(body["extracted_fields"]) == set(schema)  # 只回该类 schema 的键
        assert body["extracted_fields"][first] == "识别值"
        numeric = [k for k in schema if k in module.NUMERIC_FIELDS]
        assert all(body["extracted_fields"][k] == 0 for k in numeric if k != first)
        prompt = chat.await_args.kwargs["messages"][0]["content"]
        assert module.DOCUMENT_CONTEXTS[doc_type] in prompt and first in prompt


async def test_upload_creates_row_evidence_and_writes_back(monkeypatch, tmp_path):
    llm = json.dumps({"payer": "甲公司", "amount": 12345.6, "date": "2025-12-31"}, ensure_ascii=False)
    async with ocr_world(monkeypatch, tmp_path, module.router, wp_code="D0-5") as w:
        with _engines(llm=llm) as (recognize, _):
            resp = await w.client.post(URL.format(wp=w.wp.id), files=pdf("回单.pdf"),
                                       data={"document_type": "bank_receipt", **ROW})
        assert resp.status_code == 200, resp.text
        att = await _only_attachment(w.db)
        wp_links, ev_links = await links_of(w.db, att.id)
        assert wp_links == []  # 行级证据只写证据链接（ADR-AEI-02）
        assert [(e.sheet_name, e.cell_ref, e.evidence_type) for e in ev_links] == [("D0-5", "row:r1", "voucher")]
        assert att.attachment_type == "voucher"  # 回单 = 凭证 / 原始单据（不按 D0 声明记成「函证回函」）
        assert (att.ocr_text, att.ocr_status) == (OCR_TEXT, "completed")
        assert att.ocr_fields_cache["extracted_fields"]["payer"] == "甲公司"
        assert unwrap(resp.json())["attachment_id"] == str(att.id)
        assert Path(recognize.await_args.args[0]).resolve() == Path(att.file_path).resolve()  # 识别的就是附件原件


@pytest.mark.parametrize(("doc_type", "requested", "expected"), [
    ("contract", None, "contract"),
    ("statement", None, "support"),
    ("invoice", "support", "support"),  # 请求带了证据类型就用请求的
])
async def test_evidence_type_follows_document_type(monkeypatch, tmp_path, doc_type, requested, expected):
    data = {"document_type": doc_type, **ROW, **({"evidence_type": requested} if requested else {})}
    async with ocr_world(monkeypatch, tmp_path, module.router, wp_code="K0-6") as w:
        with _engines():
            resp = await w.client.post(URL.format(wp=w.wp.id), files=pdf(), data=data)
        assert resp.status_code == 200, resp.text
        att = await _only_attachment(w.db)
        assert att.attachment_type == expected


async def test_ocr_failure_marks_attachment_failed(monkeypatch, tmp_path):
    async with ocr_world(monkeypatch, tmp_path, module.router, wp_code="H0-5") as w:
        with _engines(ocr_error=RuntimeError("引擎不可用")) as (_, chat):
            resp = await w.client.post(URL.format(wp=w.wp.id), files=pdf(), data={"document_type": "invoice", **ROW})
        assert resp.status_code == 200, resp.text
        body = unwrap(resp.json())
        assert body["ocr_text"] == "" and set(body["extracted_fields"]) == set(module.DOCUMENT_SCHEMAS["invoice"])
        att = await _only_attachment(w.db)
        assert att.ocr_status == "failed"  # 不停在「识别中」
        chat.assert_not_awaited()


@pytest.mark.parametrize(("data", "file_name", "message"), [
    ({"document_type": "contract_d4"}, "单据.pdf", "不支持的单据类型"),
    ({"document_type": "invoice"}, "单据.docx", "不支持的文件类型"),
])
async def test_rejections_write_nothing(monkeypatch, tmp_path, data, file_name, message):
    async with ocr_world(monkeypatch, tmp_path, module.router, wp_code="D0-5") as w:
        with _engines() as (recognize, _):
            resp = await w.client.post(URL.format(wp=w.wp.id), files=pdf(file_name), data={**data, **ROW})
        assert resp.status_code == 400, resp.text
        assert message in resp.text
        assert await count(w.db, Attachment) == 0
        recognize.assert_not_awaited()


def test_document_types_have_contexts_and_evidence_types():
    assert set(module.DOCUMENT_SCHEMAS) == set(module.DOCUMENT_CONTEXTS) == set(module.DOCUMENT_EVIDENCE_TYPES)
    assert set(module.DOCUMENT_SCHEMAS) == {"bank_receipt", "invoice", "shipping", "statement", "contract", "voucher"}
