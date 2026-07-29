"""G1 交易性金融资产 — 合同/协议 OCR 识别端点（G1-14 衍生金融工具核查）.

POST /api/workpapers/{wp_id}/g1/contract-ocr
Content-Type: multipart/form-data
Body: file (PDF/image)
Optional: attachment_id（已关联附件时回流 ocr_text/ocr_fields_cache）, force_reocr

识别贷款/投资/存款等协议，判断是否含影响合同价值的变量（利率/汇率/商品价格/
指数/信用等级等），供 G1-14 衍生识别 B 问卷自动勾选参考。
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

router = APIRouter(tags=["g1-ocr"])

# B 问卷 8 项影响变量（与前端 G1_DERIVATIVE_B_VARIABLES 对齐）
_B_VARIABLE_FIELDS = {
    "b1_interestRate": "是否含利率挂钩/浮动利率条款(true/false)",
    "b2_financialPrice": "是否含金融工具价格挂钩条款(true/false)",
    "b3_commodityPrice": "是否含商品价格挂钩条款(true/false)",
    "b4_exchangeRate": "是否含汇率挂钩/外币结算条款(true/false)",
    "b5_priceIndex": "是否含价格或利率指数挂钩条款(true/false)",
    "b6_creditRating": "是否含信用等级/信用指数挂钩条款(true/false)",
    "b7_otherFinancial": "是否含其它金融变量条款(true/false)",
    "b8_otherNonFinancial": "是否含其它非金融变量(非合同一方特有)条款(true/false)",
}

_META_FIELDS = {
    "instrumentName": "工具/合同名称",
    "counterparty": "对手方",
    "summary": "识别摘要",
}

_EMPTY: dict = {k: False for k in _B_VARIABLE_FIELDS}
_EMPTY.update({k: "" for k in _META_FIELDS})

_ALL_SCHEMA = {**_B_VARIABLE_FIELDS, **_META_FIELDS}


class G1ContractOcrResponse(BaseModel):
    attachment_id: str
    ocr_text: str
    extracted_fields: dict
    summary: str
    confidence: float
    reused: bool = False
    written_back: bool = False
    governed: bool = False
    requires_human_confirmation: bool = True


def _resp(
    attachment_id: str,
    ocr_text: str,
    extracted_fields: dict,
    summary: str,
    confidence: float,
    *,
    reused: bool = False,
    written_back: bool = False,
) -> G1ContractOcrResponse:
    return G1ContractOcrResponse(
        attachment_id=attachment_id,
        ocr_text=ocr_text,
        extracted_fields=extracted_fields,
        summary=summary,
        confidence=confidence,
        reused=reused,
        written_back=written_back,
        governed=False,
        requires_human_confirmation=True,
    )


@router.post("/api/workpapers/{wp_id}/g1/contract-ocr", response_model=G1ContractOcrResponse)
async def g1_contract_ocr(
    wp_id: str,
    file: UploadFile = File(...),
    attachment_id: str | None = Form(None),
    force_reocr: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> G1ContractOcrResponse:
    """上传合同/协议附件，OCR识别并提取衍生变量；可选回流已关联附件证据链。"""
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
            merged = dict(_EMPTY)
            for key in _B_VARIABLE_FIELDS:
                if key in fields:
                    merged[key] = bool(fields[key])
            for key in _META_FIELDS:
                if key in fields and fields[key] is not None:
                    merged[key] = str(fields[key])
            summary = str(merged.get("summary") or (reused["ocr_text"] or "")[:200].replace("\n", " "))
            return _resp(
                str(linked_att_id),
                reused["ocr_text"],
                merged,
                summary,
                float(reused.get("confidence") or 0),
                reused=True,
                written_back=False,
            )

    allowed = (".pdf", ".png", ".jpg", ".jpeg")
    filename = file.filename or "upload.pdf"
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, f"不支持的文件类型: {suffix}")

    temp_id = str(linked_att_id) if linked_att_id else str(uuid4())
    storage_dir = Path("storage/workpapers") / wp_id / "contracts"
    storage_dir.mkdir(parents=True, exist_ok=True)
    file_path = storage_dir / f"{temp_id}{suffix}"

    content = await file.read()
    async with aiofiles.open(str(file_path), "wb") as f:
        await f.write(content)

    ocr_text = ""
    try:
        ocr_result = await UnifiedOCRService().recognize(str(file_path))
        ocr_text = ocr_result.get("text", "")
    except Exception as e:  # noqa: BLE001
        logger.warning("G1 contract OCR failed: %s", e)
        return _resp(temp_id, "", dict(_EMPTY), "", 0.0)

    if not ocr_text.strip():
        return _resp(temp_id, "", dict(_EMPTY), "", 0.0)

    extracted = dict(_EMPTY)
    summary = ocr_text[:200].replace("\n", " ")
    try:
        messages = [
            {
                "role": "system",
                "content": (
                    "你是审计衍生工具识别专家。阅读合同/协议 OCR 文本，判断合同价值是否"
                    "受下列变量影响（用于识别衍生或嵌入衍生特征）。"
                    "布尔字段：识别到相关条款填 true，否则 false。"
                    f"严格返回 JSON：{json.dumps(_ALL_SCHEMA, ensure_ascii=False)}"
                ),
            },
            {"role": "user", "content": f"合同 OCR 文本：\n{ocr_text[:5000]}"},
        ]
        llm_result = await chat_completion(messages=messages, temperature=0.1, max_tokens=800)
        if isinstance(llm_result, str):
            json_str = llm_result.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()
            parsed = json.loads(json_str)
            if isinstance(parsed, dict):
                for key in _B_VARIABLE_FIELDS:
                    if key in parsed:
                        extracted[key] = bool(parsed[key])
                for key in _META_FIELDS:
                    if key in parsed and parsed[key] is not None:
                        extracted[key] = str(parsed[key])
                summary = str(extracted.get("summary") or summary)
    except Exception as e:  # noqa: BLE001
        logger.warning("G1 contract LLM extract failed: %s", e)

    # 置信度：命中的布尔项数 / 总布尔项（有识别就有信心）
    hit = sum(1 for k in _B_VARIABLE_FIELDS if extracted.get(k))
    confidence = round(min(1.0, 0.3 + hit * 0.1), 2) if ocr_text.strip() else 0.0

    out_id, written = await finalize_linked_ocr_writeback(
        db,
        wp_id=wp_uuid,
        linked_att_id=linked_att_id,
        temp_id=temp_id,
        ocr_text=ocr_text,
        extracted_fields=extracted,
        confidence=confidence,
    )
    return _resp(out_id, ocr_text, extracted, summary, confidence, written_back=written)
