"""H1 固定资产 — 房屋权证 OCR 识别端点

POST /api/workpapers/{wp_id}/h1/property-title-ocr
Content-Type: multipart/form-data
Body: file (PDF/image)

上传不动产权证/房屋所有权证扫描件，OCR 后提取权属核对关键字段，供 H1-16 预填。
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

router = APIRouter(tags=["h1-ai"])

PROPERTY_TITLE_FIELDS_SCHEMA = {
    "titleCertNo": "不动产权证号/房屋所有权证号",
    "owner": "权利人/房屋所有权人",
    "coOwnership": "共有情况(单独所有/共同共有/按份共有等)",
    "address": "房屋坐落/不动产坐落",
    "issueDate": "登记时间/发证日期(YYYY-MM-DD)",
    "propertyNature": "权利类型/房屋性质(如国有建设用地使用权/房屋所有权)",
    "usage": "规划用途/房屋用途",
    "buildingArea": "建筑面积(数字,平方米)",
    "landArea": "土地面积/宗地面积(数字,平方米)",
    "usefulLife": "使用期限/土地使用期限",
    "issuingAuthority": "颁发单位/登记机构",
    "otherRights": "他项权利/备注栏抵押查封等",
    "mortgagee": "抵押权人(若有)",
    "mortgageNature": "抵押性质(若有,如最高额抵押)",
}

_EMPTY_FIELDS: dict = {k: "" for k in PROPERTY_TITLE_FIELDS_SCHEMA}
_EMPTY_FIELDS["buildingArea"] = 0
_EMPTY_FIELDS["landArea"] = 0

_LLM_SYSTEM_PROMPT = (
    "你是审计不动产权属证明信息提取专家。"
    "请从以下OCR文本中提取中国不动产权证书或房屋所有权证书的关键信息。\n"
    "严格按JSON格式返回以下字段（不确定的填空字符串，面积填0）：\n"
    f"{json.dumps(PROPERTY_TITLE_FIELDS_SCHEMA, ensure_ascii=False, indent=2)}"
)


class H1PropertyTitleOcrResponse(BaseModel):
    attachment_id: str
    ocr_text: str
    extracted_fields: dict
    confidence: float


def _build_extraction_prompt(ocr_text: str) -> str:
    return f"OCR文本：\n{ocr_text[:6000]}"


@router.post("/api/workpapers/{wp_id}/h1/property-title-ocr")
async def h1_property_title_ocr(
    wp_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> H1PropertyTitleOcrResponse:
    """上传权证附件，OCR识别并提取权属字段供 H1-16 预填"""
    _ = db, current_user

    allowed_types = (".pdf", ".png", ".jpg", ".jpeg")
    filename = file.filename or "upload.pdf"
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed_types:
        raise HTTPException(400, f"不支持的文件类型: {suffix}，仅支持 {allowed_types}")

    attachment_id = str(uuid4())
    storage_dir = Path("storage/workpapers") / wp_id / "property-titles"
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
        logger.warning("H1 property title OCR failed for %s: %s", wp_id, e)
        return H1PropertyTitleOcrResponse(
            attachment_id=attachment_id,
            ocr_text="",
            extracted_fields=dict(_EMPTY_FIELDS),
            confidence=0,
        )

    if not ocr_text.strip():
        return H1PropertyTitleOcrResponse(
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
                for key in PROPERTY_TITLE_FIELDS_SCHEMA:
                    if key in parsed and parsed[key] is not None:
                        extracted_fields[key] = parsed[key]

                filled = sum(
                    1 for k, v in extracted_fields.items()
                    if v not in ("", None, 0)
                )
                confidence = round(filled / len(PROPERTY_TITLE_FIELDS_SCHEMA), 2)

    except Exception as e:
        logger.warning("H1 property title LLM extraction failed for %s: %s", wp_id, e)
        return H1PropertyTitleOcrResponse(
            attachment_id=attachment_id,
            ocr_text=ocr_text,
            extracted_fields=dict(_EMPTY_FIELDS),
            confidence=0,
        )

    return H1PropertyTitleOcrResponse(
        attachment_id=attachment_id,
        ocr_text=ocr_text,
        extracted_fields=extracted_fields,
        confidence=confidence,
    )


# ─── H1-17 运输设备权证 OCR（行驶证/登记证书）─────────────────────────────────

VEHICLE_TITLE_FIELDS_SCHEMA = {
    "plateNo": "号牌号码/机动车登记编号",
    "vinNo": "车辆识别代号/车架号VIN",
    "engineNo": "发动机号码",
    "drivingLicenseNo": "行驶证号",
    "regCertNo": "登记证书编号",
    "regDate": "注册登记日期(YYYY-MM-DD)",
    "owner": "所有人/车主",
    "useNature": "使用性质(如非营运/货运)",
    "inspectionExpiry": "检验有效期止/年检截止日(YYYY-MM-DD)",
    "regRemarks": "登记栏备注(抵押/质押/查封等)",
}

_VEHICLE_EMPTY_FIELDS: dict = {k: "" for k in VEHICLE_TITLE_FIELDS_SCHEMA}

_VEHICLE_LLM_SYSTEM_PROMPT = (
    "你是审计机动车权属证明信息提取专家。"
    "请从以下OCR文本中提取中国机动车行驶证或机动车登记证书的关键信息。\n"
    "严格按JSON格式返回以下字段（不确定的填空字符串）：\n"
    f"{json.dumps(VEHICLE_TITLE_FIELDS_SCHEMA, ensure_ascii=False, indent=2)}"
)


class H1VehicleTitleOcrResponse(BaseModel):
    attachment_id: str
    ocr_text: str
    extracted_fields: dict
    confidence: float


@router.post("/api/workpapers/{wp_id}/h1/vehicle-title-ocr")
async def h1_vehicle_title_ocr(
    wp_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> H1VehicleTitleOcrResponse:
    """上传行驶证/登记证书附件，OCR识别并提取车辆权属字段供 H1-17 预填"""
    _ = db, current_user

    allowed_types = (".pdf", ".png", ".jpg", ".jpeg")
    filename = file.filename or "upload.pdf"
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed_types:
        raise HTTPException(400, f"不支持的文件类型: {suffix}，仅支持 {allowed_types}")

    attachment_id = str(uuid4())
    storage_dir = Path("storage/workpapers") / wp_id / "vehicle-titles"
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
        logger.warning("H1 vehicle title OCR failed for %s: %s", wp_id, e)
        return H1VehicleTitleOcrResponse(
            attachment_id=attachment_id,
            ocr_text="",
            extracted_fields=dict(_VEHICLE_EMPTY_FIELDS),
            confidence=0,
        )

    if not ocr_text.strip():
        return H1VehicleTitleOcrResponse(
            attachment_id=attachment_id,
            ocr_text="",
            extracted_fields=dict(_VEHICLE_EMPTY_FIELDS),
            confidence=0,
        )

    extracted_fields = dict(_VEHICLE_EMPTY_FIELDS)
    confidence = 0.0

    try:
        messages = [
            {"role": "system", "content": _VEHICLE_LLM_SYSTEM_PROMPT},
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
                for key in VEHICLE_TITLE_FIELDS_SCHEMA:
                    if key in parsed and parsed[key] is not None:
                        extracted_fields[key] = parsed[key]

                filled = sum(
                    1 for _k, v in extracted_fields.items()
                    if v not in ("", None, 0)
                )
                confidence = round(filled / len(VEHICLE_TITLE_FIELDS_SCHEMA), 2)

    except Exception as e:
        logger.warning("H1 vehicle title LLM extraction failed for %s: %s", wp_id, e)
        return H1VehicleTitleOcrResponse(
            attachment_id=attachment_id,
            ocr_text=ocr_text,
            extracted_fields=dict(_VEHICLE_EMPTY_FIELDS),
            confidence=0,
        )

    return H1VehicleTitleOcrResponse(
        attachment_id=attachment_id,
        ocr_text=ocr_text,
        extracted_fields=extracted_fields,
        confidence=confidence,
    )
