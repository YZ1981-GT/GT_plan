"""G6 其他债权投资(main组) — AI 辅助生成端点

POST /api/workpapers/{wp_id}/g6-main/ai/{section}

sections:
  - adjudication-analysis   (G6-1 审定表审计结论/变动分析)
  - disclosure-text          (附注披露文本生成)
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

router = APIRouter(tags=["g6-main-ai"])

# AI 生成超时（秒）
_AI_TIMEOUT = 30.0


class G6MainAiGenerateRequest(BaseModel):
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class G6MainAiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 G6《其他债权投资》的主组工作底稿。
科目1503其他债权投资（借方/资产类），以公允价值计量且其变动计入其他综合收益的金融资产（CAS22分类为FVOCI-Debt类）。

本组底稿核心关注其他债权投资的实质性审计程序：
- G6-1 审定表：77行8层多层结构(成本/利息调整/应计利息/小计/公允价值变动/减值/报表数/重分类)
- G6-2 明细表：33列3区段Tab(基础信息/期初+变动/期末+审定)
- G6-3 坏账准备明细表：20列2区段Tab，ECL公式链(③=①×②, ⑥=⑤×②A+①×(②A-②), ⑧=③+⑥)
- G6-4 调整分录汇总：AJE/RJE分录+借贷平衡

FVOCI-Debt（以公允价值计量且其变动计入其他综合收益）的特殊计量规则：
1. 摊余成本计量利息收入（同AC类债权投资G4，实际利率法）
2. 公允价值变动计入其他综合收益（OCI），处置时转入当期损益
3. 减值损失在利润表确认，但不减少账面金额（通过OCI调整）
4. 报表列示数=成本小计+公允价值变动-减值准备

审计逻辑链：完整性→估值→分类→存在性→减值→列报。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "adjudication-analysis": (
        "请生成G6-1审定表的审计结论和变动分析，评价以下方面：\n"
        "1. 其他债权投资各明细科目（成本/利息调整/应计利息）期初期末变动的合理性\n"
        "2. 小计公式（成本+利息调整+应计利息）的正确性\n"
        "3. 公允价值变动金额的确认依据（活跃市场报价/估值技术）\n"
        "4. 减值准备计提的充分性（ECL三阶段一致性）\n"
        "5. 报表列示数=小计+公允价值变动-减值 的正确性\n"
        "6. |变动率|>20%的科目重点变动原因分析\n"
        "7. 与试算表数据的一致性比对结论"
    ),
    "disclosure-text": (
        "请生成其他债权投资附注披露文本，需包含以下内容：\n"
        "1. 会计政策说明：FVOCI-Debt分类标准与计量方法\n"
        "2. 期初期末余额变动表：按投资种类分项列示\n"
        "3. 利息收入确认：实际利率法计算的利息收入\n"
        "4. 公允价值变动：计入其他综合收益的累计公允价值变动\n"
        "5. 减值准备：ECL三阶段分类及变动明细\n"
        "6. 重要项目说明：前五名持有情况（如适用）\n"
        "7. 限制性说明：质押或受限情况（如有）"
    ),
}

_SUPPORTED_SECTIONS = set(_SECTION_PROMPTS.keys())


@router.post("/api/workpapers/{wp_id}/g6-main/ai/{section}")
async def g6_main_ai_generate(
    wp_id: str,
    section: str,
    body: G6MainAiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> G6MainAiGenerateResponse:
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
        return G6MainAiGenerateResponse(content="", sources=[])
    return G6MainAiGenerateResponse(content=result, sources=[])


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
        logger.warning("G6 Main AI: project context 加载失败: %s", e)
    return ctx
