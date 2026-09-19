"""K7 递延收益 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/k7/ai-generate

sections: amort-conclusion / deferred-check-eval / overall-opinion

科目 2401 递延收益（贷方/负债类）。
核心认定：完整性（负债易少计）+ 政府补助分摊合理性（CAS16）+ 分摊去向正确性。
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

router = APIRouter(tags=["k7-ai"])


class K7AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class K7AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "amort-conclusion",
    "deferred-check-eval",
    "overall-opinion",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 K7《递延收益》。
科目2401递延收益（贷方/负债类）。

核心关注：
- **负债类方向**：期末 = 期初 + 收到(增加) - 分摊(减少)
- **政府补助分摊（CAS16）**：
  - 与资产相关：在相关资产使用寿命内按合理系统方法分期计入损益（直线法）
    本期分摊 = 补助总额 / 分摊期总期数 × 本期期数
  - 与收益相关：补偿以后期间费用 → 确认为递延收益，分期计入其他收益/营业外收入
    补偿已发生费用/损失 → 直接计入当期损益
  - 期末余额 = 补助总额 - 累计分摊
- **分摊去向**：其他收益(6117) / 营业外收入(6301)
- **完整性认定**：负债类易少计风险
- **存在性**：补助批文真实、资金实际到账
- **计价与分摊**：分摊方法/期限是否恰当，与资产使用寿命匹配

相关准则：CAS16政府补助、CAS30财务报表列报。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "amort-conclusion": (
        "请生成K7-4政府补助分摊测算表的分摊合理性结论。综合评价："
        "①各补助项目分摊方法的适当性（与资产相关→直线法按使用寿命；与收益相关→分期/一次性）"
        "②分摊期限与相关资产使用寿命/费用补偿期的匹配性"
        "③本期分摊金额测算=补助总额/分摊期总期数×本期期数 vs 企业实际分摊"
        "④测算差异分析（差异>重要性水平时说明原因及影响）"
        "⑤期末余额=补助总额-累计分摊 的验证结果"
        "⑥对递延收益期末余额公允性的整体评价"
        "确保符合CAS16政府补助第13-14条分摊要求。"
    ),
    "deferred-check-eval": (
        "请生成K7-5递延收益检查表的逐项评价。综合评价："
        "①补助真实性（批文、到账、对应项目真实存在）"
        "②批文合规性（政府文件号、审批程序、资金来源）"
        "③相关类型判断正确性（与资产/与收益，判断依据充分）"
        "④分摊方法适当性（是否与CAS16要求一致）"
        "⑤计入科目正确性（其他收益6117 vs 营业外收入6301 vs 冲减相关成本）"
        "⑥补助条件是否满足（是否存在退回风险）"
        "⑦关联方补助（是否存在非真实补助掩盖的关联交易）"
        "逐项给出合规/不合规判断及依据。"
    ),
    "overall-opinion": (
        "请生成K7-1审定表底部的审计综合意见。综合评价递延收益科目整体的"
        "完整性（是否存在少计递延收益/未确认政府补助）、存在性（补助真实性验证）、"
        "计价和分摊（分摊方法/期限是否恰当，测算差异是否在可接受范围）、分类（流动vs非流动）、"
        "列报与披露的恰当性（CAS16政府补助披露要求）。"
        "说明是否发现需要调整的重大事项，审定数与未审数的主要差异原因。"
        "重点评价：分摊合理性（与资产使用寿命/补偿期匹配）、分摊去向正确性"
        "（其他收益/营业外收入）、补助条件持续满足情况、退回风险评估。"
    ),
}


@router.post("/api/workpapers/{wp_id}/k7/ai-generate")
async def k7_ai_generate(
    wp_id: str,
    body: K7AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> K7AiGenerateResponse:
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
        return K7AiGenerateResponse(content="", sources=[])
    return K7AiGenerateResponse(content=result, sources=[])


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
        logger.warning("K7 AI: project context 加载失败: %s", e)
    return ctx
