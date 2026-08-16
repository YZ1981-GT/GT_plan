"""K0 管理循环函证 — AI 辅助生成端点.

POST /api/workpapers/{wp_id}/k0/ai/{section}

sections:
- alternative-audit-note       → K0-5/K0-6 替代程序审计说明
- alternative-audit-conclusion → K0-5/K0-6 替代程序审计结论
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

router = APIRouter(tags=["k0-ai"])


class K0AiGenerateRequest(BaseModel):
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class K0AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    # K0-5 / K0-6 替代程序检查表（既有）
    "alternative-audit-note",
    "alternative-audit-conclusion",
    # K0-1 下区「三、审计说明」5 段 + 「四、审计结论」
    # 🔴 本端点是**硬门**（下方 `if section not in _SUPPORTED_SECTIONS: raise 400`），
    #    前端 `catch` 会把 400 吞成「AI 生成失败」⇒ 漏登记等于按钮空转。
    #    与前端 `k0LowerZoneSpec.K0_AI_SECTIONS` 交叉锁死（守卫双向断言）。
    # spec: k0-confirmation-source-alignment R3.7 / Task 10
    "k0-summary-control",
    "k0-summary-error-analysis",
    "k0-summary-reliability",
    "k0-summary-mismatch",
    "k0-summary-unreplied-alternative",
    "k0-summary-conclusion",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 K0《管理循环函证》。
科目覆盖：其他应收款、其他应付款（往来款项第三方函证确认）。
核心关注：未回函被函证单位的替代程序（期后收付款检查、期末余额支持性证据、
本期发生额检查、往来对账/协议证据）；往来对账差异分析；
期后收回/付款比例评价；与K1/K3往来信息交叉核对。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "alternative-audit-note": (
        "请生成管理循环函证替代程序检查表的审计说明，描述对未回函被函证单位执行的替代程序范围、"
        "抽样方法、检查证据类型（银行回单/借款协议/原始单据/审批凭证/对账单/往来协议等），"
        "以及期后收付款比例、往来对账比例的计算依据。"
    ),
    "alternative-audit-conclusion": (
        "请生成管理循环函证替代程序检查表的审计结论，评价替代程序所获取证据的充分适当性，"
        "对其他应收款/其他应付款的存在性、完整性、计价与权利义务作出结论。"
    ),
    # ─── K0-1 下区「三、审计说明」5 段（标题逐字取自源模板 S28/X28/S32/X32/S36）───
    # 🔴 每条 prompt 都写明源模板口径 + 「不得虚构」约束（平台铁律：过短的笼统 prompt
    #    会诱导模型自造披露内容；≥20 字且点明口径来源）。
    "k0-summary-control": (
        "请生成 K0-1《函证结果汇总表》「1.对询证函保持的控制的说明」。"
        "按准则 1312 的控制要求描述：询证函由审计项目组亲自寄发、回函直接寄至项目组、"
        "地址与联系方式经独立核实（见 K0-2 核实被函证单位信息）、跟函过程留痕（见 K0-3）。"
        "**不得虚构**未在底稿中记录的控制措施；未执行或无法判断的环节写「[待补充]」。"
    ),
    "k0-summary-error-analysis": (
        "请生成 K0-1「2.对误差的分析」。源模板界定误差构成条件为「不符事项的金额高于或低于"
        "账户余额人民币（）万元，并且被审计单位不能合理解释其差异并提供相应依据」——"
        "请据此说明本次函证界定的误差门槛、发现的不符事项笔数与金额、是否构成误差及其理由。"
        "**不得虚构**具体金额；未确定的门槛与未查明的差异原因写「[待补充]」。"
    ),
    "k0-summary-reliability": (
        "请生成 K0-1「3.对以传真或电子邮件形式收到的回函的可靠性的考虑」。"
        "按准则 1312 说明：电子形式回函可靠性低于原件，需验证发件人身份、邮箱/传真号与"
        "被函证单位公开信息一致、必要时致电确认，并要求在审计报告日前寄回原件"
        "（验证过程见 K0-7 邮件传真回函可靠性验证表）。"
        "同时说明「如果回函中存在未函证的其他信息，应考虑未函证信息的影响，"
        "并考虑实施进一步审计程序」的处理。**不得虚构**未实际执行的验证步骤。"
    ),
    "k0-summary-mismatch": (
        "请生成 K0-1「4.针对不符事项的程序」。说明对回函金额与账面不符的项目执行的程序："
        "取得差异明细并编制调节表（见 K0-4 函证差异调节表）、区分时间性差异与错报、"
        "检查支持性证据、评价是否需提出审计调整。"
        "**不得虚构**差异原因与调整金额；未查明的写「[待补充]」。"
    ),
    "k0-summary-unreplied-alternative": (
        "请生成 K0-1「5.针对未回函的替代程序」。说明对未回函被函证单位执行的替代程序："
        "检查期后收付款、期末余额支持性证据、本期发生额原始凭证、往来对账或协议"
        "（见 K0-5 其他应收款替代程序 / K0-6 其他应付款替代程序），"
        "并评价所获证据是否足以替代函证。**不得虚构**未实际检查的证据类型。"
    ),
    # ─── K0-1 下区「四、审计结论」（源模板参考结论 A/B/C 在 B64:B66）───
    "k0-summary-conclusion": (
        "请生成 K0-1《函证结果汇总表》的审计结论。结合下区「一、函证情况」的发函金额占账面比例、"
        "回函确认金额占账面比例、回函和替代确认金额占账面比例三项覆盖率，"
        "以及不符事项与未回函替代程序的结果，对其他应收款/其他应付款的存在性、"
        "完整性、计价与权利义务作出结论。"
        "源模板参考结论三选一：A「未见异常。」/ B「除以下重大不符事项应当作为调整事项予以调整外，"
        "其余未见异常。」/ C「由于存在以下重大未调整事项（或审计范围受到限制无法获取充分、"
        "适当证据），不可确认。」——请据实选择并补充具体事项。**不得虚构**覆盖率数字与不符事项。"
    ),
}


@router.post("/api/workpapers/{wp_id}/k0/ai/{section}")
async def k0_ai_generate(
    wp_id: str,
    section: str,
    body: K0AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> K0AiGenerateResponse:
    if not getattr(settings, "WP_AI_SERVICE_ENABLED", True):
        raise HTTPException(503, "AI 服务未启用")
    if section not in _SUPPORTED_SECTIONS:
        raise HTTPException(400, f"不支持的 section: {section}。支持: {sorted(_SUPPORTED_SECTIONS)}")

    project_context = await _load_project_context(wp_id, db)
    user_prompt = _build_user_prompt(section, body.existingContent, body.relatedContext, project_context)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    result = await chat_completion(messages=messages, temperature=0.3, max_tokens=2000)
    if isinstance(result, str) and result.startswith("["):
        return K0AiGenerateResponse(content="", sources=[])
    return K0AiGenerateResponse(content=result, sources=[])


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
        logger.warning("K0 AI: project context 加载失败: %s", e)
    return ctx
