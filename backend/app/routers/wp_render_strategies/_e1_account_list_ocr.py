"""E1 货币资金 — 已开立银行结算账户清单 OCR 识别端点

POST /api/workpapers/{wp_id}/e1/account-list-ocr
Content-Type: multipart/form-data
Body: file (PDF/image)

上传人行/基本户开户行打印的《已开立银行结算账户清单》，
OCR + LLM 提取账户行，供前端确认后回填 E1-10。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.attachment_ocr_writeback import (
    finalize_linked_ocr_writeback,
    load_reusable_ocr,
    parse_optional_uuid,
    provision_wp_linked_attachment,
)
from app.services.attachment_service import AttachmentService
from app.services.llm_client import chat_completion
from app.services.unified_ocr_service import UnifiedOCRService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["e1-ocr"])

ACCOUNT_ROW_SCHEMA = {
    "bank": "开户银行名称",
    "accountNo": "账号",
    "accountType": "账户性质（基本/一般/专用/临时等）",
    "accountStatus": "账户状态（正常/已注销/久悬等）",
    "openDate": "开户日期(YYYY-MM-DD)",
    "closeDate": "销户日期(YYYY-MM-DD，无则空)",
}

_EMPTY_FIELDS: dict[str, Any] = {
    "entityName": "",
    "printDate": "",
    "accounts": [],
}

_LLM_SYSTEM_PROMPT = (
    "你是注册会计师审计助手，专长于解读中国人民银行或商业银行出具的"
    "《已开立银行结算账户清单》。\n"
    "请从OCR文本中提取账户清单，严格返回JSON：\n"
    "{\n"
    '  "entityName": "清单上的单位/企业名称",\n'
    '  "printDate": "打印/查询日期 YYYY-MM-DD",\n'
    '  "accounts": [ '
    + json.dumps(ACCOUNT_ROW_SCHEMA, ensure_ascii=False)
    + " ]\n"
    "}\n"
    "规则：\n"
    "1. accounts 尽量提取清单中的全部账户；不要虚构未出现的账号。\n"
    "2. 日期统一 YYYY-MM-DD；无法判断留空。\n"
    "3. accountStatus 优先用原文；无则根据销户日期推断（有销户日填已注销，否则正常）。\n"
    "4. accountType 尽量规范为：基本存款账户/一般存款账户/专用存款账户/临时存款账户。"
)


class E1AccountListOcrResponse(BaseModel):
    attachment_id: str
    ocr_text: str
    extracted_fields: dict
    confidence: float
    reused: bool = False
    written_back: bool = False
    governed: bool = False
    requires_human_confirmation: bool = True


def _parse_llm_json(raw: str) -> dict:
    json_str = (raw or "").strip()
    if "```json" in json_str:
        json_str = json_str.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in json_str:
        json_str = json_str.split("```", 1)[1].split("```", 1)[0].strip()
    parsed = json.loads(json_str)
    return parsed if isinstance(parsed, dict) else {}


def _normalize_accounts(raw: Any) -> list[dict[str, str]]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
    if not isinstance(raw, list):
        return []
    rows: list[dict[str, str]] = []
    keys = ("bank", "accountNo", "accountType", "accountStatus", "openDate", "closeDate")
    for item in raw:
        if not isinstance(item, dict):
            continue
        row = {k: str(item.get(k) or "").strip() for k in keys}
        if not row["bank"] and not row["accountNo"]:
            continue
        if not row["accountStatus"]:
            row["accountStatus"] = "已注销" if row["closeDate"] else "正常"
        rows.append(row)
    return rows


def _normalize_fields(parsed: dict) -> dict[str, Any]:
    return {
        "entityName": str(parsed.get("entityName") or "").strip(),
        "printDate": str(parsed.get("printDate") or "").strip(),
        "accounts": _normalize_accounts(parsed.get("accounts")),
    }


@router.post("/api/workpapers/{wp_id}/e1/account-list-ocr", response_model=E1AccountListOcrResponse)
async def e1_account_list_ocr(
    wp_id: str,
    file: UploadFile = File(...),
    attachment_id: str | None = Form(None),
    force_reocr: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> E1AccountListOcrResponse:
    """上传《已开立银行结算账户清单》，OCR + AI 提取账户行供 E1-10 确认回填。"""
    try:
        wp_uuid = UUID(wp_id)
    except ValueError:
        raise HTTPException(400, "无效的 wp_id")

    linked_att_id = parse_optional_uuid(attachment_id)

    allowed = (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")
    filename = file.filename or "account-list.pdf"
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, f"不支持的文件类型: {suffix}，仅支持 {allowed}")

    if linked_att_id is not None and not force_reocr:
        reused = await load_reusable_ocr(db, linked_att_id)
        if reused is not None:
            fields = reused["extracted_fields"] or {}
            return E1AccountListOcrResponse(
                attachment_id=str(linked_att_id),
                ocr_text=reused["ocr_text"],
                extracted_fields=fields,
                confidence=float(reused.get("confidence") or 0),
                reused=True,
                written_back=False,
            )

    content = await file.read()
    out_attachment_id = str(linked_att_id) if linked_att_id else str(uuid4())
    if linked_att_id is None:
        out_attachment_id, linked_att_id = await provision_wp_linked_attachment(
            db,
            wp_id=wp_uuid,
            file_name=filename,
            content=content,
            attachment_type="support",
            created_by=getattr(_user, "id", None),
        )

    storage_dir = Path("storage/workpapers") / wp_id / "account-lists"
    storage_dir.mkdir(parents=True, exist_ok=True)
    file_path = storage_dir / f"{out_attachment_id}{suffix}"

    async with aiofiles.open(str(file_path), "wb") as f:
        await f.write(content)

    ocr_text = ""
    try:
        ocr_result = await UnifiedOCRService().recognize(str(file_path))
        ocr_text = ocr_result.get("text", "") or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("E1 account-list OCR failed for %s: %s", wp_id, e)
        if linked_att_id is not None:
            await AttachmentService(db).update_ocr_status(linked_att_id, "failed", ocr_text="")
            await db.commit()
        return E1AccountListOcrResponse(
            attachment_id=out_attachment_id,
            ocr_text="",
            extracted_fields=dict(_EMPTY_FIELDS),
            confidence=0,
        )

    if not ocr_text.strip():
        if linked_att_id is not None:
            await AttachmentService(db).update_ocr_status(linked_att_id, "failed", ocr_text="")
            await db.commit()
        return E1AccountListOcrResponse(
            attachment_id=out_attachment_id,
            ocr_text="",
            extracted_fields=dict(_EMPTY_FIELDS),
            confidence=0,
        )

    extracted_fields = dict(_EMPTY_FIELDS)
    confidence = 0.0
    try:
        messages = [
            {"role": "system", "content": _LLM_SYSTEM_PROMPT},
            {"role": "user", "content": f"OCR文本：\n{ocr_text[:12000]}"},
        ]
        llm_result = await chat_completion(messages=messages, temperature=0.1, max_tokens=5000)
        raw = llm_result if isinstance(llm_result, str) else str(llm_result)
        extracted_fields = _normalize_fields(_parse_llm_json(raw))
        accounts = extracted_fields.get("accounts") or []
        filled = (1 if extracted_fields.get("entityName") else 0) + (1 if accounts else 0)
        # 账户越多通常越完整，轻微加权
        confidence = round(min(1.0, filled / 2 + min(len(accounts), 10) * 0.03), 2)
    except Exception as e:  # noqa: BLE001
        logger.warning("E1 account-list LLM extraction failed for %s: %s", wp_id, e)
        if linked_att_id is not None:
            await AttachmentService(db).update_ocr_status(linked_att_id, "failed", ocr_text=ocr_text)
            await db.commit()
        return E1AccountListOcrResponse(
            attachment_id=out_attachment_id,
            ocr_text=ocr_text,
            extracted_fields=dict(_EMPTY_FIELDS),
            confidence=0,
        )

    out_attachment_id, written = await finalize_linked_ocr_writeback(
        db,
        wp_id=wp_uuid,
        linked_att_id=linked_att_id,
        temp_id=out_attachment_id,
        ocr_text=ocr_text,
        extracted_fields=extracted_fields,
        confidence=confidence,
    )
    return E1AccountListOcrResponse(
        attachment_id=out_attachment_id,
        ocr_text=ocr_text,
        extracted_fields=extracted_fields,
        confidence=confidence,
        written_back=written,
    )
