"""D2 应收账款 — 保理终止确认判断向导（附件 OCR + AI 辅助判断）

- POST /api/workpapers/{wp_id}/d2/derecognition-ocr    附件上传 → OCR 文本 + 摘要
- POST /api/workpapers/{wp_id}/d2/derecognition-judge   单步 AI 辅助判断（结合证据+知识库引用）

终止确认 9 步判断流程来源：致同「应收账款预期信用损失计提及保理合同分析参考示例.xlsx」。
AI 仅给出建议，最终判断由审计师确认后回填底稿（人工判断优先）。
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

router = APIRouter(tags=["d2-derecognition"])

# 允许的建议枚举（前端点选/回填用）
_SUGGESTIONS = ("符合", "不符合", "不适用")


# ═══════════════════════════════════════════════════════════════════════════════
# OCR 端点
# ═══════════════════════════════════════════════════════════════════════════════

class DerecognitionOcrResponse(BaseModel):
    attachment_id: str
    ocr_text: str
    summary: str
    confidence: float


@router.post("/api/workpapers/{wp_id}/d2/derecognition-ocr", response_model=DerecognitionOcrResponse)
async def d2_derecognition_ocr(
    wp_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DerecognitionOcrResponse:
    """上传保理合同/协议附件 → OCR 识别文本（供 AI 判断与人工核对）。"""
    allowed = (".pdf", ".png", ".jpg", ".jpeg")
    filename = file.filename or "upload.pdf"
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, f"不支持的文件类型: {suffix}（支持 PDF/PNG/JPG）")

    attachment_id = str(uuid4())
    storage_dir = Path("storage/workpapers") / wp_id / "derecognition"
    storage_dir.mkdir(parents=True, exist_ok=True)
    file_path = storage_dir / f"{attachment_id}{suffix}"

    content = await file.read()
    async with aiofiles.open(str(file_path), "wb") as f:
        await f.write(content)

    ocr_text = ""
    try:
        ocr_result = await UnifiedOCRService().recognize(str(file_path))
        ocr_text = ocr_result.get("text", "") if isinstance(ocr_result, dict) else str(ocr_result or "")
    except Exception as e:  # noqa: BLE001
        logger.warning("D2 derecognition OCR failed: %s", e)
        return DerecognitionOcrResponse(attachment_id=attachment_id, ocr_text="", summary="", confidence=0)

    summary = ocr_text[:300].replace("\n", " ").strip()
    confidence = round(min(len(ocr_text) / 500.0, 1.0), 2) if ocr_text.strip() else 0
    return DerecognitionOcrResponse(
        attachment_id=attachment_id,
        ocr_text=ocr_text,
        summary=summary,
        confidence=confidence,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# AI 辅助判断端点
# ═══════════════════════════════════════════════════════════════════════════════

class KnowledgeRef(BaseModel):
    id: str | None = None
    name: str = ""
    excerpt: str = ""


class DerecognitionJudgeRequest(BaseModel):
    step_id: str
    step_title: str
    step_note: str = ""
    evidence_text: str = ""
    knowledge_refs: list[KnowledgeRef] = []
    context: dict = {}


class DerecognitionJudgeResponse(BaseModel):
    suggestion: str          # 符合 / 不符合 / 不适用
    reasoning: str           # 判断理由
    ai_available: bool = True


_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），精通 CAS 23《金融资产转移》、CAS 33《合并财务报表》及企业会计准则解释第8号。
你正在协助审计师完成应收账款保理业务的"终止确认判断"。审计师会给你当前判断步骤、判断要点、以及已上传的合同/协议证据文本和引用的知识库资料。

你的任务：针对该步骤，给出专业判断建议。
输出严格 JSON：{"suggestion": "符合|不符合|不适用", "reasoning": "判断理由，引用证据中的关键条款，150字以内"}
- suggestion 含义：该步骤条件是否"符合"终止确认要求（或该步骤是否已满足继续下一步的条件）；无法判断或证据不足时用"不适用"并在理由中说明需补充的证据。
- 立场：保持职业怀疑，重点识别转让方是否保留了信用风险/延迟支付风险（如宽泛的商业纠纷定义、超额担保、追加收购款、兜底回购条款等）。
- 仅输出 JSON，不要输出多余文字。"""


@router.post("/api/workpapers/{wp_id}/d2/derecognition-judge", response_model=DerecognitionJudgeResponse)
async def d2_derecognition_judge(
    wp_id: str,
    body: DerecognitionJudgeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DerecognitionJudgeResponse:
    """针对终止确认某一步骤，结合证据文本与知识库引用给出 AI 判断建议（仅建议，人工确认为准）。"""
    parts: list[str] = [
        f"## 当前判断步骤\n{body.step_title}",
        f"## 判断要点\n{body.step_note}" if body.step_note else "",
    ]
    if body.evidence_text.strip():
        parts.append(f"## 合同/协议证据（OCR）\n{body.evidence_text[:4000]}")
    if body.knowledge_refs:
        refs = "\n".join(
            f"- {r.name}：{r.excerpt[:200]}" for r in body.knowledge_refs if (r.name or r.excerpt)
        )
        if refs:
            parts.append(f"## 引用知识库资料\n{refs}")
    if body.context:
        try:
            parts.append(f"## 底稿上下文\n{json.dumps(body.context, ensure_ascii=False)[:800]}")
        except Exception:  # noqa: BLE001
            pass

    user_prompt = "\n\n".join(p for p in parts if p)

    try:
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        llm_result = await chat_completion(messages=messages, temperature=0.2, max_tokens=600)
    except Exception as e:  # noqa: BLE001
        logger.warning("D2 derecognition judge LLM failed: %s", e)
        return DerecognitionJudgeResponse(suggestion="不适用", reasoning="AI 服务暂不可用，请人工判断。", ai_available=False)

    suggestion = "不适用"
    reasoning = ""
    try:
        json_str = (llm_result or "").strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()
        parsed = json.loads(json_str)
        if isinstance(parsed, dict):
            s = str(parsed.get("suggestion", "")).strip()
            suggestion = s if s in _SUGGESTIONS else "不适用"
            reasoning = str(parsed.get("reasoning", "")).strip()
    except Exception:  # noqa: BLE001
        # 解析失败时把原文作为理由返回
        reasoning = (llm_result or "")[:400]

    if not reasoning:
        reasoning = "AI 未给出明确理由，请人工复核证据。"

    return DerecognitionJudgeResponse(suggestion=suggestion, reasoning=reasoning, ai_available=True)
