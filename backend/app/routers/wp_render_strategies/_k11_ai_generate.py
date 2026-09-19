"""K11 资产减值损失 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/k11/ai-generate

sections: impairment-summary-conclusion / overall-opinion

损益类底稿AI辅助要点：
- 减值汇总结论（各类资产减值损失汇总+源底稿核对）
- 总体审计意见

Requirements: 6.1
"""

from __future__ import annotations

import logging
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.llm_client import chat_completion

logger = logging.getLogger(__name__)

router = APIRouter(tags=["k11-ai"])


class K11AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class K11AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "impairment-summary-conclusion",
    "overall-opinion",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 K11《资产减值损失》。
科目6701资产减值损失（**损益类/借方科目**）。

资产减值损失核心规则：
1. **损益类取发生额！**非期末余额。借方=减值增加（计提），贷方=减值转回/红冲
2. 净发生额=借方发生-贷方发生（正数=净减值）
3. 审定数=未审数+AJE+RJE
4. K11为各类资产减值损失的汇总底稿
5. 资产类别：存货跌价(F2)/固定资产减值(H1)/无形资产减值(I1)/商誉减值(I3)/在建工程/长期股权投资/其他
6. 商誉减值不可转回（CAS8规定）
7. 各类别减值须与源底稿核对一致（差异=0）

适用准则：CAS8资产减值、CAS1存货（跌价）、CAS4固定资产减值等。
输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "impairment-summary-conclusion": (
        "请生成K11资产减值损失减值汇总结论，汇总各类资产减值损失情况。"
        "需涵盖：\n"
        "1) 各类资产减值损失本期发生情况概述\n"
        "   - 存货跌价损失（F2）\n"
        "   - 固定资产减值损失（H1）\n"
        "   - 无形资产减值损失（I1）\n"
        "   - 商誉减值损失（I3，不可转回）\n"
        "   - 在建工程减值/长期股权投资减值/其他\n"
        "2) 各类别与源底稿核对结果（是否一致/差异说明）\n"
        "3) 本期减值总额与上期比较（同比变动分析）\n"
        "4) 重大减值事项识别及审计关注点\n"
        "5) 减值迹象判断的合理性评价\n"
        "6) 汇总结论（减值计提是否充分/是否存在需关注事项）"
    ),
    "overall-opinion": (
        "请生成K11资产减值损失底稿总体审计意见。"
        "需涵盖：\n"
        "1) 科目概况（6701资产减值损失本期发生额/审定数/重大程度）\n"
        "2) 各类资产减值汇总核对结论\n"
        "3) 商誉减值特殊考虑（不可转回/是否需要进一步减值测试）\n"
        "4) 与相关科目联动情况（各资产科目减值准备变动一致性）\n"
        "5) 减值迹象判断及管理层估计合理性\n"
        "6) 总体审计结论（是否存在重大错报/审计调整建议）\n"
        "7) 剩余审计风险评估"
    ),
}


@router.post("/api/workpapers/{wp_id}/k11/ai-generate")
async def k11_ai_generate(
    wp_id: str,
    body: K11AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> K11AiGenerateResponse:
    if not getattr(settings, "WP_AI_SERVICE_ENABLED", True):
        raise HTTPException(503, "AI 服务未启用")

    if body.section not in _SUPPORTED_SECTIONS:
        raise HTTPException(
            400,
            f"不支持的 section: {body.section}。支持: {sorted(_SUPPORTED_SECTIONS)}",
        )

    project_context = await _load_project_context(wp_id, db)
    user_prompt = _build_user_prompt(
        body.section, body.existingContent, body.relatedContext, project_context
    )
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    result = await chat_completion(messages=messages, temperature=0.3, max_tokens=2000)
    if isinstance(result, str) and result.startswith("["):
        return K11AiGenerateResponse(content="", sources=[])
    return K11AiGenerateResponse(content=result, sources=[])


def _build_user_prompt(
    section: str,
    existing_content: str,
    related_context: dict[str, Any],
    project_context: dict,
) -> str:
    parts: list[str] = [f"## 任务\n{_SECTION_PROMPTS.get(section, '请生成审计文本。')}\n"]
    ctx_lines = []
    if project_context.get("client_name"):
        ctx_lines.append(f"客户名称：{project_context['client_name']}")
    if project_context.get("audit_year"):
        ctx_lines.append(f"审计年度：{project_context['audit_year']}年")
    if project_context.get("business_category"):
        ctx_lines.append(f"行业：{project_context['business_category']}")
    if ctx_lines:
        parts.append("## 项目信息\n" + "\n".join(ctx_lines) + "\n")
    if related_context:
        ctx_str = "\n".join(f"- {k}: {v}" for k, v in related_context.items() if v)
        if ctx_str:
            parts.append(f"## 底稿数据\n{ctx_str}\n")
    if existing_content:
        parts.append(f"## 已有内容\n{existing_content[:2000]}\n请补充完善。")
    else:
        parts.append("请根据以上信息生成专业初稿。")
    return "\n".join(parts)


async def _load_project_context(wp_id: str, db: AsyncSession) -> dict:
    ctx: dict = {"client_name": "", "audit_year": "", "business_category": ""}
    try:
        result = await db.execute(
            sa.text("""
                SELECT p.client_name, p.audit_year, p.business_category
                FROM working_paper wp
                JOIN projects p ON wp.project_id = p.id
                WHERE wp.id = :wp_id
            """),
            {"wp_id": wp_id},
        )
        row = result.fetchone()
        if row:
            ctx["client_name"] = row.client_name or ""
            ctx["audit_year"] = str(row.audit_year) if row.audit_year else ""
            ctx["business_category"] = row.business_category or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("K11 AI: project context 加载失败: %s", e)
    return ctx
