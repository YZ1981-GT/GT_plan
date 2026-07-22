"""H2 在建工程 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/h2/ai-generate

sections: adj-note / adj-conclusion / analysis-progress /
          analysis-conclusion / analysis-indicator-suggest / analysis-reason /
          cost-comparison-note / interest-cap-summary / impairment-conclusion /
          stocktake-plan / transfer-note / transfer-conclusion
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

router = APIRouter(tags=["h2-ai"])


class H2AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class H2AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "adj-note",
    "adj-conclusion",
    "analysis-progress",
    "analysis-conclusion",
    "analysis-indicator-suggest",
    "analysis-reason",
    "cost-comparison-note",
    "interest-cap-summary",
    "impairment-conclusion",
    "stocktake-plan",
    "transfer-note",
    "transfer-conclusion",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 H2《在建工程》。
科目1604在建工程（借方/资产类）。
核心关注：资产类三角勾稽含转固（期末=期初+增加-减少-转固）、CAS4转固五条件判定、
利息资本化CAS17（无/有专门借款2分支）、工程造价比较分析、工程监盘停工减值迹象。
CAS4固定资产准则：确认条件（五条件全满足方可转固：①实体建造完成②达设计要求③试运转正常④支出已确定⑤可使用状态）。
CAS17借款费用准则：资本化条件（资产支出已发生+借款费用已发生+使资产达到可使用必要活动已开始）、
资本化金额（无专门借款=加权支出×加权资本化率；有专门借款=专门利息-闲置收益+一般借款补充）。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "adj-note": (
        "请生成H2-1在建工程审定表的审计说明，分析在建工程各项目的三角勾稽结果（含转固扣减）、"
        "期初到期末变动的主要原因（增加/减少/转固分别）、未审数与审定数的差异说明。"
    ),
    "adj-conclusion": (
        "请生成H2-1在建工程审定表的审计结论，评价在建工程科目整体的真实性、完整性和计价准确性，"
        "说明转固时点是否恰当、是否发现需要调整的重大事项。"
    ),
    "analysis-progress": (
        "请生成H2-4在建工程分析表的审计说明：覆盖指标分析性程序（本期vs上期）、"
        "异常变动指标、以及各工程项目的完工率/超期/资本化率合理性评价；"
        "说明数据来源（H2-1/H2-2）及拟跟进的细节测试索引。"
    ),
    "analysis-conclusion": (
        "请生成H2-4在建工程分析表的审计结论（分析性程序总体结论，2~6句）："
        "评价指标变动与工程进度/资本化/工期是否合理，是否需追加细节测试，"
        "对存在与完整性认定的初步结论。"
    ),
    "analysis-indicator-suggest": (
        "你正在协助编制H2-4在建工程分析表。模板已有6项基础指标："
        "①在建工程/资产总额 ②期末余额 ③减值准备÷原值 ④实际支出与预算差异 "
        "⑤利息资本化率 ⑥产能利用率。"
        "relatedContext.availableSuggestions 列出尚未添加的候选指标（含 id、name、scenario）。"
        "请根据行业、aggregates（超期项目数、转固、利息等）与已有异常，"
        "建议还应当新增哪些分析指标（优先从 availableSuggestions 中选，也可提出自定义指标名）。"
        "输出格式：先用3~6条简洁中文说明「为何建议、关注什么风险」，"
        "文中务必点名候选指标的 id（如 transfer_ratio）和中文名称，便于前端一键添加。"
        "若现有指标已足够，明确说明「暂无需新增」并简述理由。"
    ),
    "analysis-reason": (
        "请为H2-4指标分析表的每一项指标生成「变动原因及合理性解释」。"
        "输入见 relatedContext.indicators（含 name/current/prior/changePct/abnormal/explanation）。"
        "严格按JSON数组输出，每项含 id（与输入一致）、name、explanation（1~2句审计用语）。"
        "变动不大（|changePct|<20或为空）可写「变动不大，属于正常波动」；"
        "异常项须指出可能原因与建议跟进程序（如→H2-7/H2-10/H2-15），勿虚构未提供的具体事实。"
        "只输出JSON数组，不要markdown代码块包裹以外的废话。"
    ),
    "cost-comparison-note": (
        "请生成H2-7工程造价比较分析表的审计说明：评价各工程单方造价与可比价均值的差异及原因、"
        "可比价来源是否充分；说明本期在建工程增加与现金流量表「购置固定资产、无形资产和其他长期资产"
        "支付的现金」的主体层勾稽结果及重大差异解释；指出是否需补充审计程序。"
    ),
    "interest-cap-summary": (
        "请生成H2-10/H2-11利息资本化测算的汇总说明，分析利息资本化金额的合理性、"
        "资本化期间的恰当性、加权资本化率/专门借款利率的计算方法、"
        "账面资本化金额与测算金额的差异原因。"
    ),
    "impairment-conclusion": (
        "请生成H2-15/H2-16减值测算的审计结论，评价在建工程减值迹象判断的充分性（特别是停工项目）、"
        "可收回金额计算方法（DCF/市场法）及关键假设的合理性、减值计提是否充分。"
    ),
    "stocktake-plan": (
        "请生成H2-12在建工程监盘计划结论（直接输出正文，2~8句）："
        "概括存在性认定风险应对、监盘时间/地点/范围与覆盖率、拟抽盘工程选取、双向抽查与复盘安排，"
        "说明是否可进入H2-13执行盘点检查。"
    ),
    "transfer-note": (
        "请生成H2-5转固时点检查表的审计说明（对齐致同双表逻辑）："
        "说明表一样本（期末仍挂列在建）是否存在已达预定可使用状态未转固及原因/期后转固；"
        "说明表二已转固项目转固时点与验收/试生产/正式投产证据的比对、CAS4五条件判定、"
        "延迟天数关注事项，以及与H2-2转固合计、H1入账金额的勾稽结果。"
    ),
    "transfer-conclusion": (
        "请生成H2-5转固时点检查表的审计结论（2~6句）："
        "评价重大项目转固时点是否恰当，是否存在延迟转固少计折旧或提前转固，"
        "是否需调整（→H2-3）及对折旧的影响；结论应可直接写入底稿。"
    ),
}


@router.post("/api/workpapers/{wp_id}/h2/ai-generate")
async def h2_ai_generate(
    wp_id: str,
    body: H2AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> H2AiGenerateResponse:
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
        return H2AiGenerateResponse(content="", sources=[])
    return H2AiGenerateResponse(content=result, sources=[])


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
        logger.warning("H2 AI: project context 加载失败: %s", e)
    return ctx
