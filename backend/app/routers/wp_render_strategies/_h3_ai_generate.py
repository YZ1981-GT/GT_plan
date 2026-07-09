"""H3 投资性房地产 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/h3/ai-generate

sections: adj-note-cost / adj-note-fair / adj-conclusion / policy-evaluation /
          transfer-analysis / fair-value-summary / rental-analysis / impairment-conclusion
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

router = APIRouter(tags=["h3-ai"])


class H3AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}
    measurement_model: str = "cost"


class H3AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "adj-note-cost",
    "adj-note-fair",
    "adj-conclusion",
    "policy-evaluation",
    "transfer-analysis",
    "fair-value-summary",
    "rental-analysis",
    "impairment-conclusion",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 H3《投资性房地产》。
科目1503投资性房地产（借方/资产类）+ 成本模式下1504累计折旧（贷方/资产备抵类）。
核心关注：双计量模式（成本模式/公允价值模式）、互转三方向处理、
租金收入测算、公允价值确定方法。
CAS3投资性房地产准则：
- 成本模式：按H1固定资产计提折旧和减值
- 公允价值模式：不计提折旧和减值，公允价值变动计入当期损益
- 互转：自用→投资(公允差额→OCI/PL)；投资→自用(公允→入账)；在建→投资(账面/公允→入账)
- 计量模式变更：仅允许成本→公允（视同会计政策变更追溯调整），不允许公允→成本

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "adj-note-cost": (
        "请生成H3-1投资性房地产审定表的审计说明（成本模式），分析原值/累计折旧各分类的三角勾稽结果、"
        "期初到期末变动的主要原因（增加/减少/转换）、未审数与审定数的差异说明。"
    ),
    "adj-note-fair": (
        "请生成H3-1投资性房地产审定表的审计说明（公允价值模式），分析公允价值各分类的变动结果、"
        "公允价值变动金额及原因、增减转换的影响、与评估报告的一致性。"
    ),
    "adj-conclusion": (
        "请生成H3-1投资性房地产审定表的审计结论，评价投资性房地产科目整体的真实性、完整性和计价准确性，"
        "说明是否发现需要调整的重大事项，包括计量模式选择的恰当性。"
    ),
    "policy-evaluation": (
        "请生成H3-4会计政策检查的审计师评价，逐项评价被审计单位投资性房地产的确认条件（CAS3第3条）、"
        "计量模式选择及变更、折旧政策（成本模式）、公允价值确定方法（公允模式）、"
        "转换处理的恰当性。"
    ),
    "transfer-analysis": (
        "请生成H3-6互转审核的审计分析，说明本期各方向转换（自用→投资/投资→自用/在建→投资）的"
        "金额、会计处理正确性、公允价值确定依据、OCI/损益确认的合规性、"
        "转出=转入金额一致性验证结果。"
    ),
    "fair-value-summary": (
        "请生成H3-8公允价值复核的审计汇总，评价评估师资质及独立性、"
        "评估方法（收益法/比较法/成本法）的恰当性、关键假设的合理性、"
        "独立测算与评估值的差异是否在可接受范围内。"
    ),
    "rental-analysis": (
        "请生成H3-14租金收入测算的审计分析，汇总本期租金收入总额、平均空置率、"
        "实际收入与测算差异、即将到期合同数量及影响、"
        "租金回报率分析、与其他业务收入-租金的交叉验证结果。"
    ),
    "impairment-conclusion": (
        "请生成H3-10减值测算表的审计结论（仅成本模式），评价减值迹象判断的充分性、"
        "可收回金额计算方法（DCF/公允-处置费）及关键假设的合理性、"
        "减值计提是否充分、空置资产是否需要特别关注。"
    ),
}


@router.post("/api/workpapers/{wp_id}/h3/ai-generate")
async def h3_ai_generate(
    wp_id: str,
    body: H3AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> H3AiGenerateResponse:
    if not getattr(settings, "WP_AI_SERVICE_ENABLED", True):
        raise HTTPException(503, "AI 服务未启用")
    if body.section not in _SUPPORTED_SECTIONS:
        raise HTTPException(400, f"不支持的 section: {body.section}。支持: {sorted(_SUPPORTED_SECTIONS)}")

    project_context = await _load_project_context(wp_id, db)
    user_prompt = _build_user_prompt(
        body.section, body.existingContent, body.relatedContext,
        project_context, body.measurement_model,
    )
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    result = await chat_completion(messages=messages, temperature=0.3, max_tokens=2000)
    if isinstance(result, str) and result.startswith("["):
        return H3AiGenerateResponse(content="", sources=[])
    return H3AiGenerateResponse(content=result, sources=[])


def _build_user_prompt(
    section: str,
    existing_content: str,
    related_context: dict[str, Any],
    project_context: dict,
    measurement_model: str,
) -> str:
    parts: list[str] = [f"## 任务\n{_SECTION_PROMPTS.get(section, '请生成审计文本。')}\n"]
    ctx_lines = []
    if project_context.get("client_name"):
        ctx_lines.append(f"客户名称：{project_context['client_name']}")
    if project_context.get("audit_year"):
        ctx_lines.append(f"审计年度：{project_context['audit_year']}年")
    if project_context.get("business_category"):
        ctx_lines.append(f"行业：{project_context['business_category']}")
    model_label = "成本模式" if measurement_model == "cost" else "公允价值模式"
    ctx_lines.append(f"计量模式：{model_label}")
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
        logger.warning("H3 AI: project context 加载失败: %s", e)
    return ctx
