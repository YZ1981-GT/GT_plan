"""J2 设定受益计划 — AI生成端点.

AI辅助精算假设合理性分析、ISA620评估建议。

Spec: .kiro/specs/j2-defined-benefit-plan/
Requirements: 5.3
"""
from __future__ import annotations
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workpapers/{wp_id}/j2/ai", tags=["j2-ai"])


class J2AiRequest(BaseModel):
    section: str  # assumption-analysis / isa620-evaluation / sensitivity-summary / accrual-conclusion
    context: dict | None = None
    existing_content: str | None = None


class J2AiResponse(BaseModel):
    content: str
    section: str


AI_PROMPTS = {
    "assumption-analysis": (
        "作为审计专家，请分析以下设定受益计划的精算假设合理性：\n"
        "1. 折现率是否与当前国债收益率水平一致\n"
        "2. 薪酬增长率是否反映被审计单位实际薪酬政策\n"
        "3. 死亡率和离职率是否与行业经验数据一致\n"
        "请结合具体数值给出评价结论。"
    ),
    "isa620-evaluation": (
        "作为审计专家，请根据ISA620（利用专家工作）要求，评价精算师工作利用的适当性：\n"
        "1. 精算师资质是否满足要求\n"
        "2. 独立性是否得到保证\n"
        "3. 精算工作范围是否覆盖全部设定受益义务\n"
        "4. 精算方法论是否符合CAS9/IAS19要求\n"
        "请给出总体结论。"
    ),
    "sensitivity-summary": (
        "请总结设定受益计划的敏感性分析结论：\n"
        "关注折现率变动对DBO的影响幅度，评估精算假设变动的重要性水平。"
    ),
    "accrual-conclusion": (
        "请根据审计程序执行结果，草拟设定受益计划计提充分性的审计结论。\n"
        "需涵盖：精算假设合理性、DBO计量准确性、ISA620合规性、披露完整性。"
    ),
}


@router.post("/generate")
async def ai_generate(
    wp_id: str,
    request: J2AiRequest,
    db: AsyncSession = Depends(get_db),
) -> J2AiResponse:
    """AI辅助生成精算分析内容."""
    prompt = AI_PROMPTS.get(request.section, "请提供审计分析意见。")

    # 构建完整 prompt
    full_prompt = prompt
    if request.context:
        import json
        full_prompt += f"\n\n当前数据：{json.dumps(request.context, ensure_ascii=False, indent=2)}"
    if request.existing_content:
        full_prompt += f"\n\n已有内容（可参考优化）：{request.existing_content}"

    # 调用通用AI接口
    try:
        from app.services.ai_service import chat_completion
        content = await chat_completion(
            system_prompt="你是资深审计师，精通CAS9设定受益计划准则和ISA620利用专家工作准则。请用专业但简洁的语言回答。",
            user_prompt=full_prompt,
            max_tokens=800,
        )
    except Exception as e:
        logger.warning("J2 AI generate failed, returning placeholder: %s", e)
        content = f"[AI生成暂时不可用] 请手动填写{request.section}相关内容。"

    return J2AiResponse(content=content, section=request.section)
