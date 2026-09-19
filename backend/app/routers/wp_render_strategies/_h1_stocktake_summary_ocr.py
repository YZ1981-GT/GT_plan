"""H1-11 固定资产监盘小结 — 附件 OCR 识别端点

POST /api/workpapers/{wp_id}/h1/stocktake-summary-ocr?section=location|narrative|precheck|building|recount|client-plan|plan-narrative
Content-Type: multipart/form-data
Body: file (PDF/image)

供监盘小结/计划分区上传：确认弹窗后回写对应字段，并返回 attachment_id 供二次编辑关联。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.llm_client import chat_completion
from app.services.unified_ocr_service import UnifiedOCRService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["h1-ai"])

_SECTION_SCHEMAS: dict[str, dict[str, str]] = {
    "location": {
        "assetCategory": "资产类别(房屋建筑物/机器设备/运输设备/办公设备等)",
        "assetName": "资产名称",
        "storageLocation": "存放地点/坐落地址",
        "certIndex": "权证号或检查记录索引(如有)",
    },
    "precheck": {
        "documentType": "资料类型(明细账卡片/管理制度/维修制度/存放示意图/其他)",
        "indexSuggestion": "建议底稿索引号",
        "content": "资料摘要(50字以内)",
    },
    "building": {
        "titleCertNo": "不动产权证号/房屋所有权证号",
        "owner": "权利人",
        "address": "房屋坐落",
        "buildingArea": "建筑面积(数字,平方米)",
        "qtyMatchHint": "与账面核对提示(数量/面积是否一致的简述)",
        "content": "检查记录摘要",
    },
    "recount": {
        "recountPersonnel": "复盘人员姓名",
        "recountTotalUnits": "设备总台套数(数字)",
        "recountSampleUnits": "复盘台套数(数字)",
        "recountTotalAmount": "固定资产账面总值(数字,元)",
        "recountSampleAmount": "复盘资产账面值(数字,元)",
        "recountCorrectUnits": "复盘正确台套数(数字)",
        "recountCorrectAmount": "复盘正确金额(数字,元)",
        "content": "复盘说明摘要",
    },
    "narrative": {
        "content": "可写入监盘小结文本框的完整叙述(保留原文关键信息)",
    },
    "client-plan": {
        "icSystemName": "固定资产盘点/管理制度名称",
        "icFrequency": "盘点时间或频次",
        "icResponsible": "负责部门或人员",
        "clientPlanArrange": "企业盘点计划安排摘要",
        "clientMeetingNote": "盘点会议时间与参会人员",
        "clientHeadcountEstimate": "预计盘点人数",
        "specialRequirements": "对审计监盘的特殊配合要求",
        "content": "企业盘点计划全文摘要",
    },
    "plan-narrative": {
        "content": "可写入监盘计划文本框的完整叙述(保留原文关键信息)",
    },
}

_NUM_KEYS = {
    "buildingArea",
    "recountTotalUnits",
    "recountSampleUnits",
    "recountTotalAmount",
    "recountSampleAmount",
    "recountCorrectUnits",
    "recountCorrectAmount",
}


class H1StocktakeSummaryOcrResponse(BaseModel):
    attachment_id: str
    ocr_text: str
    extracted_fields: dict
    confidence: float
    section: str


def _empty_fields(section: str) -> dict:
    schema = _SECTION_SCHEMAS[section]
    out: dict = {}
    for k in schema:
        out[k] = 0 if k in _NUM_KEYS else ""
    return out


@router.post("/api/workpapers/{wp_id}/h1/stocktake-summary-ocr")
async def h1_stocktake_summary_ocr(
    wp_id: str,
    file: UploadFile = File(...),
    section: str = Query(
        "narrative",
        description="location|narrative|precheck|building|recount|client-plan|plan-narrative",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> H1StocktakeSummaryOcrResponse:
    _ = db, current_user
    if section not in _SECTION_SCHEMAS:
        raise HTTPException(400, f"不支持的 section: {section}")

    allowed = (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff")
    filename = file.filename or "upload.pdf"
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, f"不支持的文件类型: {suffix}")

    attachment_id = str(uuid4())
    storage_dir = Path("storage/workpapers") / wp_id / "h1-stocktake-summary"
    storage_dir.mkdir(parents=True, exist_ok=True)
    file_path = storage_dir / f"{attachment_id}{suffix}"

    content = await file.read()
    async with aiofiles.open(str(file_path), "wb") as f:
        await f.write(content)

    ocr_text = ""
    try:
        ocr_service = UnifiedOCRService()
        ocr_result = await ocr_service.recognize(str(file_path))
        ocr_text = ocr_result.get("text", "") or ""
    except Exception as e:
        logger.warning("H1-11 OCR failed for %s/%s: %s", wp_id, section, e)
        return H1StocktakeSummaryOcrResponse(
            attachment_id=attachment_id,
            ocr_text="",
            extracted_fields=_empty_fields(section),
            confidence=0,
            section=section,
        )

    if not ocr_text.strip():
        return H1StocktakeSummaryOcrResponse(
            attachment_id=attachment_id,
            ocr_text="",
            extracted_fields=_empty_fields(section),
            confidence=0,
            section=section,
        )

    schema = _SECTION_SCHEMAS[section]
    system = (
        "你是审计固定资产监盘小结信息提取专家。从 OCR 文本提取可写入 H1-11 监盘小结的字段。\n"
        "严格返回 JSON（不确定填空字符串，数值填0）：\n"
        f"{json.dumps(schema, ensure_ascii=False, indent=2)}"
    )
    extracted = _empty_fields(section)
    confidence = 0.0
    try:
        llm_result = await chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"OCR文本：\n{ocr_text[:6000]}"},
            ],
            temperature=0.1,
            max_tokens=1200,
        )
        if isinstance(llm_result, str):
            json_str = llm_result.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()
            parsed = json.loads(json_str)
            if isinstance(parsed, dict):
                for key in schema:
                    if key in parsed and parsed[key] is not None:
                        if key in _NUM_KEYS:
                            try:
                                extracted[key] = float(parsed[key])
                            except (TypeError, ValueError):
                                extracted[key] = 0
                        else:
                            extracted[key] = str(parsed[key])
                filled = sum(1 for k, v in extracted.items() if v not in ("", 0, None))
                confidence = round(filled / max(len(schema), 1), 2)
    except Exception as e:
        logger.warning("H1-11 LLM extraction failed: %s", e)
        # narrative 兜底：至少回写全文便于人工确认
        if section == "narrative":
            extracted["content"] = ocr_text[:4000]
            confidence = 0.3

    # 始终附带全文，便于二次编辑
    extracted["full_text"] = ocr_text[:8000]

    return H1StocktakeSummaryOcrResponse(
        attachment_id=attachment_id,
        ocr_text=ocr_text,
        extracted_fields=extracted,
        confidence=confidence,
        section=section,
    )
