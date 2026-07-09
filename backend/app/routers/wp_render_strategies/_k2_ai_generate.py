"""K2 其他流动资产 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/k2/ai-generate

sections: amort-conclusion / classification-eval / overall-opinion
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

router = APIRouter(tags=["k2-ai"])


class K2AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class K2AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "amort-conclusion",
    "classification-eval",
    "overall-opinion",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 K2《其他流动资产》。
科目1231其他流动资产（借方/资产类）。
核心关注：资产类三角勾稽（期末=期初+借方-贷方）、合同取得成本资本化（CAS14增量+可收回+直接相关）、
摊销测算引擎（直线法=成本/总期数×本期期数；进度法=成本×(本期进度-上期进度)）、
摊余成本=取得成本-累计摊销、分类正确性（流动vs非流动）、可回收性评估。

CAS14收入准则：合同取得成本资本化条件——增量成本+预期可收回+与合同直接相关。
不满足条件的直接费用化。摊销在相关商品/服务转让时确认。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "amort-conclusion": (
        "请生成K2-5摊销测算表的审计师结论，综合评价被审计单位对合同取得成本摊销的合理性。"
        "应包括：摊销方法选择（直线法/进度法）是否恰当、摊销期确定是否合理（与合同期/履约期匹配）、"
        "测算摊销与企业实际摊销的差异分析、差异是否超过重要性水平需调整、"
        "摊余成本与期末余额的一致性验证。如有差异需提出调整建议。"
    ),
    "classification-eval": (
        "请生成K2-6检查表中分类评价部分的审计师评价，逐项评价其他流动资产的：\n"
        "1. 分类正确性——是否满足流动资产定义（预期一年内变现/使用/消耗）；\n"
        "2. 合同取得成本资本化合理性——CAS14三条件是否满足；\n"
        "3. 可回收性评估——是否存在减值迹象、预计可收回金额是否超过账面；\n"
        "4. 列报恰当性——披露是否完整、是否需要重分类为非流动。\n"
        "请结合CAS14和CAS30相关准则要求进行评价。"
    ),
    "overall-opinion": (
        "请生成K2-1审定表底部的审计综合意见，综合评价其他流动资产科目整体的存在性、"
        "完整性、计价和分摊（摊销充分性）、权利和义务、列报与披露的恰当性。"
        "说明是否发现需要调整的重大事项，审定数与未审数的主要差异原因，"
        "合同取得成本摊销的总体合理性，对报表层面影响的结论。"
    ),
}


@router.post("/api/workpapers/{wp_id}/k2/ai-generate")
async def k2_ai_generate(
    wp_id: str,
    body: K2AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> K2AiGenerateResponse:
    if not getattr(settings, "WP_AI_SERVICE_ENABLED", True):
        raise HTTPException(503, "AI 服务未启用")
    if body.section not in _SUPPORTED_SECTIONS:
        raise HTTPException(400, f"不支持的 section: {body.section}。支持: {sorted(_SUPPORTED_SECTIONS)}")

    project_context = await _load_project_context(wp_id, db)
    user_prompt = _build_user_prompt(body.section, body.existingContent, body.relatedContext, project_context)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    result = await chat_completion(messages=messages, temperature=0.3, max_tokens=2000)
    if isinstance(result, str) and result.startswith("["):
        return K2AiGenerateResponse(content="", sources=[])
    return K2AiGenerateResponse(content=result, sources=[])


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
    except Exception as e:
        logger.warning("K2 AI: project context 加载失败: %s", e)
    return ctx
