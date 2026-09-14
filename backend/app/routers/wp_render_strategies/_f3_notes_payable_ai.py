"""F3 应付票据 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/f3/ai-generate

sections: adjudication-note / adjudication-conclusion / detail-note /
          detail-conclusion / interest-note / interest-conclusion /
          overdue-evaluation / related-evaluation / debit-check-conclusion /
          credit-check-conclusion
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

router = APIRouter(tags=["f3-ai"])


class F3AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class F3AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "adjudication-note",
    "adjudication-conclusion",
    "detail-note",
    "detail-conclusion",
    "adjustment-note",
    "adjustment-conclusion",
    "interest-note",
    "interest-conclusion",
    "overdue-note",
    "overdue-evaluation",
    "related-note",
    "related-conclusion",
    "related-evaluation",
    "debit-check-conclusion",
    "credit-check-conclusion",
    "voucher-check-note",
    "voucher-check-conclusion",
    "voucher-check-issue",
    "listed-note",
    "soe-note",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 F3《应付票据》。
科目2201应付票据，贷方/负债类。核心关注：带息票据利息测算、逾期票据风险、关联方票据集中度。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "adjudication-note": (
        "请生成F3-1应付票据审定表的审计说明：概述银行承兑汇票和商业承兑汇票"
        "期初、期末未审及审定余额，说明账项调整和重分类事项；核对F3-2明细表及"
        "试算平衡表2201科目的一致性，并关注保证金存款受限、已到期未兑付票据、"
        "关联方开具或承兑票据等事项。不得虚构底稿数据中不存在的程序或证据。"
    ),
    "adjudication-conclusion": (
        "请生成F3-1应付票据审定表的审计结论。结合期末审定合计与试算平衡表差异、"
        "银行/商业承兑分类及异常事项，采用明确的A/B/C口径：A为未见重大异常；"
        "B为除已识别调整或说明事项外未见重大异常；C为存在重大未调整差异或范围受限，"
        "无法确认。只输出可直接填入底稿的结论正文。"
    ),
    "detail-note": (
        "请生成F3-2期末应付票据明细表的审计说明：概述票据类别及余额构成，"
        "说明与应付票据备查簿、征信报告、承兑保证金及其他货币资金的核对情况；"
        "重点列明逾期票据、关联方票据、未函证票据、账项调整及重分类事项。"
        "必须以传入的汇总和异常明细为依据，不得虚构程序或证据。"
    ),
    "detail-conclusion": (
        "请生成F3-2期末应付票据明细表的正式审计结论。结合期末审定余额、"
        "逾期账龄、函证、保证金以及调整事项，采用A/B/C口径：A为未见异常；"
        "B为除已识别调整或说明事项外未见异常；C为存在重大未调整事项或范围受限，"
        "不可确认。只输出可直接填入底稿的结论正文。"
    ),
    "adjustment-note": (
        "请生成F3-3应付票据调整分录的审计说明：概述AJE/RJE编制依据、"
        "主要调整事项（如逾期重分类、利息补提、保证金重分类）及对审定数的影响；"
        "说明借贷是否平衡。不得虚构未提供的分录内容。"
    ),
    "adjustment-conclusion": (
        "请生成F3-3应付票据调整分录的审计结论，优先采用A/B/C模板，"
        "结合分录平衡性与拟调整事项给出明确表述。"
    ),
    "interest-note": (
        "请生成F3-4应付票据（带息）利息测算表的审计说明：概述带息票据的笔数、"
        "票面金额合计及测算方法（应计利息=票面金额×票面利率×期限/360），"
        "说明应计利息测算数与账面已计利息的差异情况及原因，列明拟调整事项"
        "（补提或冲回应付利息）。必须以传入的汇总和差异明细为依据，不得虚构数据。"
    ),
    "interest-conclusion": (
        "请生成F3-4应付票据（带息）利息测算表的审计结论。结合应计利息测算数与"
        "账面已计利息的差异合计及重大差异笔数，评价利息是否足额计提、会计处理是否正确，"
        "采用A/B/C口径：A为利息计提充分准确未见异常；B为除已识别调整事项外未见异常；"
        "C为存在重大未调整差异。只输出可直接填入底稿的结论正文。"
    ),
    "overdue-note": (
        "请生成F3-5逾期未付票据检查表的审计说明。根据传入数据概述逾期票据笔数、"
        "票面金额、期后支付和尚未支付金额，说明借款或违约条件、会计调整、抵押担保"
        "及诉讼事项的检查结果，分析对信用风险和持续经营能力的影响。"
        "不得声称已取得传入数据未体现的凭证或法律文件。"
    ),
    "overdue-evaluation": (
        "请生成F3-5逾期未付票据检查表的审计结论。结合期后支付、未付金额、逾期时长、"
        "会计调整、抵押担保及诉讼/持续经营风险，评价相关会计处理和披露是否恰当。"
        "采用A/B/C口径：A为未见重大异常；B为除已识别调整或披露事项外未见重大异常；"
        "C为存在重大未调整事项或持续经营重大不确定性。只输出可直接填入底稿的正文。"
    ),
    "related-note": (
        "请生成F3-6应付票据关联方及交易检查表的审计说明。根据传入数据概述关联方数量、"
        "期初余额、本期借贷发生、期末余额及期后付款，说明关联方识别来源和余额勾稽情况，"
        "评价交易商业实质、款项性质、定价政策及余额集中度，并说明关联方交易和余额披露核查结果。"
        "不得虚构未执行的程序或未取得的证据。"
    ),
    "related-conclusion": (
        "请生成F3-6应付票据关联方及交易检查表的审计结论。结合余额公式勾稽、商业实质、"
        "定价政策、期后付款、异常集中度和披露情况，评价交易真实性、合理性、合法性及会计处理。"
        "采用A/B/C口径：A为未见重大异常；B为除已识别调整或披露事项外未见重大异常；"
        "C为存在重大未调整差异、缺乏商业实质或披露重大遗漏。只输出可直接填入底稿的正文。"
    ),
    "related-evaluation": "请生成F3-6关联方票据检查的审计说明，评价集中度、结算方式及定价公允性。",
    "debit-check-conclusion": "请生成F3-7借方检查区（票据减少）的总体审计结论。",
    "credit-check-conclusion": "请生成F3-7贷方检查区（票据增加）的总体审计结论。",
    "voucher-check-note": (
        "请生成F3-7应付票据检查表的审计说明。三个检查区：本期借方（兑付，核对付款审批单"
        "和银行回单）、本期贷方（开票，核对入库单/验收单和采购发票）、资产负债表日后借方"
        "（关注应计未计票据）。根据传入的样本笔数、检查金额、检查比例和异常明细，说明样本"
        "选取标准与规模、原始凭证核对情况、检查比例是否充分（比例较低应扩大样本或说明原因）"
        "及异常凭证处理。不得虚构未执行的程序或未取得的单据。"
    ),
    "voucher-check-conclusion": (
        "请生成F3-7应付票据检查表的审计结论。结合三个检查区（本期借方、本期贷方、"
        "资产负债表日后借方）的检查金额、检查比例和异常笔数，评价：1.应付票据存在且记录于"
        "恰当账户；2.由被审计单位拥有或控制；3.金额恰当、记录于恰当会计期间、披露恰当。"
        "采用A/B/C口径：A为未见重大异常；B为除已识别调整或说明事项外未见重大异常；"
        "C为存在重大未调整差异或范围受限。只输出可直接填入底稿的结论正文。"
    ),
    "voucher-check-issue": (
        "请针对F3-7应付票据检查表中的单笔凭证生成异常/检查说明。根据传入的凭证信息"
        "（日期、编号、业务内容、金额、票据类别）及单据勾稽结果（付款审批单/银行回单或"
        "入库单/采购发票的缺失、金额不符情况），简明扼要地说明该笔凭证的核对结果、"
        "异常性质及建议的处理措施（补充单据、追加程序或提请调整）。"
        "2-4句话即可，只输出正文。"
    ),
    "listed-note": (
        "请生成上市公司口径应付票据附注披露说明文字：可涵盖已到期未支付金额、"
        "保证金受限、关联方票据等，语言简洁、适合直接写入附注说明栏。"
        "不得虚构传入数据中不存在的金额或事项。"
    ),
    "soe-note": (
        "请生成国有企业口径应付票据附注披露说明文字：应说明本期已到期未支付的"
        "应付票据总金额，并可补充保证金受限、关联方票据等事项。"
        "不得虚构传入数据中不存在的金额或事项。"
    ),
}


@router.post("/api/workpapers/{wp_id}/f3/ai-generate")
async def f3_ai_generate(
    wp_id: str,
    body: F3AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> F3AiGenerateResponse:
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
        return F3AiGenerateResponse(content="", sources=[])
    return F3AiGenerateResponse(content=result, sources=[])


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
        logger.warning("F3 AI: project context 加载失败: %s", e)
    return ctx
