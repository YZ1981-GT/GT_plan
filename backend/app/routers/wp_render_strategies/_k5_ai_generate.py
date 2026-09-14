"""K5 预计负债 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/k5/ai-generate

sections: litigation-eval / warranty-conclusion / decommission-conclusion / contingency-disclosure / overall-opinion

科目 2701 预计负债（贷方/负债类）。
核心认定：完整性（负债易少计）+ 或有事项三级判断 + 最佳估计数计量。
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

router = APIRouter(tags=["k5-ai"])


class K5AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class K5AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "litigation-eval",
    "warranty-conclusion",
    "decommission-conclusion",
    "contingency-disclosure",
    "overall-opinion",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 K5《预计负债》。
科目2701预计负债（贷方/负债类）。

核心关注：
- **负债类方向**：期末 = 期初 + 计提(增加) - 转销/冲回(减少)
- **或有事项三级可能性**（CAS13）：
  - 很可能(>50%) → 确认预计负债 + 计量最佳估计数
  - 可能(≤50%且非极小) → 不确认但披露为或有负债
  - 极小可能 → 不确认也不披露
- **最佳估计数计量**：单一最可能金额 / 区间中值(上限+下限)/2 / 期望值加权Σ(金额×概率)
- **时间价值重大时按现值折现**（弃置费用等）
- 产品质量保修：预计保修支出 = 销售收入 × 历史保修率
- 弃置费用：现值 = 未来支出 / (1+折现率)^年数
- 未决诉讼：律师函+败诉可能性+预计损失
- 完整性认定为主（负债易少计风险）

相关准则：CAS13或有事项、CAS30财务报表列报。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "litigation-eval": (
        "请生成K5-6未决诉讼检查表的诉讼评估结论。逐案评价："
        "①案件基本情况（原告/被告/涉案金额/诉讼阶段）"
        "②律师意见分析（胜诉/败诉可能性评估）"
        "③败诉可能性级别判断（很可能/可能/极小可能）"
        "④预计损失金额（基于可能性级别和计量方法）"
        "⑤是否需确认预计负债（很可能→确认；可能→披露；极小可能→不处理）"
        "⑥对审计意见的影响及后续程序建议。"
        "确保符合CAS13或有事项判断框架。"
    ),
    "warranty-conclusion": (
        "请生成K5-4产品质量保修检查表的审计结论。综合评价："
        "①历史保修率的合理性（与行业平均比较、趋势分析）"
        "②预计保修支出=销售收入×保修率的测算是否正确"
        "③期初/本期计提/本期使用/期末变动的合理性"
        "④与K5-1审定表产品质量保证行的交叉验证"
        "⑤保修准备是否充足（是否存在少计风险）"
        "⑥产品召回、重大质量事故等特殊事项。"
    ),
    "decommission-conclusion": (
        "请生成K5-5弃置费用检查表的审计结论。综合评价："
        "①弃置义务确认条件（法定义务/合同义务/推定义务）"
        "②预计弃置支出金额的估计依据"
        "③折现率选择的合理性（无风险利率+风险溢价）"
        "④现值计算=预计支出/(1+折现率)^年数 是否正确"
        "⑤本期利息调整=期初现值×折现率 是否正确"
        "⑥与K5-1审定表弃置义务行的交叉验证"
        "⑦假设变更（支出估计/时间/利率）对预计负债的敏感性。"
    ),
    "contingency-disclosure": (
        "请生成预计负债附注中或有事项的披露段落。"
        "按CAS13要求披露：①或有负债（可能级别，已识别但未确认的）"
        "②或有资产（如有）③预计负债变动明细"
        "④未决诉讼概况（在不影响诉讼的前提下）"
        "⑤产品质量保修义务说明"
        "⑥弃置费用义务说明"
        "⑦环境恢复义务等特殊或有事项。"
        "注意：不应披露可能损害企业利益的信息（如败诉预期金额）。"
    ),
    "overall-opinion": (
        "请生成K5-1审定表底部的审计综合意见。综合评价预计负债科目整体的"
        "完整性（是否存在少计预计负债）、存在性（确认条件是否仍满足）、"
        "计价和分摊（最佳估计数计量方法是否恰当）、分类（流动vs非流动）、"
        "列报与披露的恰当性（CAS13或有事项披露）。"
        "说明是否发现需要调整的重大事项，审定数与未审数的主要差异原因。"
        "重点评价：或有事项三级判断的合理性、最佳估计数计量的充分性、"
        "律师函证据的支持力度、产品质保/弃置费用测算的准确性。"
    ),
}


@router.post("/api/workpapers/{wp_id}/k5/ai-generate")
async def k5_ai_generate(
    wp_id: str,
    body: K5AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> K5AiGenerateResponse:
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
        return K5AiGenerateResponse(content="", sources=[])
    return K5AiGenerateResponse(content=result, sources=[])


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
        logger.warning("K5 AI: project context 加载失败: %s", e)
    return ctx
