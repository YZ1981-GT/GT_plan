"""E1 货币资金 — 大额收支检查 OCR 识别端点（E1-23）

POST /api/workpapers/{wp_id}/e1/large-check-ocr
Content-Type: multipart/form-data
Body: file (PDF/image), side (debit|credit)

OCR + LLM 提取收支单据/审批信息，供前端 E1LargeCheckOcrConfirmDialog 确认后回填行。

@spec e1-orphan-components-wiring — Task 6
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.llm_client import chat_completion
from app.services.unified_ocr_service import UnifiedOCRService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["e1-ocr"])

_FIELD_SCHEMA = {
    "date": "收支日期 YYYY-MM-DD",
    "voucherNo": "凭证号",
    "businessContent": "摘要/业务内容",
    "counterAccount": "对方科目",
    "amount": "金额（正数）",
    "receiptDate": "收付款凭证日期 YYYY-MM-DD",
    "receiptParty": "收付款方/对方单位",
    "receiptAmount": "收付款单据金额（正数）",
    "approvalDateNo": "审批日期及文号",
    "isProperlyApproved": "是否经适当审批（是/否/不适用）",
    "otherSupportDocs": "其他佐证文件",
    "indexNo": "索引号",
}

_LLM_SYSTEM_PROMPT = (
    "你是注册会计师审计助手。请从OCR文本中提取大额收支检查所需的信息，"
    "严格返回JSON：\n"
    + json.dumps(_FIELD_SCHEMA, ensure_ascii=False, indent=2)
    + "\n规则：\n"
    "1. 金额取绝对值正数；无法确定时留0。\n"
    "2. 日期统一 YYYY-MM-DD；无法确定时留空串。\n"
    "3. isProperlyApproved 只允许「是」「否」「不适用」三值。\n"
    "4. 不要虚构OCR文本中未出现的内容。"
)


class LargeCheckOcrResponse(BaseModel):
    fields: dict[str, Any]
    confidence: float | None = None
    preview: str | None = None
    file_name: str = ""


def _parse_llm_json(raw: str) -> dict:
    json_str = (raw or "").strip()
    if "```json" in json_str:
        json_str = json_str.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in json_str:
        json_str = json_str.split("```", 1)[1].split("```", 1)[0].strip()
    parsed = json.loads(json_str)
    return parsed if isinstance(parsed, dict) else {}


def _safe_float(v: Any) -> float:
    try:
        if v is None or v == "":
            return 0.0
        return abs(float(str(v).replace(",", "").replace("，", "").strip()))
    except (TypeError, ValueError):
        return 0.0


def _normalize_fields(parsed: dict) -> dict[str, Any]:
    return {
        "date": str(parsed.get("date") or "").strip(),
        "voucherNo": str(parsed.get("voucherNo") or "").strip(),
        "businessContent": str(parsed.get("businessContent") or "").strip(),
        "counterAccount": str(parsed.get("counterAccount") or "").strip(),
        "amount": _safe_float(parsed.get("amount")),
        "receiptDate": str(parsed.get("receiptDate") or "").strip(),
        "receiptParty": str(parsed.get("receiptParty") or "").strip(),
        "receiptAmount": _safe_float(parsed.get("receiptAmount")),
        "approvalDateNo": str(parsed.get("approvalDateNo") or "").strip(),
        "isProperlyApproved": str(parsed.get("isProperlyApproved") or "").strip(),
        "otherSupportDocs": str(parsed.get("otherSupportDocs") or "").strip(),
        "indexNo": str(parsed.get("indexNo") or "").strip(),
    }


_EMPTY_FIELDS: dict[str, Any] = _normalize_fields({})


@router.post("/api/workpapers/{wp_id}/e1/large-check-ocr", response_model=LargeCheckOcrResponse)
async def e1_large_check_ocr(
    wp_id: str,
    file: UploadFile = File(...),
    side: str = Form("debit"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> LargeCheckOcrResponse:
    """上传收支单据/审批影像，OCR + AI 提取大额收支检查所需字段。"""
    try:
        UUID(wp_id)
    except ValueError:
        raise HTTPException(400, "无效的 wp_id")

    if side not in ("debit", "credit"):
        raise HTTPException(400, f"side 必须为 debit 或 credit，收到: {side}")

    allowed = (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")
    filename = file.filename or "large-check-doc.pdf"
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, f"不支持的文件类型: {suffix}")

    content = await file.read()
    tmp_dir = Path("storage/workpapers") / wp_id / "large-check-ocr"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"{uuid4()}{suffix}"
    tmp_path.write_bytes(content)

    # OCR
    ocr_text = ""
    try:
        ocr_result = await UnifiedOCRService().recognize(str(tmp_path))
        ocr_text = ocr_result.get("text", "") or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("E1 large-check OCR failed for %s: %s", wp_id, e)
        return LargeCheckOcrResponse(
            fields=dict(_EMPTY_FIELDS), confidence=0, preview="", file_name=filename
        )

    if not ocr_text.strip():
        return LargeCheckOcrResponse(
            fields=dict(_EMPTY_FIELDS), confidence=0, preview="", file_name=filename
        )

    # LLM extraction
    fields = dict(_EMPTY_FIELDS)
    confidence = 0.0
    try:
        user_msg = f"收支方向：{side}（{'借方/支出' if side == 'debit' else '贷方/收入'}）\nOCR文本：\n{ocr_text[:8000]}"
        messages = [
            {"role": "system", "content": _LLM_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]
        llm_result = await chat_completion(messages=messages, temperature=0.1, max_tokens=2000)
        raw = llm_result if isinstance(llm_result, str) else str(llm_result)
        fields = _normalize_fields(_parse_llm_json(raw))
        filled = sum(1 for v in fields.values() if v and v != 0 and v != 0.0)
        confidence = round(min(1.0, filled / len(fields)), 2)
    except Exception as e:  # noqa: BLE001
        logger.warning("E1 large-check LLM extraction failed for %s: %s", wp_id, e)

    return LargeCheckOcrResponse(
        fields=fields,
        confidence=confidence,
        preview=ocr_text[:500] if ocr_text else "",
        file_name=filename,
    )
