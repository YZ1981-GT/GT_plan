"""H0 固定资产循环函证 — AI 辅助生成端点.

POST /api/workpapers/{wp_id}/h0/ai-generate

sections:
- alternative-audit-note       → H0-5 替代程序审计说明
- alternative-audit-conclusion   → H0-5 替代程序审计结论
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

router = APIRouter(tags=["h0-ai"])


class H0AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class H0AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "alternative-audit-note",
    "alternative-audit-conclusion",
    # ── H0-1 下区「三、审计说明」5 小节 + 「四、审计结论」 ──
    # 前端真源 = `h0SummaryLowerZone.ts` 的 `H0_AUDIT_NOTE_SECTIONS[].aiSection`
    # spec: h0-confirmation-source-fidelity-and-linkage R2.7 / R2.9
    "summary-control",
    "summary-error-analysis",
    "summary-reliability",
    "summary-mismatch",
    "summary-alternative",
    "summary-conclusion",
}

# 🔴 铁律：prompt 过短会诱导模型自造披露内容。每条 ≥20 字 + 写明源模板口径 + 「不得虚构」。
_NO_FABRICATION = "只依据底稿已有数据与源模板口径撰写，不得虚构金额、单位名称或未执行的程序。"

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 H0《固定资产循环函证》。
科目覆盖：固定资产、在建工程、使用权资产相关购置与权属。
核心关注：未回函被函证单位的替代程序（期后验收/权属证据、期末余额支持性证据、
本期新增资产检查、抵押担保/融资租赁证据）；权属证书与账面记录核对；
新增资产请购审批、到货验收、转固手续完整性；与 H1/L1/L3 抵质押信息交叉核对。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "alternative-audit-note": (
        "请生成 H0-5 固定资产循环替代程序检查表的审计说明，描述对未回函被函证单位执行的替代程序范围、"
        "抽样方法、检查证据类型（验收单/权属证书/采购合同/发票/付款凭证/转固手续/抵押融资租赁合同等），"
        "以及权属证据比例、验收证据比例的计算依据。"
    ),
    "alternative-audit-conclusion": (
        "请生成 H0-5 固定资产循环替代程序检查表的审计结论，评价替代程序所获取证据的充分适当性，"
        "对固定资产的存在性、权属、计价与完整性作出结论。"
    ),
    # ── H0-1 下区（源模板 `函证结果汇总表H0-1` S29/W29/S33/S34/S37/C39） ──
    "summary-control": (
        "请生成 H0-1 函证结果汇总表「1、对询证函保持的控制的说明」（源模板 S29）。"
        "说明注册会计师如何全程控制询证函：亲自设计与寄发、直接接收回函、留存寄送单回执与快递物流信息、"
        "跟函时观察实地场所与核对过程、确认处理函证人员身份与权限，以防范询证函被拦截、篡改或串通舞弊。"
        + _NO_FABRICATION
    ),
    "summary-error-analysis": (
        "请生成 H0-1 函证结果汇总表「2、对误差的分析」（源模板 W29）。"
        "依据源模板给定的误差构成条件（不符事项金额高于或低于账户余额约定阈值，且被审计单位不能合理解释差异并提供依据），"
        "分析已识别不符事项的性质、金额、成因，判断是否构成错报并说明是否推断至总体。"
        + _NO_FABRICATION
    ),
    "summary-reliability": (
        "请生成 H0-1 函证结果汇总表「3、对以传真或电子邮件形式收到的回函的可靠性的考虑」（源模板 S33，对应底稿 H0-6）。"
        "说明对回函者身份的确认方式、回函邮箱/传真号的验证过程、是否致电被询证者确认、"
        "是否要求在审计报告日前寄回原件，以及据此得出的可靠性结论。"
        + _NO_FABRICATION
    ),
    "summary-mismatch": (
        "请生成 H0-1 函证结果汇总表「4、针对不符事项的程序」（源模板 S34）。"
        "说明对回函不符事项查明原因所执行的程序、取得的支持性证据、是否已在 H0-4 差异核对表逐项调节、"
        "以及是否存在舞弊迹象需记录至 H0-7。若回函中含未函证的其他信息，应说明其影响与进一步程序。"
        + _NO_FABRICATION
    ),
    "summary-alternative": (
        "请生成 H0-1 函证结果汇总表「5、针对未回函的替代程序」（源模板 S37）。"
        "说明对未回函项目执行的替代程序（检查交易发生的记账凭证与支持性证据、检查资产负债表日后会计处理等，见 H0-5）、"
        "覆盖金额与比例，以及替代程序是否已取得充分适当的审计证据。"
        + _NO_FABRICATION
    ),
    "summary-conclusion": (
        "请生成 H0-1 函证结果汇总表「四、审计结论」（源模板 C39）。"
        "参照源模板三种参考结论择一表述：A 未见异常；"
        "B 除以下重大不符事项应当作为调整事项予以调整外，其余未见异常；"
        "C 由于存在以下重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认。"
        "结论须与函证覆盖率、不符事项处理结果、替代程序结论一致。"
        + _NO_FABRICATION
    ),
}


@router.post("/api/workpapers/{wp_id}/h0/ai-generate")
async def h0_ai_generate(
    wp_id: str,
    body: H0AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> H0AiGenerateResponse:
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
        return H0AiGenerateResponse(content="", sources=[])
    return H0AiGenerateResponse(content=result, sources=[])


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
        logger.warning("H0 AI: project context 加载失败: %s", e)
    return ctx
