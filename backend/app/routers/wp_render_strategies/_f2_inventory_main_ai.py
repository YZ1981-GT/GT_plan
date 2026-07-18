"""F2 存货核心组 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/f2/ai-generate
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

router = APIRouter(tags=["f2-ai"])


class F2AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class F2AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "adj-note",
    "adj-conclusion",
    "analysis-conclusion",
    "cutoff-conclusion",
    "cutoff-process-note",
    "cutoff-audit-note",
    "cutoff-standard-conclusion",
    "policy-evaluation",
    "production-sales-conclusion",
    "cost-comparison-conclusion",
    "summary-note",
    "summary-conclusion",
    "summary-objective",
    "summary-process",
    "summary-change-reason",
    "detail-valuation",
    "detail-change",
    "detail-long-aging",
    "detail-impairment",
    "detail-conclusion",
    "listed-note-category",
    "listed-note-nrv",
    "listed-note-provision",
    "listed-note-borrow",
    "listed-note-re",
    "soe-note-category",
    "soe-note-borrow",
    "soe-note-amort",
    "f2-14-note",
    "f2-14-conclusion",
    "f2-14-summary",
    "f2-16-note",
    "f2-16-conclusion",
    "f2-16-process",
    "f2-18-note-a",
    "f2-18-note-b",
    "f2-18-note-c",
    "f2-18-note-d",
    "f2-18-abnormal",
    "f2-18-conclusion",
    "f2-19-note",
    "f2-19-conclusion",
    "f2-20-note",
    "f2-20-abnormal",
    "f2-20-conclusion",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 F2《存货》。
科目1401~1412存货，借方/资产类。核心关注：收发存核对、计价测试、跌价准备、截止测试、库龄分析。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "adj-note": "请生成F2-1存货审定表的审计说明，涵盖存货总体状况、主要审计程序及发现。",
    "adj-conclusion": "请生成F2-1存货审定表的审计结论，评价存货账面价值是否公允反映。",
    "summary-note": (
        "请生成F2-2存货明细汇总表的审计说明。结合各类别原值/跌价/账面价值未审与审定差异、"
        "跨表明细勾稽及重大调整，概述测试情况与拟调整影响；不得虚构未提供的金额。"
    ),
    "summary-conclusion": (
        "请生成F2-2存货明细汇总表的审计结论，仅采用A/B/C之一开头："
        "A未见异常；B除已识别拟调整事项外其余未见异常；C存在重大未调整或范围受限不可确认。"
    ),
    "summary-objective": (
        "请生成F2-2存货明细汇总表「一、审计目标」条目，通常涵盖存在、权利与义务、完整性、计价与分摊等，"
        "用编号列表，简洁适合底稿页眉区。"
    ),
    "summary-process": (
        "请生成F2-2存货明细汇总表「二、审计过程」条目，说明取得明细并与总账核对、抽查收发存、"
        "截止测试、库龄与跌价分析等程序，用编号列表，不得虚构已执行但未提供的程序结果。"
    ),
    "summary-change-reason": (
        "请基于上下文中各类别审定变动率，生成存货账面价值「变动原因分析」提示要点（按类别），"
        "便于审计人员粘贴到对应行；变动不显著的可写「变动不重大」。"
    ),
    "detail-valuation": "请撰写该类存货明细表审计说明第1问：计价方法。",
    "detail-change": "请撰写该类存货明细表审计说明第2问：本期发生重大变动的原因。",
    "detail-long-aging": "请撰写该类存货明细表审计说明第3问：库龄较长的原因。",
    "detail-impairment": "请撰写该类存货明细表审计说明第4问：计提跌价准备的主要项目及原因。",
    "detail-conclusion": "请生成该类存货明细表的审计结论，可采用A/B/C模板。",
    "cutoff-conclusion": (
        "请生成F2-29~32存货截止测试审计结论。结合追查方向（账→单存在/发生，或单→账完整性）、"
        "截止日前后抽样天数、跨期笔数与金额、差异样本摘要，评价期间归属是否恰当；"
        "优先采用A/B/C结论模板，指出拟调整或需扩大测试的事项。"
    ),
    "cutoff-process-note": (
        "请生成F2-29~32存货截止测试的过程补充说明。结合底稿类型、追查方向、抽样窗口、"
        "金额门槛、样本分类及监盘/收入截止勾稽情况，简洁说明样本选取和核查过程；"
        "不得虚构未提供的凭证编号或核查结果。"
    ),
    "cutoff-audit-note": (
        "请生成F2-29~32存货截止测试审计说明。概述抽样范围、账证/单账勾稽、"
        "截止日前后期间归属核实、异常样本及拟调整或扩大测试情况；"
        "如上下文没有异常，应使用审慎的未见异常表述。"
    ),
    "cutoff-standard-conclusion": (
        "请生成F2-29~32存货截止测试标准审计结论，仅采用A/B/C之一开头并给出简洁依据："
        "A表示未见异常；B表示除已识别并拟调整事项外其余未见异常；"
        "C表示存在重大未调整错报或范围受限，无法确认截止准确性。"
    ),
    "listed-note-category": "请撰写存货附注「分类说明」披露文字。",
    "listed-note-nrv": "请撰写上市附注披露：可变现净值确定依据及转回/转销原因。",
    "listed-note-provision": "请撰写上市附注披露：存货跌价准备计提的具体依据。",
    "listed-note-borrow": "请撰写存货期末余额中含有借款费用资本化金额的说明。",
    "listed-note-re": "请撰写房地产开发企业对外披露补充说明。",
    "soe-note-category": "请撰写国有企业存货附注「分类说明」。",
    "soe-note-borrow": "请撰写国企口径存货借款费用资本化说明。",
    "soe-note-amort": "请撰写合同履约成本本期摊销金额及说明。",
    "f2-14-note": (
        "请生成F2-14存货调整分录汇总的审计说明：概述AJE/RJE编制依据、"
        "主要调整事项及对F2-1审定数的影响；说明借贷是否平衡。"
    ),
    "f2-14-conclusion": (
        "请生成F2-14调整分录的审计结论，优先采用A/B/C模板，"
        "结合分录平衡性与对审定表回写结果给出明确表述。"
    ),
    "f2-14-summary": (
        "请为单笔存货调整分录撰写「调整事项说明」，表述简洁适合表格单元格。"
    ),
    "f2-16-note": (
        "请生成F2-16存货会计政策、核算流程检查表的审计说明："
        "概述政策符合准则/一贯采用的核查情况、成本核算流程了解结果。"
    ),
    "f2-16-conclusion": (
        "请生成F2-16审计结论（政策评价结论），优先A/B/C模板，"
        "结合政策合规性、一贯性及成本核算流程合理性。"
    ),
    "f2-16-process": (
        "请撰写F2-16「存货成本核算」某一分项叙述，依据 fieldLabel 指向的具体环节。"
    ),
    "policy-evaluation": (
        "请生成F2-16存货会计政策评价结论，评价发出计价、可变现净值、跌价准备、盘存制度等"
        "是否符合企业会计准则第1号且前后一贯；可采用A/B/C结论模板。"
    ),
    "analysis-conclusion": (
        "请生成F2-18存货总体分析的审计结论，涵盖构成、周转指标、同行业比较与产品大类周转，"
        "识别异常波动及减值迹象；可采用A/B/C结论模板。"
    ),
    "f2-18-note-a": (
        "请撰写F2-18「存货构成分析」审计说明：概括三期结构变化、重大占比变动及关注点。"
    ),
    "f2-18-note-b": (
        "请撰写F2-18「存货指标三期对比」审计说明：评价周转率/天数、跌价占比、存货占流动资产等变动。"
    ),
    "f2-18-note-c": (
        "请撰写F2-18「同行业对比」审计说明：对照行业平均与对标公司偏差，评价是否异常。"
    ),
    "f2-18-note-d": (
        "请撰写F2-18「主要产品大类周转」审计说明：指出周转显著放缓或加快的产品类别。"
    ),
    "f2-18-abnormal": (
        "请根据底稿中已标记异常的构成/指标项，撰写「异常原因」说明，条理清晰、可复核。"
    ),
    "f2-18-conclusion": (
        "请生成F2-18总体分析结论（分析结论/审计结论），优先A/B/C模板，"
        "结合构成、指标、行业与产品周转异常标记给出明确结论。"
    ),
    "production-sales-conclusion": (
        "请生成F2-19产销量变动分析审计结论，关注产销匹配、购耗产出比异常及是否需延伸至F2-64；可采用A/B/C模板。"
    ),
    "f2-19-note": (
        "请撰写F2-19审计说明中某一分项（产量波动/同比变动/购耗勾稽/进一步索引等），专业简洁。"
    ),
    "f2-19-conclusion": (
        "请生成F2-19存货产销量变动分析的审计结论，优先A/B/C模板。"
    ),
    "cost-comparison-conclusion": (
        "请生成F2-20产品单位成本比较审计结论，关注材料/人工/制造费用波动及异常产品；可采用A/B/C模板。"
    ),
    "f2-20-note": (
        "请撰写F2-20「审计说明」：概述单位成本比较程序、关注产品与交叉索引情况，"
        "不展开逐项异常原因（异常原因另有字段）。"
    ),
    "f2-20-abnormal": (
        "请根据底稿中已标记异常（或合计波动超阈值）的产品，撰写「异常原因」说明："
        "区分材料/人工/制造费用哪一块驱动，并可提示交叉索引F2-64/F2-61等，条理清晰、可复核。"
    ),
    "f2-20-conclusion": (
        "请生成F2-20产成品单位成本年度比较的审计结论，优先A/B/C模板，"
        "结合异常产品数量与追查情况给出明确表述。"
    ),
}


@router.post("/api/workpapers/{wp_id}/f2/ai-generate")
async def f2_ai_generate(
    wp_id: str,
    body: F2AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> F2AiGenerateResponse:
    if not getattr(settings, "WP_AI_SERVICE_ENABLED", True):
        raise HTTPException(503, "AI 服务未启用")
    if body.section not in _SUPPORTED_SECTIONS:
        raise HTTPException(400, f"不支持的 section: {body.section}")

    project_context = await _load_project_context(wp_id, db)
    user_prompt = _build_user_prompt(body.section, body.existingContent, body.relatedContext, project_context)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    result = await chat_completion(messages=messages, temperature=0.3, max_tokens=2000)
    if isinstance(result, str) and result.startswith("["):
        return F2AiGenerateResponse(content="", sources=[])
    return F2AiGenerateResponse(content=result, sources=[])


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
        logger.warning("F2 AI: project context 加载失败: %s", e)
    return ctx
