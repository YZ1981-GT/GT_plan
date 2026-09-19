"""D4 营业收入 — 合同OCR识别端点

POST /api/workpapers/{wp_id}/d4/contract-ocr
Content-Type: multipart/form-data
Body: file (PDF/image)
Optional: attachment_id（已关联附件时回流 ocr_text/ocr_fields_cache）, force_reocr

spec: attachment-workpaper-linkage-convergence Task 7.1（OCR 双轨归一试点）
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
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
)
from app.services.llm_client import chat_completion
from app.services.unified_ocr_service import UnifiedOCRService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["d4-ai"])

CONTRACT_FIELDS_SCHEMA = {
    "contractNo": "合同编号",
    "counterparty": "交易对方名称",
    "signDate": "合同签订日期",
    "serviceContent": "服务内容/提供产品名称",
    "contractAmount": "合同金额(数字)",
    "deliveryTime": "交货时间/服务期间",
    "deliveryMethod": "交货方式/提供服务方式",
    "settlementMethod": "结算方式",
    "settlementTime": "结算时间",
    "warrantyClause": "质量保证条款",
    "returnClause": "销售退回条款",
    "breachClause": "违约条款",
    "specialTerms": "特殊约定",
    "isSigned": "订立双方是否签字(Y/N/NA)",
    "isSealed": "订立双方是否盖章(Y/N/NA)",
    "recognitionMethod": "时段法/时点法",
    "acceptanceClause": "验收条款",
    "recognitionTime": "收入确认时间",
    "controlTransferDoc": "表明控制权转移的单据名称",
    "specialTransaction": "是否涉及特定交易及说明",
}

_EMPTY_FIELDS = {k: "" for k in CONTRACT_FIELDS_SCHEMA}
_EMPTY_FIELDS["contractAmount"] = 0


class D4ContractOcrResponse(BaseModel):
    attachment_id: str
    ocr_text: str
    extracted_fields: dict
    confidence: float
    reused: bool = False
    written_back: bool = False
    governed: bool = False
    requires_human_confirmation: bool = True


_LLM_SYSTEM_PROMPT = (
    "你是审计合同信息提取专家。请从以下OCR文本中提取销售合同的关键信息。\n"
    "严格按JSON格式返回以下字段（不确定的填空字符串，金额填0）：\n"
    f"{json.dumps(CONTRACT_FIELDS_SCHEMA, ensure_ascii=False, indent=2)}"
)


def _build_extraction_prompt(ocr_text: str) -> str:
    return f"OCR文本：\n{ocr_text[:6000]}"


def _resp(
    attachment_id: str,
    ocr_text: str,
    extracted_fields: dict,
    confidence: float,
    *,
    reused: bool = False,
    written_back: bool = False,
) -> D4ContractOcrResponse:
    return D4ContractOcrResponse(
        attachment_id=attachment_id,
        ocr_text=ocr_text,
        extracted_fields=extracted_fields,
        confidence=confidence,
        reused=reused,
        written_back=written_back,
        governed=False,
        requires_human_confirmation=True,
    )


async def _finalize(
    db: AsyncSession,
    wp_id: UUID,
    linked_att_id: UUID | None,
    temp_id: str,
    ocr_text: str,
    extracted_fields: dict,
    confidence: float,
) -> D4ContractOcrResponse:
    out_id, written = await finalize_linked_ocr_writeback(
        db,
        wp_id=wp_id,
        linked_att_id=linked_att_id,
        temp_id=temp_id,
        ocr_text=ocr_text,
        extracted_fields=extracted_fields,
        confidence=confidence,
    )
    return _resp(
        out_id,
        ocr_text,
        extracted_fields,
        confidence,
        reused=False,
        written_back=written,
    )


@router.post("/api/workpapers/{wp_id}/d4/contract-ocr")
async def d4_contract_ocr(
    wp_id: str,
    file: UploadFile = File(...),
    attachment_id: str | None = Form(None),
    force_reocr: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> D4ContractOcrResponse:
    """上传合同附件，OCR识别并提取字段；可选回流已关联附件证据链。"""
    linked_att_id = parse_optional_uuid(attachment_id)
    try:
        wp_uuid = UUID(wp_id)
    except ValueError:
        if linked_att_id is not None:
            raise HTTPException(400, "无效的 wp_id")
        wp_uuid = UUID(int=0)

    if linked_att_id is not None and not force_reocr:
        reused = await load_reusable_ocr(db, linked_att_id)
        if reused is not None:
            fields = reused["extracted_fields"] or {}
            merged = dict(_EMPTY_FIELDS)
            merged.update({k: fields[k] for k in CONTRACT_FIELDS_SCHEMA if k in fields})
            return _resp(
                str(linked_att_id),
                reused["ocr_text"],
                merged,
                float(reused.get("confidence") or 0),
                reused=True,
                written_back=False,
            )

    allowed_types = (".pdf", ".png", ".jpg", ".jpeg")
    filename = file.filename or "upload.pdf"
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed_types:
        raise HTTPException(400, f"不支持的文件类型: {suffix}，仅支持 {allowed_types}")

    temp_id = str(linked_att_id) if linked_att_id else str(uuid4())
    storage_dir = Path("storage/workpapers") / wp_id / "contracts"
    storage_dir.mkdir(parents=True, exist_ok=True)
    file_path = storage_dir / f"{temp_id}{suffix}"

    content = await file.read()
    async with aiofiles.open(str(file_path), "wb") as f:
        await f.write(content)

    ocr_text = ""
    try:
        ocr_service = UnifiedOCRService()
        ocr_result = await ocr_service.recognize(str(file_path))
        ocr_text = ocr_result.get("text", "")
    except Exception as e:
        logger.warning("D4 contract OCR failed for %s: %s", wp_id, e)
        return await _finalize(
            db, wp_uuid, linked_att_id, temp_id, "", dict(_EMPTY_FIELDS), 0.0,
        )

    if not ocr_text.strip():
        return await _finalize(
            db, wp_uuid, linked_att_id, temp_id, "", dict(_EMPTY_FIELDS), 0.0,
        )

    extracted_fields = dict(_EMPTY_FIELDS)
    confidence = 0.0

    try:
        messages = [
            {"role": "system", "content": _LLM_SYSTEM_PROMPT},
            {"role": "user", "content": _build_extraction_prompt(ocr_text)},
        ]
        llm_result = await chat_completion(
            messages=messages,
            temperature=0.1,
            max_tokens=2000,
        )

        if isinstance(llm_result, str):
            json_str = llm_result.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()

            parsed = json.loads(json_str)
            if isinstance(parsed, dict):
                for key in CONTRACT_FIELDS_SCHEMA:
                    if key in parsed and parsed[key] is not None:
                        extracted_fields[key] = parsed[key]

                filled = sum(
                    1 for k, v in extracted_fields.items()
                    if v and v != "" and v != 0
                )
                confidence = round(filled / len(CONTRACT_FIELDS_SCHEMA), 2)

    except Exception as e:
        logger.warning("D4 contract LLM extraction failed for %s: %s", wp_id, e)
        return await _finalize(
            db, wp_uuid, linked_att_id, temp_id, ocr_text, dict(_EMPTY_FIELDS), 0.0,
        )

    return await _finalize(
        db, wp_uuid, linked_att_id, temp_id, ocr_text, extracted_fields, confidence,
    )
