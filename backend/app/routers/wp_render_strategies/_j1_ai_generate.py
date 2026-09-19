"""J1 应付职工薪酬 — AI生成端点.

支持 section：
- accrual_analysis: 计提合理性分析
- allocation_analysis: 分配闭合分析
- monthly_fluctuation: 月度波动分析
- industry_compare: 行业对比分析结论
- severance_assessment: 辞退福利CAS9评估

Spec: .kiro/specs/j1-employee-compensation/
Requirements: 5.3
"""
from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.database import get_db
from app.deps import get_current_user
from app.services.llm_client import chat_completion

logger = logging.getLogger(__name__)
router = APIRouter(tags=["j1-ai"])

SUPPORTED_SECTIONS = {
    "accrual_analysis",
    "allocation_analysis",
    "monthly_fluctuation",
    "industry_compare",
    "severance_assessment",
}

SECTION_PROMPTS = {
    "accrual_analysis": (
        "你是审计专家，请根据以下薪酬计提情况数据，分析计提合理性：\n"
        "重点关注：差异率>5%的项目、多提/少提原因、是否需要调整。\n"
        "语言：简洁专业中文，150字以内。"
    ),
    "allocation_analysis": (
        "你是审计专家，请分析以下薪酬分配情况：\n"
        "重点关注：分配是否闭合(各费用科目合计=贷方增加)、分配比例是否合理。\n"
        "语言：简洁专业中文，100字以内。"
    ),
    "monthly_fluctuation": (
        "你是审计专家，请分析以下应付职工薪酬月度数据异常波动：\n"
        "重点关注：哪些月份偏离月均>30%、可能原因（年终奖/补发/裁员等）。\n"
        "语言：简洁专业中文，150字以内。"
    ),
    "industry_compare": (
        "你是审计专家，请根据以下行业对比数据，给出薪酬合理性分析结论：\n"
        "重点关注：人均薪酬/薪酬占比是否显著偏离行业均值、可能原因。\n"
        "语言：简洁专业中文，100字以内。"
    ),
    "severance_assessment": (
        "你是审计专家，请根据CAS9辞退福利确认条件和明细数据，评估辞退福利确认是否恰当：\n"
        "重点关注：四项条件是否全部满足、金额测算是否合理、精算是否需要。\n"
        "语言：简洁专业中文，150字以内。"
    ),
}


class J1AiRequest(BaseModel):
    section: str
    context: str = ""
    existing_content: str = ""


class J1AiResponse(BaseModel):
    content: str
    section: str


@router.post("/api/workpapers/{wp_id}/j1/ai-generate", response_model=J1AiResponse)
async def ai_generate(
    wp_id: str,
    req: J1AiRequest,
    _user=Depends(get_current_user),
    _db=Depends(get_db),
):
    """AI生成J1各section的分析文本."""
    if req.section not in SUPPORTED_SECTIONS:
        raise HTTPException(400, f"不支持的section: {req.section}")

    system_prompt = SECTION_PROMPTS[req.section]
    user_content = f"数据：\n{req.context}\n"
    if req.existing_content:
        user_content += f"\n现有内容（需改进）：\n{req.existing_content}"

    try:
        result = await chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            max_tokens=500,
        )
        if not isinstance(result, str):
            raise TypeError("unexpected streaming response")
        return J1AiResponse(content=result, section=req.section)
    except Exception as e:
        logger.error("J1 AI generate failed: %s", e)
        raise HTTPException(500, "AI生成失败，请稍后重试") from e
