"""F4 应付账款 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/f4/ai-generate

sections: adjudication-* / detail-* / adjustment-* / substantive-*-note|conclusion /
          long-outstanding-note|conclusion / related-party-note|conclusion /
          unrecorded-note|conclusion / voucher-check-note|conclusion|issue /
          financing-note|conclusion / disclosure-*
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

router = APIRouter(tags=["f4-ai"])


class F4AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class F4AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "adjudication-reason",
    "adjudication-note",
    "adjudication-conclusion",
    "detail-note",
    "detail-conclusion",
    "adjustment-note",
    "adjustment-conclusion",
    "substantive-turnover-note",
    "substantive-creditor-note",
    "substantive-conclusion",
    "long-outstanding-note",
    "long-outstanding-conclusion",
    "related-party-note",
    "related-party-conclusion",
    "unrecorded-conclusion",
    "unrecorded-note",
    "voucher-check",
    "voucher-check-note",
    "voucher-check-conclusion",
    "voucher-check-issue",
    "financing-evaluation",
    "financing-note",
    "financing-conclusion",
    "disclosure-listed",
    "disclosure-listed-note",
    "disclosure-listed-conclusion",
    "disclosure-soe",
    "disclosure-soe-note",
    "disclosure-soe-conclusion",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 F4《应付账款》。
科目2202应付账款，贷方/负债类。核心关注：长期挂账风险、未入账负债（反向截止测试）、关联方集中度、供应商融资合规性。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "adjudication-reason": (
        "请为F4-1应付账款审定表中指定性质或账龄项目生成余额变动原因分析。"
        "结合上期审定数、本期审定数、变动额和变动率，使用审计底稿语言说明可能的业务驱动，"
        "但只能依据传入数据，不得虚构采购合同、工程进度、付款安排或其他证据。"
        "若传入信息不足，应明确建议向管理层了解并核对明细。控制在2至4句话。"
    ),
    "adjudication-note": (
        "请生成F4-1应付账款审定表的审计说明。先概述期初、期末审定余额及总体变动，"
        "重点分析变动率绝对值超过30%的性质项目；再说明1年以上账龄余额及长期挂账关注；"
        "最后说明按性质与按账龄分类是否勾稽一致，以及期初、期末审定数与试算平衡表2202科目"
        "是否一致。涉及差异时应列明差异和建议核查程序，不得虚构未取得的证据。"
    ),
    "adjudication-conclusion": (
        "请生成F4-1应付账款审定表的正式审计结论。结合按性质及按账龄分类、账项调整和"
        "重分类调整、重大余额变动、双口径交叉核对及与试算平衡表的差异，评价应付账款余额"
        "的完整性、准确性、分类和列报。采用A/B/C口径：A为未见重大异常；B为除已识别调整"
        "或说明事项外未见重大异常；C为存在重大未调整差异、分类不一致或审计范围受限。"
        "只输出可直接填入底稿的结论正文。"
    ),
    "detail-note": (
        "请生成F4-2应付账款明细表的审计说明，按源表五项逻辑组织正文："
        "（1）期初数与上期审定数、期末总账/明细账/报表的核对情况；"
        "（2）期末余额重大变动及可能的业务原因；（3）大额借贷方发生额及关注事项；"
        "（4）账龄超过1年特别是3年以上的大额款项性质、未偿还或未结转原因；"
        "（5）期后付款及期后付款超过资产负债表日余额的异常事项。"
        "同时说明未审账龄与期末未审余额、审定账龄与审定数是否勾稽，以及关联方款项、"
        "AJE/RJE和异常行的检查结果。只能依据传入数据，不得虚构已执行程序、合同或回函。"
    ),
    "detail-conclusion": (
        "请生成F4-2应付账款明细表的正式审计结论。结合明细完整性、期初至期末滚动公式、"
        "未审及审定两层账龄勾稽、重大调整/重分类、长期挂账、关联方及期后付款异常，"
        "评价余额的存在、完整性、计价、分类和列报。采用A/B/C口径：A为未见重大异常；"
        "B为除已识别调整或说明事项外未见重大异常；C为存在重大未调整事项、账龄不勾稽"
        "或审计范围受限。只输出可直接填入底稿的结论正文。"
    ),
    "adjustment-note": (
        "请生成F4-3应付账款调整分录的审计说明：概述AJE/RJE编制依据、主要调整事项"
        "及对审定数的影响；说明借贷是否平衡。不得虚构未提供的分录内容。"
    ),
    "adjustment-conclusion": (
        "请生成F4-3应付账款调整分录的审计结论，优先采用A/B/C模板，"
        "结合分录平衡性与拟调整事项给出明确表述。只输出可直接填入底稿的正文。"
    ),
    "substantive-turnover-note": (
        "请生成F4-4应付账款周转率（支付期）分析的审计说明。依据本期/上期主营业务成本、"
        "存货期初期末、应付账款期初期末，说明采购成本口径（成本+期末存货-期初存货）、"
        "周转率及平均支付天数的同比变化，并评价与同行业平均周转率的差异。"
        "只依据传入数据解释趋势；数据不足或无法计算时明确指出待补数据，不得虚构付款政策或行业证据。"
    ),
    "substantive-creditor-note": (
        "请生成F4-4期末应付账款前十名债权人分析的审计说明。根据实际债权人名称、"
        "期末审定数、上年年末余额、变动金额/比例及发生原因，概述余额集中度和重大增减项目；"
        "对变动率绝对值超过20%、上期为零、关联方或原因不完整的项目提出针对性核查建议。"
        "不得使用“债权人1/2/3”等占位名称，不得虚构合同、采购或付款证据。"
    ),
    "substantive-conclusion": (
        "请生成F4-4应付账款实质性分析的正式审计结论。综合付款期趋势、同行业差异、"
        "前十名债权人集中度和重大余额变动，评价应付账款余额变动是否合理以及是否需要"
        "进一步实施合同/采购/付款/函证/期后事项核查。采用A/B/C口径：A为未见重大异常；"
        "B为除已识别关注事项外未见重大异常；C为存在重大无法解释波动或审计证据不足。"
        "只输出可直接填入底稿的结论正文。"
    ),
    "long-outstanding-note": (
        "请生成F4-5账龄1年以上应付账款检查表的审计说明。按债权人概述期末余额、账龄、"
        "经济业务、未偿还或未结转原因、支付计划和审定金额；重点说明无法支付、涉及诉讼、"
        "3年以上、缺少支持性证据及存在审计调整的项目。评价合同、对账单、付款计划、"
        "银行回单、诉讼文书或律师函等证据是否与填写结论相符。不得将“长期挂账”直接推断为"
        "债务灭失或应转营业外收入，不得虚构未取得的证据。"
    ),
    "long-outstanding-conclusion": (
        "请生成F4-5账龄1年以上应付账款检查的正式审计结论。综合长期未偿还原因、支付能力、"
        "诉讼状态、支付计划、审定金额及支持性证据，评价应付账款的存在、完整性、计价、"
        "终止确认和列报是否恰当。采用A/B/C口径：A为证据充分且未见重大异常；"
        "B为除已识别调整或待补证据事项外未见重大异常；C为存在重大无法支付/诉讼事项、"
        "余额无法确认或审计证据不足。只输出可直接填入底稿的结论正文。"
    ),
    "related-party-note": (
        "请生成F4-6应付账款关联方及交易检查表的审计说明。按实际关联方概述关联关系、"
        "期初余额、本期借贷发生、期末余额、账龄、定价政策、交易性质和期后付款；"
        "说明期末=期初+贷方-借方的勾稽及与F4-2审定数的核对结果。重点分析关联关系未细化、"
        "定价政策缺失、长期账龄无期后付款、借方余额、异常付款、余额高度集中及索引证据缺失事项。"
        "还应说明关联方清单完整性和关联交易/余额披露核对程序。不得虚构定价证据或关联关系。"
    ),
    "related-party-conclusion": (
        "请生成F4-6应付账款关联方及交易检查的正式审计结论，评价关联方识别是否完整，"
        "交易是否真实、合理、合法，定价是否具有依据，余额和会计处理是否准确，期后付款是否异常，"
        "关联交易及余额披露是否完整正确。采用A/B/C口径：A为证据充分且未见重大异常；"
        "B为除已识别调整、披露更正或待补证据事项外未见重大异常；C为存在重大未识别关联方、"
        "异常利益输送、余额无法核对或披露重大遗漏。只输出可直接填入底稿的结论正文。"
    ),
    "unrecorded-note": (
        "请生成F4-7未入账应付账款检查的审计说明，按五类程序分别说明："
        "大额供应商平均付款期及期后付款比较；料到单未到项目的入库单、合同不含税单价、"
        "暂估金额和记账凭证核对；现场截止日未处理供应商发票的归属期判断；"
        "期后付款凭证与银行付款单/对账单核对；期后增加凭证与购货发票核对。"
        "列明应计入报告期金额、未去重候选调整和证据不完整项目；同一负债可能同时出现在发票、"
        "付款和期后增加测试中，形成调整前必须按供应商、单据和金额去重。不得根据OCR结果直接作归属期判断，"
        "不得虚构未取得的账外清单或单据。"
    ),
    "unrecorded-conclusion": (
        "请生成F4-7未入账应付账款检查的正式审计结论。综合五类程序评价负债完整性、"
        "采购截止、付款截止及相关披露是否恰当，并说明已识别未入账金额及建议调整。"
        "采用A/B/C口径：A为多时段和多单据核对证据充分且未见重大未入账；"
        "B为除已识别调整或待补证据事项外未见重大异常；C为存在重大未入账负债、"
        "截止性错报或账外资料不完整导致证据不足。只输出可直接填入底稿的结论正文。"
    ),
    "voucher-check-note": (
        "请生成F4-8应付账款检查表的审计说明。两个检查区：本期借方（付款/减少，核对付款审批单"
        "和银行回单）、本期贷方（采购/增加，核对入库单/验收单和采购发票，可结合存货采购入库检查F2-33）。"
        "根据传入的样本笔数、检查金额、与F4-2账面发生额的检查比例和异常明细，说明样本选取标准与规模、"
        "原始凭证核对情况、检查比例是否充分（比例较低应扩大样本或说明原因）及异常凭证处理。"
        "不得虚构未执行的程序或未取得的单据。"
    ),
    "voucher-check-conclusion": (
        "请生成F4-8应付账款检查表的正式审计结论。结合借/贷两区的检查金额、检查比例和异常笔数，评价："
        "1.资产负债表中记录的应付账款是存在的，且已经记录在恰当的账户中；"
        "2.记录的应付账款由被审计单位拥有或控制；"
        "3.应付账款以恰当的金额包括在财务报表中，相关计价分摊调整及披露恰当。"
        "采用A/B/C口径：A为未见重大异常；B为除已识别调整或说明事项外未见重大异常；"
        "C为存在重大未调整差异或范围受限。只输出可直接填入底稿的结论正文。"
    ),
    "voucher-check-issue": (
        "请针对F4-8应付账款检查表中的单笔凭证生成异常/检查说明。根据传入的凭证信息"
        "（供应商、日期、编号、业务内容、对方科目、金额）及单据勾稽结果（付款审批单/银行回单或"
        "入库单/采购发票的缺失、金额不符、对手方不一致等情况），简明扼要地说明该笔凭证的核对结果、"
        "异常性质及建议的处理措施（补充单据、追加程序或提请调整）。"
        "2-4句话即可，只输出正文。"
    ),
    "financing-note": (
        "请生成F4-9供应商融资检查表的审计说明。说明：1.供应链融资平台明细与企业台账核对结果；"
        "2.各供应商融资金额、本期采购金额、差异及借款余额；"
        "3.融资金额大于采购金额项目的资金流向关注及是否需穿透检查；"
        "4.对金融机构直接支付给供应商款项的账务处理和披露是否正确完整。"
        "只能依据传入数据，不得虚构未取得的平台导出、合同或回单。"
    ),
    "financing-conclusion": (
        "请生成F4-9供应商融资检查表的正式审计结论。综合平台与台账核对、融资金额与采购差异、"
        "借款余额、直付供应商账务及披露，评价应付账款及相关供应商融资披露的完整性与恰当性。"
        "采用A/B/C口径：A为证据充分且未见重大异常；B为除已识别调整或待补证据事项外未见重大异常；"
        "C为存在重大虚假采购融资、体外循环迹象或披露重大遗漏。只输出可直接填入底稿的结论正文。"
    ),
    "disclosure-listed": (
        "请生成应付账款附注披露文字（上市公司口径）。根据传入的按性质披露表"
        "（各项目期末余额、上年年末余额及合计）和账龄超过1年的重要应付账款明细"
        "（债权人、期末余额、未偿还或未结转的原因），按企业会计准则附注格式撰写披露正文："
        "先列示按性质分类的期末与上年年末余额，再披露账龄超过1年的重要应付账款及其"
        "未偿还或未结转原因。金额必须与传入数据一致，不得虚构披露项目。"
    ),
    "disclosure-listed-note": (
        "请生成应付账款附注披露（上市公司）的审计说明。说明披露数据与F4-1审定表"
        "（期末=期末审定数、上年年末=期初审定数）及F4-5长期挂账检查表的核对情况，"
        "披露合计与审定合计是否一致，账龄超过1年项目的披露完整性。"
        "存在不一致时应列明差异并建议核查，不得虚构核对程序。"
    ),
    "disclosure-listed-conclusion": (
        "请生成应付账款附注披露（上市公司）的审计结论。评价按性质分类披露、"
        "账龄超过1年重要应付账款及原因披露是否完整、准确并符合企业会计准则和"
        "上市公司信息披露要求。采用A/B/C口径：A为披露恰当；B为除已识别披露调整外恰当；"
        "C为存在重大披露遗漏或错报。只输出可直接填入底稿的结论正文。"
    ),
    "disclosure-soe": (
        "请生成应付账款附注披露文字（国有企业口径）。根据传入的按账龄披露表"
        "（1年以内、1至2年、2至3年、3年以上各档期末余额、期初余额及合计）和"
        "账龄超过1年的重要应付账款明细（债权单位名称、期末余额、未偿还原因），"
        "按企业会计准则及国资监管附注格式撰写披露正文：先列示按账龄分类的期末与期初余额，"
        "再披露账龄超过1年的重要应付账款及其未偿还原因。"
        "金额必须与传入数据一致，不得虚构披露项目。"
    ),
    "disclosure-soe-note": (
        "请生成应付账款附注披露（国企）的审计说明。说明按账龄披露数据与F4-1审定表按账龄分类"
        "（期末=期末审定数、期初=期初审定数）及F4-5长期挂账检查表的核对情况，"
        "按账龄披露合计与按性质审定合计是否交叉一致，账龄超过1年重要应付账款的披露完整性。"
        "存在不一致时应列明差异并建议核查，不得虚构核对程序。"
    ),
    "disclosure-soe-conclusion": (
        "请生成应付账款附注披露（国企）的审计结论。评价按账龄分类披露、"
        "账龄超过1年重要应付账款及未偿还原因披露是否完整、准确并符合企业会计准则和"
        "国资监管列报要求。采用A/B/C口径：A为披露恰当；B为除已识别披露调整外恰当；"
        "C为存在重大披露遗漏或错报。只输出可直接填入底稿的结论正文。"
    ),
}

# 区块级别名：前端按整个区块请求时（不带 -note 后缀）复用该区块的说明提示词
_SECTION_PROMPTS["voucher-check"] = _SECTION_PROMPTS["voucher-check-note"]
_SECTION_PROMPTS["financing-evaluation"] = _SECTION_PROMPTS["financing-note"]


@router.post("/api/workpapers/{wp_id}/f4/ai-generate")
async def f4_ai_generate(
    wp_id: str,
    body: F4AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> F4AiGenerateResponse:
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
        return F4AiGenerateResponse(content="", sources=[])
    return F4AiGenerateResponse(content=result, sources=[])


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
        logger.warning("F4 AI: project context 加载失败: %s", e)
    return ctx
