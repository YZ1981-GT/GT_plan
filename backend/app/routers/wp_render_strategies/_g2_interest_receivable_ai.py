"""G2 应收利息 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/g2/ai/{section}

sections: interest-calc-conclusion / ecl-conclusion / overdue-evaluation /
          voucher-check-conclusion / overall-opinion
"""

from __future__ import annotations

import asyncio
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

router = APIRouter(tags=["g2-ai"])

# AI 生成超时（秒）
_AI_TIMEOUT = 30.0


class G2AiGenerateRequest(BaseModel):
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class G2AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 G2《应收利息》。
科目1132应收利息（借方/资产类）。
核心关注：利息测算准确性（面值×票面利率×计息天数/365）、ECL三阶段减值充分性
（Stage1: 12个月PD / Stage2: 整个存续期PD / Stage3: 已发生减值）、
长期未收回风险评估（逾期>180天→Stage3 / >90天→Stage2）、
凭证检查（利息确认与收回的真实性和完整性）。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "adjudication-note": (
        "请生成G2-1审定表的审计说明，概述对应收利息（1132）期初/期末审定程序、"
        "与试算平衡表勾稽情况、拟调整事项及影响。"
    ),
    "adjudication-conclusion": (
        "请生成G2-1审定表的审计结论，按A/B/C口径评价科目1132审定数与试算勾稽结果。"
    ),
    "detail-note": (
        "请生成G2-2明细表的审计说明，概述逐笔计息基础核对、应计利息测算"
        "（面值×利率×天数/365）、与账面差异及减值阶段关注事项。"
    ),
    "detail-conclusion": (
        "请生成G2-2明细表的审计结论，按A/B/C口径评价明细完整性与计息准确性。"
    ),
    "bad-debt-note": (
        "请生成G2-3坏账准备明细的审计说明，概述ECL阶段划分、PD/LGD参数、"
        "测算与企业计提差异及阶段转移情况。"
    ),
    "bad-debt-conclusion": (
        "请生成G2-3坏账准备明细的审计结论，按A/B/C口径评价减值计提充分性。"
    ),
    "adjustment-note": (
        "请生成G2-4调整分录汇总的审计说明，概述与应收利息（1132）相关的账项/报表调整依据、"
        "借贷平衡情况、与调整分录模块勾稽及对审定表的影响。"
    ),
    "adjustment-conclusion": (
        "请生成G2-4调整分录汇总的审计结论，按A/B/C口径评价调整分录是否恰当、完整、借贷平衡。"
    ),
    "interest-calc-note": (
        "请生成G2-5利息测算表的审计说明，概述独立测算程序、与企业计提差异及原因分析。"
    ),
    "interest-calc-conclusion": (
        "请生成G2-5利息测算表的审计结论，评价各投资标的应收利息测算结果"
        "（面值×票面利率×计息天数/365），与企业计提利息的差异及其合理性。"
    ),
    "overdue-note": (
        "请生成G2-6长期未收回检查的审计说明，概述逾期识别程序、可收回性评估"
        "及阶段迁移建议依据。"
    ),
    "overdue-evaluation": (
        "请生成G2-6长期未收回检查的审计评价，分析逾期应收利息的回收风险、"
        "债务人信用状况、催收有效性，以及阶段转移建议"
        "（逾期>180天→Stage3、>90天→Stage2）的合理性。"
    ),
    "ecl-note": (
        "请生成G2-7坏账准备测算的审计说明，概述独立ECL测算方法、参数选取"
        "及与企业计提差异分析。"
    ),
    "ecl-conclusion": (
        "请生成G2-7坏账准备测算的审计结论，评价ECL三阶段划分"
        "（Stage1/2/3）的适当性、PD/LGD参数选取的合理性、"
        "ECL=EAD×PD×LGD测算结果与企业计提的差异及减值充分性。"
    ),
    "voucher-note": (
        "请生成G2-8凭证检查表的审计说明，概述借方利息确认/贷方利息收回抽凭程序、"
        "差异及逾期收回关注事项。"
    ),
    "voucher-check-conclusion": (
        "请生成G2-8凭证检查表的审计结论，评价抽查凭证（借方利息确认/贷方利息收回）"
        "的真实性、完整性及账务处理的正确性，包括测算利息与实际入账差异。"
    ),
    "disclosure-listed-note": (
        "请生成G2上市公司附注披露说明初稿，按投资类型列示应收利息期初/期末余额，"
        "并与审定数勾稽。"
    ),
    "disclosure-soe-note": (
        "请生成G2国企附注披露说明初稿，简要列示应收利息期初/期末余额及主要构成，"
        "并与审定数勾稽。"
    ),
    "overall-opinion": (
        "请生成G2应收利息的整体审计意见，综合利息测算准确性、ECL减值充分性、"
        "长期未收回风险、凭证核对结果各方面，形成对科目1132列报与披露的总体结论。"
    ),
}

_SUPPORTED_SECTIONS = set(_SECTION_PROMPTS.keys())


@router.post("/api/workpapers/{wp_id}/g2/ai/{section}")
async def g2_ai_generate(
    wp_id: str,
    section: str,
    body: G2AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> G2AiGenerateResponse:
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
    try:
        result = await asyncio.wait_for(
            chat_completion(messages=messages, temperature=0.3, max_tokens=2000),
            timeout=_AI_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise HTTPException(504, "AI 生成超时（30秒），请重试")
    if isinstance(result, str) and result.startswith("["):
        return G2AiGenerateResponse(content="", sources=[])
    return G2AiGenerateResponse(content=result, sources=[])


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
    except Exception as e:  # noqa: BLE001
        logger.warning("G2 AI: project context 加载失败: %s", e)
    return ctx
