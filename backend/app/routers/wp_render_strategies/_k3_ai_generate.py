"""K3 其他应付款 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/k3/ai-generate

sections: large-amount-eval / long-outstanding-eval / related-party-eval / overall-opinion

科目 2241 其他应付款（贷方/负债类）。
核心认定：完整性（负债易少计）+ 反向截止测试。
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

router = APIRouter(tags=["k3-ai"])


class K3AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class K3AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "large-amount-eval",
    "long-outstanding-eval",
    "related-party-eval",
    "overall-opinion",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 K3《其他应付款》。
科目2241其他应付款（贷方/负债类）。

核心关注：
- **负债类方向**：期末 = 期初 + 贷方(增加) - 借方(减少)，与资产类相反！
- **完整性认定**为主（负债易少计风险）：反向截止测试（期后偿付倒查未入账负债）
- 大额其他应付款分析（占比/形成原因/偿付计划）
- 长期挂账检查（3年以上未偿付→评估是否转营业外收入）
- 关联方及交易检查（公允性/资金占用/披露完整性）
- 账龄分析（1年内/1-2年/2-3年/3年以上）

相关准则：CAS30财务报表列报（流动负债披露）、CAS36关联方披露。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "large-amount-eval": (
        "请生成K3-4大额其他应付款情况分析表的审计评价。对重要性水平以上的其他应付款逐笔分析"
        "形成原因、款项性质（保证金/暂收/代收/其他）、预计偿付时间、偿付能力评估。"
        "重点关注：是否存在到期未付情况、是否有资金占用嫌疑、"
        "大额款项增减变动的合理性、是否需要重分类为长期应付款。"
    ),
    "long-outstanding-eval": (
        "请生成K3-5长期挂账检查表的审计评价。分析长期挂账（3年以上）其他应付款的"
        "形成原因、债权人是否仍存续、偿付计划可行性、是否存在无法支付情形。"
        "评价是否需要转入营业外收入（确实无法支付的应付款项）、"
        "是否存在利用长期挂账应付款调节利润的风险、"
        "对完整性认定的影响（长期不付≠不存在义务）。"
    ),
    "related-party-eval": (
        "请生成K3-6关联方及交易检查表的审计评价。检查关联方往来款项的"
        "交易价格公允性、是否存在非经营性资金占用（控股股东/实际控制人）、"
        "披露完整性（CAS36要求）、是否存在利益输送或异常交易安排。"
        "重点关注：关联方余额占比、本期新增关联方往来的商业实质、"
        "期后回款/偿付情况验证。"
    ),
    "overall-opinion": (
        "请生成K3-1审定表底部的审计综合意见。综合评价其他应付款科目整体的"
        "完整性（是否存在少计负债，反向截止测试结论）、存在性（长期挂账真实性）、"
        "计价和分摊（金额准确性）、权利和义务、列报与披露的恰当性。"
        "说明是否发现需要调整的重大事项，审定数与未审数的主要差异原因，"
        "对报表层面影响的结论。强调负债类完整性认定的审计关注。"
    ),
}


@router.post("/api/workpapers/{wp_id}/k3/ai-generate")
async def k3_ai_generate(
    wp_id: str,
    body: K3AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> K3AiGenerateResponse:
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
        return K3AiGenerateResponse(content="", sources=[])
    return K3AiGenerateResponse(content=result, sources=[])


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
        logger.warning("K3 AI: project context 加载失败: %s", e)
    return ctx
