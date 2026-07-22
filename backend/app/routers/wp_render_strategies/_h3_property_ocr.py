"""H3 投资性房地产 — 不动产权证 OCR 识别端点

POST /api/workpapers/{wp_id}/h3/real-estate-title-ocr
Content-Type: multipart/form-data
Body: file (PDF/image)

上传不动产权证/房屋所有权证/土地使用权证扫描件，OCR 后提取权属核对关键字段，
供 H3-12 产权核对表逐行预填（权利人/证载面积/用途/权证号/抵押受限等）。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.llm_client import chat_completion
from app.services.unified_ocr_service import UnifiedOCRService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["h3-ai"])

TITLE_FIELDS_SCHEMA = {
    "titleCertNo": "不动产权证号/房屋所有权证号/土地使用权证号",
    "certOwner": "权利人/所有权人",
    "coOwnership": "共有情况(单独所有/共同共有/按份共有等)",
    "address": "房屋坐落/不动产坐落",
    "issueDate": "登记时间/发证日期(YYYY-MM-DD)",
    "propertyNature": "权利类型/不动产性质(如国有建设用地使用权/房屋所有权)",
    "certPurpose": "规划用途/房屋用途(如商业/办公/出租)",
    "buildingArea": "建筑面积(数字,平方米)",
    "landArea": "土地面积/宗地面积(数字,平方米)",
    "usefulLife": "使用期限/土地使用期限",
    "issuingAuthority": "颁发单位/登记机构",
    "otherRights": "他项权利/备注栏抵押查封等",
    "mortgagee": "抵押权人(若有)",
    "mortgageNature": "抵押性质(若有,如最高额抵押)",
}

_EMPTY_FIELDS: dict = {k: "" for k in TITLE_FIELDS_SCHEMA}
_EMPTY_FIELDS["buildingArea"] = 0
_EMPTY_FIELDS["landArea"] = 0

_LLM_SYSTEM_PROMPT = (
    "你是审计不动产权属证明信息提取专家。"
    "请从以下OCR文本中提取中国不动产权证书/房屋所有权证书/土地使用权证书的关键信息。\n"
    "严格按JSON格式返回以下字段（不确定的填空字符串，面积填0）：\n"
    f"{json.dumps(TITLE_FIELDS_SCHEMA, ensure_ascii=False, indent=2)}"
)


class H3TitleOcrResponse(BaseModel):
    attachment_id: str
    ocr_text: str
    extracted_fields: dict
    confidence: float


def _build_extraction_prompt(ocr_text: str) -> str:
    return f"OCR文本：\n{ocr_text[:6000]}"


@router.post("/api/workpapers/{wp_id}/h3/real-estate-title-ocr")
async def h3_real_estate_title_ocr(
    wp_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> H3TitleOcrResponse:
    """上传不动产权证附件，OCR识别并提取权属字段供 H3-12 预填"""
    _ = db, current_user

    allowed_types = (".pdf", ".png", ".jpg", ".jpeg")
    filename = file.filename or "upload.pdf"
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed_types:
        raise HTTPException(400, f"不支持的文件类型: {suffix}，仅支持 {allowed_types}")

    attachment_id = str(uuid4())
    storage_dir = Path("storage/workpapers") / wp_id / "h3-title-certs"
    storage_dir.mkdir(parents=True, exist_ok=True)
    file_path = storage_dir / f"{attachment_id}{suffix}"

    content = await file.read()
    async with aiofiles.open(str(file_path), "wb") as f:
        await f.write(content)

    ocr_text = ""
    try:
        ocr_service = UnifiedOCRService()
        ocr_result = await ocr_service.recognize(str(file_path))
        ocr_text = ocr_result.get("text", "")
    except Exception as e:
        logger.warning("H3 title OCR failed for %s: %s", wp_id, e)
        return H3TitleOcrResponse(
            attachment_id=attachment_id,
            ocr_text="",
            extracted_fields=dict(_EMPTY_FIELDS),
            confidence=0,
        )

    if not ocr_text.strip():
        return H3TitleOcrResponse(
            attachment_id=attachment_id,
            ocr_text="",
            extracted_fields=dict(_EMPTY_FIELDS),
            confidence=0,
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
                for key in TITLE_FIELDS_SCHEMA:
                    if key in parsed and parsed[key] is not None:
                        extracted_fields[key] = parsed[key]

                filled = sum(
                    1 for _k, v in extracted_fields.items()
                    if v not in ("", None, 0)
                )
                confidence = round(filled / len(TITLE_FIELDS_SCHEMA), 2)

    except Exception as e:
        logger.warning("H3 title LLM extraction failed for %s: %s", wp_id, e)
        return H3TitleOcrResponse(
            attachment_id=attachment_id,
            ocr_text=ocr_text,
            extracted_fields=dict(_EMPTY_FIELDS),
            confidence=0,
        )

    return H3TitleOcrResponse(
        attachment_id=attachment_id,
        ocr_text=ocr_text,
        extracted_fields=extracted_fields,
        confidence=confidence,
    )
