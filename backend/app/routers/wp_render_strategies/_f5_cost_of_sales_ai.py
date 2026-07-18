"""F5 营业成本 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/f5/ai-generate

sections: adjudication-note / adjudication-conclusion /
          monthly-detail-note / monthly-detail-conclusion /
          other-cost-note / other-cost-conclusion /
          comparison-note / comparison-conclusion /
          quantity-reconciliation / quantity-reconciliation-note /
          quantity-reconciliation-conclusion /
          cost-analysis / rollforward-evaluation / adjustment-evaluation
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

router = APIRouter(tags=["f5-ai"])


class F5AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class F5AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "adjudication-note",
    "adjudication-conclusion",
    "monthly-detail-note",
    "monthly-detail-conclusion",
    "other-cost-note",
    "other-cost-conclusion",
    "cost-analysis",
    "comparison-note",
    "comparison-conclusion",
    "quantity-reconciliation",
    "quantity-reconciliation-note",
    "quantity-reconciliation-conclusion",
    "rollforward-note",
    "rollforward-evaluation",
    "adjustment-note",
    "adjustment-evaluation",
    "adjustment-entry-note",
    "adjustment-entry-conclusion",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 F5《营业成本》。
科目6401营业成本，借方/损益类（发生额，无期初期末概念，本期与上期对比）。
核心关注：成本倒轧逻辑（期初材料+购入-期末-其他=投入+人工+制造=完工=营业成本）、
销售数量与结转成本数量核对、毛利率变动分析、月度成本波动、重大成本调整合规性。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "adjudication-note": (
        "请生成F5-1营业成本审定表的审计说明，按源表结构组织："
        "（1）主营业务成本本期较上期增加（负数为减少）的金额与比例；"
        "（2）主要原因（比例超过30%的品种或小计），结合传入的显著变动清单说明可能业务驱动；"
        "（3）其他业务成本重大变动及与试算平衡表6401核对差异（如有）。"
        "只能依据传入数据，不得虚构产量、售价或结转证据。控制在可直接填入底稿的段落。"
    ),
    "adjudication-conclusion": (
        "请生成F5-1营业成本审定表的正式审计结论。结合本期/上期审定、账项与重分类调整、"
        "品种结构、与试算平衡表差异及超过30%的重大变动，评价营业成本发生额的完整性、准确性"
        "及结转口径。采用A/B/C口径：A为未见重大异常；B为除已识别调整或说明事项外未见重大异常；"
        "C为存在重大未调整差异或审计范围受限。只输出可直接填入底稿的结论正文。"
    ),
    "monthly-detail-note": (
        "请生成F5-2主营业务成本月度明细表的审计说明。说明各品种1~12月成本结转情况、"
        "本期未审/审定与上期对比、未审及审定变动比例超过30%的品种及可能原因、"
        "月度结构比例是否与生产经营节奏匹配。只能依据传入数据，不得虚构产量或结转证据。"
    ),
    "monthly-detail-conclusion": (
        "请生成F5-2主营业务成本月度明细表的正式审计结论。结合月度结转完整性、调整后审定数、"
        "与上期变动及异常波动，评价主营业务成本月度明细是否公允反映结转情况。"
        "采用A/B/C口径。只输出可直接填入底稿的结论正文。"
    ),
    "other-cost-note": (
        "请生成F5-3其他业务成本明细表的审计说明。说明各项目本期/上期审定及结构比、"
        "审定变动额/变动率超过30%的项目及可能原因、与出租资产折旧/材料销售成本等底稿的勾稽核对情况。"
        "只能依据传入数据，不得虚构合同或折旧证据。"
    ),
    "other-cost-conclusion": (
        "请生成F5-3其他业务成本明细表的正式审计结论。结合项目构成、调整后审定数、"
        "与上期变动及异常波动，评价其他业务成本是否公允反映。采用A/B/C口径。"
        "只输出可直接填入底稿的结论正文。"
    ),
    "cost-analysis": "请生成F5-3其他业务成本的审计说明，分析成本构成、变动率异常项及与对应收入的配比合理性。",
    "comparison-note": (
        "请生成F5-5主营业务成本与上年度比较分析表的审计说明。说明各产品数量、平均单位成本、"
        "总成本的同比变动，对总成本变动率超过30%的产品分析数量驱动与单价驱动，"
        "并提示与F5-2月度明细、F5-6量本核对的交叉索引。只能依据传入数据，不得虚构产量或单价。"
    ),
    "comparison-conclusion": (
        "请生成F5-5主营业务成本与上年度比较分析表的正式审计结论。结合数量、单位成本与总成本"
        "同比变动及重大异常，评价主营业务成本结转同比分析是否支持发生额的合理性。"
        "采用A/B/C口径。只输出可直接填入底稿的结论正文。"
    ),
    "quantity-reconciliation": (
        "请生成F5-6销售数量与结转成本数量核对的审计说明，分析分厂/产品月度及全年差异（销售−结转）。"
    ),
    "quantity-reconciliation-note": (
        "请生成F5-6销售数量与结转成本数量核对明细表的审计说明。说明各分厂、产品的销售数量与结转成本数量"
        "月度及全年勾稽情况，对差异≠0的项目分析可能原因（截止、退货、未结转等），"
        "并提示与F5-2月度成本、F5-5比较分析的交叉索引。只能依据传入数据，不得虚构产量。"
    ),
    "quantity-reconciliation-conclusion": (
        "请生成F5-6销售数量与结转成本数量核对明细表的正式审计结论。结合销售与结转数量匹配度、"
        "重大差异及未解释事项，评价量本核对是否支持主营业务成本结转完整性。采用A/B/C口径。"
        "只输出可直接填入底稿的结论正文。"
    ),
    "rollforward-note": (
        "请生成F5-7主营业务成本倒轧表的审计说明。按四段倒轧链说明："
        "①直接材料成本、②产品生产成本、③产成品成本、④主营业务成本的取数来源与勾稽，"
        "重大调整、与试算表1401/1404/1405及F5-1审定差异。只能依据传入数据。"
    ),
    "rollforward-evaluation": (
        "请生成F5-7成本倒轧表的正式审计结论。评价材料流转→成本构成→成本结转→主营业务成本"
        "各环节勾稽关系及与F5-1审定营业成本的差异。采用A/B/C口径。只输出可直接填入底稿的结论正文。"
    ),
    "adjustment-note": (
        "请生成F5-8主营业务成本账户中重大调整事项核查表的审计说明。"
        "说明各笔重大调整的性质、借贷金额、理由充分性评价，特别关注现金/实物返利是否冲减存货或购货当期成本，"
        "以及与F5-1审定、F5-4分录的勾稽。只能依据传入数据。"
    ),
    "adjustment-evaluation": (
        "请生成F5-8重大调整事项核查表的正式审计结论。评价重大调整理由是否充分、审批与凭证是否完整、"
        "对营业成本列报的影响。采用A/B/C口径。只输出可直接填入底稿的结论正文。"
    ),
    "adjustment-entry-note": (
        "请生成F5-4营业成本调整分录的审计说明：概述AJE/RJE编制依据、主要调整事项"
        "及对6401审定发生额的影响；说明借贷是否平衡。不得虚构未提供的分录内容。"
    ),
    "adjustment-entry-conclusion": (
        "请生成F5-4营业成本调整分录的审计结论，优先采用A/B/C模板，"
        "结合分录平衡性与拟调整事项给出明确表述。只输出可直接填入底稿的正文。"
    ),
}


@router.post("/api/workpapers/{wp_id}/f5/ai-generate")
async def f5_ai_generate(
    wp_id: str,
    body: F5AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> F5AiGenerateResponse:
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
        return F5AiGenerateResponse(content="", sources=[])
    return F5AiGenerateResponse(content=result, sources=[])


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
    ctx: dict = {"client_name": "", "audit_year": ""}
    try:
        result = await db.execute(
            sa.text("""
                SELECT p.client_name, p.audit_year
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
    except Exception as e:
        logger.warning("F5 AI: project context 加载失败: %s", e)
    return ctx
