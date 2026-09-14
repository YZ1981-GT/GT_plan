"""E1 货币资金 — 银行账户清单完整性承诺函 OCR 识别端点

POST /api/workpapers/{wp_id}/e1/commit-ocr
Content-Type: multipart/form-data
Body: file (PDF/image)

上传盖章承诺函扫描件，OCR 后由 LLM 提取签署信息与账户清单，
供前端确认后回填 E1-11。
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

COMMIT_FIELDS_SCHEMA = {
    "unit": "被审计单位/本公司全称",
    "legalRep": "法定代表人姓名",
    "finance": "财务负责人姓名",
    "date": "声明日期(YYYY-MM-DD)",
    "signConfirm": "是否已签字盖章(Y/N)",
    "checkSummary": "根据承诺函内容概括的账户核对摘要（可选）",
    "accounts": [
        {
            "bank": "开户银行名称",
            "accountNo": "银行账号",
            "accountType": "账户性质",
            "openDate": "开户日期(YYYY-MM-DD)",
            "closeDate": "销户日期(YYYY-MM-DD，无则空)",
            "accountStatus": "目前状态",
            "restrictionStatus": "冻结、抵押、质押情况",
        }
    ],
}

_EMPTY_FIELDS: dict[str, Any] = {
    "unit": "",
    "legalRep": "",
    "finance": "",
    "date": "",
    "signConfirm": "",
    "checkSummary": "",
    "accounts": [],
}

_LLM_SYSTEM_PROMPT = (
    "你是注册会计师审计助手，专长于解读公司致会计师事务所的银行账户清单完整性承诺函。\n"
    "请从以下OCR文本中提取承诺函签署信息与账户清单。\n"
    "严格按JSON格式返回以下字段（不确定的填空字符串；Y/N 仅填 Y 或 N 或空；accounts 为数组）：\n"
    f"{json.dumps(COMMIT_FIELDS_SCHEMA, ensure_ascii=False, indent=2)}\n"
    "规则：\n"
    "1. accounts：提取承诺函中的全部银行账户行；无表则返回空数组。\n"
    "2. 日期统一为 YYYY-MM-DD；无法判断则留空。\n"
    "3. 若文中已盖章/签字，signConfirm 填 Y；明确未签则 N；无法判断留空。\n"
    "4. checkSummary：用一两句话概括账户数量及受限/销户情况；不要逐字复述承诺正文。\n"
    "5. 不要虚构未在原文出现的账号或银行名。"
)


class E1CommitOcrResponse(BaseModel):
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
    keys = ("bank", "accountNo", "accountType", "openDate", "closeDate", "accountStatus", "restrictionStatus")
    for item in raw:
        if not isinstance(item, dict):
            continue
        row = {k: str(item.get(k) or "").strip() for k in keys}
        if not row["bank"] and not row["accountNo"]:
            continue
        if not row["accountStatus"]:
            row["accountStatus"] = "正常"
        if not row["restrictionStatus"]:
            row["restrictionStatus"] = "无"
        rows.append(row)
    return rows


def _normalize_fields(parsed: dict) -> dict[str, Any]:
    out = dict(_EMPTY_FIELDS)
    for key in ("unit", "legalRep", "finance", "date", "checkSummary"):
        if key in parsed and parsed[key] is not None:
            out[key] = str(parsed[key]).strip()
    sign = str(parsed.get("signConfirm") or "").strip().upper()
    if sign in {"Y", "是", "已签", "已签字盖章确认"}:
        out["signConfirm"] = "Y"
    elif sign in {"N", "否", "未签", "未签署"}:
        out["signConfirm"] = "N"
    else:
        out["signConfirm"] = ""
    out["accounts"] = _normalize_accounts(parsed.get("accounts"))
    return out


@router.post("/api/workpapers/{wp_id}/e1/commit-ocr", response_model=E1CommitOcrResponse)
async def e1_commit_ocr(
    wp_id: str,
    file: UploadFile = File(...),
    attachment_id: str | None = Form(None),
    force_reocr: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> E1CommitOcrResponse:
    """上传银行账户完整性承诺函，OCR + AI 提取 E1-11 字段与账户清单。"""
    try:
        wp_uuid = UUID(wp_id)
    except ValueError:
        raise HTTPException(400, "无效的 wp_id")

    linked_att_id = parse_optional_uuid(attachment_id)

    allowed = (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")
    filename = file.filename or "commitment-letter.pdf"
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, f"不支持的文件类型: {suffix}，仅支持 {allowed}")

    if linked_att_id is not None and not force_reocr:
        reused = await load_reusable_ocr(db, linked_att_id)
        if reused is not None:
            return E1CommitOcrResponse(
                attachment_id=str(linked_att_id),
                ocr_text=reused["ocr_text"],
                extracted_fields=reused["extracted_fields"] or {},
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

    storage_dir = Path("storage/workpapers") / wp_id / "commitment-letters"
    storage_dir.mkdir(parents=True, exist_ok=True)
    file_path = storage_dir / f"{out_attachment_id}{suffix}"

    async with aiofiles.open(str(file_path), "wb") as f:
        await f.write(content)

    ocr_text = ""
    try:
        ocr_result = await UnifiedOCRService().recognize(str(file_path))
        ocr_text = ocr_result.get("text", "") or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("E1 commit OCR failed for %s: %s", wp_id, e)
        if linked_att_id is not None:
            await AttachmentService(db).update_ocr_status(linked_att_id, "failed", ocr_text="")
            await db.commit()
        return E1CommitOcrResponse(
            attachment_id=out_attachment_id,
            ocr_text="",
            extracted_fields=dict(_EMPTY_FIELDS),
            confidence=0,
        )

    if not ocr_text.strip():
        if linked_att_id is not None:
            await AttachmentService(db).update_ocr_status(linked_att_id, "failed", ocr_text="")
            await db.commit()
        return E1CommitOcrResponse(
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
            {"role": "user", "content": f"OCR文本：\n{ocr_text[:10000]}"},
        ]
        llm_result = await chat_completion(messages=messages, temperature=0.1, max_tokens=4000)
        raw = llm_result if isinstance(llm_result, str) else str(llm_result)
        parsed = _parse_llm_json(raw)
        extracted_fields = _normalize_fields(parsed)
        scalar_keys = ("unit", "legalRep", "finance", "date", "signConfirm", "checkSummary")
        filled = sum(1 for k in scalar_keys if extracted_fields.get(k))
        filled += 1 if extracted_fields.get("accounts") else 0
        confidence = round(filled / (len(scalar_keys) + 1), 2)
    except Exception as e:  # noqa: BLE001
        logger.warning("E1 commit LLM extraction failed for %s: %s", wp_id, e)
        if linked_att_id is not None:
            await AttachmentService(db).update_ocr_status(linked_att_id, "failed", ocr_text=ocr_text)
            await db.commit()
        return E1CommitOcrResponse(
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
    return E1CommitOcrResponse(
        attachment_id=out_attachment_id,
        ocr_text=ocr_text,
        extracted_fields=extracted_fields,
        confidence=confidence,
        written_back=written,
    )
