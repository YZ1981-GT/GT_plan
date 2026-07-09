"""H1 固定资产 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/h1/ai-generate

sections: adj-note / adj-conclusion / policy-evaluation / analysis-change /
          depreciation-summary / impairment-conclusion / stocktake-summary / disposal-note
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

router = APIRouter(tags=["h1-ai"])


class H1AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class H1AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "adj-note",
    "adj-conclusion",
    "policy-evaluation",
    "analysis-change",
    "depreciation-summary",
    "impairment-conclusion",
    "stocktake-summary",
    "disposal-note",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 H1《固定资产》。
科目1601固定资产（借方/资产类）+ 1602累计折旧（贷方/资产备抵类）。
核心关注：资产类三角勾稽（期末=期初+增加-减少）、折旧四种方法计算验证、
减值DCF资产组测试、实物监盘三阶段流程、权属检查逐项核验。
CAS4固定资产准则：确认条件（经济利益+成本可靠）、折旧（直线/双倍余额/年数总和/工作量）、
减值（CAS8资产减值-可收回金额=MAX(公允-处置费,使用价值现值)）。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "adj-note": (
        "请生成H1-1固定资产审定表的审计说明，分析原值/累计折旧各分类的三角勾稽结果、"
        "期初到期末变动的主要原因、未审数与审定数的差异说明。"
    ),
    "adj-conclusion": (
        "请生成H1-1固定资产审定表的审计结论，评价固定资产科目整体的真实性、完整性和计价准确性，"
        "说明是否发现需要调整的重大事项。"
    ),
    "policy-evaluation": (
        "请生成H1-5会计政策估计检查的审计师评价，逐项评价被审计单位固定资产确认条件、"
        "分类与使用年限、折旧方法与残值率、后续支出资本化/费用化标准、减值政策的恰当性。"
    ),
    "analysis-change": (
        "请生成H1-6固定资产分析表的变动分析说明，解释各资产类别的增加率/减少率/净变动率、"
        "成新率偏低的资产类别原因、结构变动的合理性评价。"
    ),
    "depreciation-summary": (
        "请生成H1-12折旧测算表的审计汇总说明，说明测算折旧与账面折旧的总差异、"
        "差异较大的资产类别及原因、折旧方法和参数的合理性评价。"
    ),
    "impairment-conclusion": (
        "请生成H1-14减值测算表的审计结论，评价减值迹象判断的充分性、"
        "可收回金额计算方法及关键假设的合理性、减值计提是否充分。"
    ),
    "stocktake-summary": (
        "请生成H1-11监盘小结的总体结论，汇总盘点覆盖率、账实相符率、"
        "盘盈盘亏的性质和金额、差异处理建议。"
    ),
    "disposal-note": (
        "请生成H1-8固定资产处置检查的审计说明，分析处置/报废的审批合规性、"
        "处置定价公允性、处置损益计算准确性及与H10的联动一致性。"
    ),
}


@router.post("/api/workpapers/{wp_id}/h1/ai-generate")
async def h1_ai_generate(
    wp_id: str,
    body: H1AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> H1AiGenerateResponse:
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
        return H1AiGenerateResponse(content="", sources=[])
    return H1AiGenerateResponse(content=result, sources=[])


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
        logger.warning("H1 AI: project context 加载失败: %s", e)
    return ctx
