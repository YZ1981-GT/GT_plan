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
    """会计政策自动生成（stub，后续接入 vLLM）"""
    return {
        "section_number": data.section_number,
        "generated_text": f"根据{data.template_type}模版，{data.section_number}章节的标准会计政策文本。（LLM 生成占位）",
        "source": "llm",
    }


@router.post("/{project_id}/ai/generate-analysis")
async def generate_analysis(
    project_id: UUID,
    data: AnalysisGenerateRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """变动分析自动生成（stub）"""
    return {
        "section_number": data.section_number,
        "generated_text": "本期余额较上期变动，主要系...（LLM 生成占位）",
        "source": "llm",
    }


@router.post("/{project_id}/ai/check-completeness")
async def check_completeness(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """披露完整性检查（stub）"""
    return {
        "missing_sections": [],
        "suggestions": ["所有必要披露事项已覆盖（LLM 检查占位）"],
    }


@router.post("/{project_id}/ai/check-expression")
async def check_expression(
    project_id: UUID,
    section_number: str = Query(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """表述规范性检查（stub）"""
    return {
        "section_number": section_number,
        "issues": [],
        "message": "表述规范，无需修改（LLM 检查占位）",
    }


@router.post("/{project_id}/ai/complete")
async def ai_complete(
    project_id: UUID,
    section_number: str = Query(...),
    current_text: str = Query(""),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """智能续写（stub）"""
    return {
        "suggestions": [
            current_text + "...（续写建议1）",
            current_text + "...（续写建议2）",
            current_text + "...（续写建议3）",
        ],
    }
