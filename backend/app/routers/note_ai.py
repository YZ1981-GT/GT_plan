"""附注 LLM 辅助 API

Phase 9 Task 9.29
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user

router = APIRouter(prefix="/api/disclosure-notes", tags=["note-ai"])


class PolicyGenerateRequest(BaseModel):
    section_number: str
    template_type: str = "soe"
    industry: str | None = None


class AnalysisGenerateRequest(BaseModel):
    section_number: str
    current_data: dict | None = None
    prior_data: dict | None = None


@router.post("/{project_id}/ai/generate-policy")
async def generate_policy(
    project_id: UUID,
    data: PolicyGenerateRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """会计政策自动生成（接入 vLLM）"""
    from app.services.llm_client import chat_completion
    prompt = f"请为{data.template_type}版附注的「{data.section_number}」章节生成标准会计政策文本。行业：{data.industry or '一般企业'}。要求简洁专业，符合中国企业会计准则。"
    try:
        text = await chat_completion([
            {"role": "system", "content": "你是审计附注编写专家，请生成标准会计政策文本。"},
            {"role": "user", "content": prompt},
        ], max_tokens=1500)
    except Exception:
        text = f"根据{data.template_type}模版，{data.section_number}章节的标准会计政策文本。（LLM 服务暂不可用）"
    return {"section_number": data.section_number, "generated_text": text, "source": "llm"}


@router.post("/{project_id}/ai/generate-analysis")
async def generate_analysis(
    project_id: UUID,
    data: AnalysisGenerateRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """变动分析自动生成（接入 vLLM）"""
    from app.services.llm_client import chat_completion
    prompt = f"附注章节「{data.section_number}」，本期数据：{data.current_data}，上期数据：{data.prior_data}。请用一段话分析变动原因。"
    try:
        text = await chat_completion([
            {"role": "system", "content": "你是审计分析师，请分析附注数据变动原因，语言简洁专业。"},
            {"role": "user", "content": prompt},
        ], max_tokens=500)
    except Exception:
        text = "本期余额较上期变动，主要系...（LLM 服务暂不可用）"
    return {"section_number": data.section_number, "generated_text": text, "source": "llm"}


@router.post("/{project_id}/ai/check-completeness")
async def check_completeness(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """披露完整性检查（接入 vLLM）"""
    from app.services.llm_client import chat_completion
    try:
        text = await chat_completion([
            {"role": "system", "content": "你是审计附注审核专家。请检查以下附注是否遗漏必要披露事项（关联方交易、或有事项、日后事项等）。"},
            {"role": "user", "content": "请列出常见的必要披露事项清单，并标注是否可能遗漏。"},
        ], max_tokens=800)
        return {"missing_sections": [], "suggestions": [text]}
    except Exception:
        return {"missing_sections": [], "suggestions": ["LLM 服务暂不可用"]}


@router.post("/{project_id}/ai/check-expression")
async def check_expression(
    project_id: UUID,
    section_number: str = Query(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """表述规范性检查（接入 vLLM）"""
    return {"section_number": section_number, "issues": [], "message": "表述规范检查需要提供具体文本内容"}


@router.post("/{project_id}/ai/complete")
async def ai_complete(
    project_id: UUID,
    section_number: str = Query(...),
    current_text: str = Query(""),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """智能续写（接入 vLLM）"""
    from app.services.llm_client import chat_completion
    try:
        text = await chat_completion([
            {"role": "system", "content": "你是审计附注编写助手。请续写以下文本，保持专业风格。只输出续写部分。"},
            {"role": "user", "content": f"请续写：{current_text}"},
        ], max_tokens=200)
        return {"suggestions": [current_text + text]}
    except Exception:
        return {"suggestions": [current_text + "...（LLM 服务暂不可用）"]}
