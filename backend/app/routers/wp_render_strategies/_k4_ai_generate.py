"""K4 其他流动负债 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/k4/ai-generate

sections: check-eval / detail-eval / overall-opinion

科目 2245 其他流动负债（贷方/负债类）。
核心认定：完整性（负债易少计）+ 分类正确性 + 流动性判断。
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

router = APIRouter(tags=["k4-ai"])


class K4AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class K4AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "check-eval",
    "detail-eval",
    "overall-opinion",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 K4《其他流动负债》。
科目2245其他流动负债（贷方/负债类）。

核心关注：
- **负债类方向**：期末 = 期初 + 贷方(增加) - 借方(减少)，与资产类相反！
- **完整性认定**为主（负债易少计风险）
- **分类正确性**：判断是否应归入其他流动负债（vs其他负债科目）
- **流动性判断**：一年内到期 vs 非流动重分类
- 明细项目逐项检查（分类/完整性/合规性）
- 三角勾稽验证（期末=期初+贷-借）

相关准则：CAS30财务报表列报（流动负债披露要求）。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "check-eval": (
        "请生成K4-4其他流动负债检查表的审计评价。逐项评价："
        "①分类正确性（该项目是否确实属于其他流动负债，而非其他应付款/预计负债/长期负债）"
        "②流动性判断（是否一年内到期/是否需重分类为非流动）"
        "③完整性（是否存在应计未计的其他流动负债，反向截止测试结论）"
        "④合规性（确认条件是否满足/计量是否准确/披露是否完整）。"
        "对存在'不合规'项的给出具体问题和后续程序建议。"
    ),
    "detail-eval": (
        "请生成K4-2其他流动负债明细表的审计分析评价。"
        "对各明细项目逐项分析：项目性质（预提费用/暂估/质量保证/其他）、"
        "期末余额合理性（与业务规模匹配度）、本期增减变动原因及合理性、"
        "与上年比较变动率异常分析。"
        "重点关注：是否有长期不变的项目（可能已不满足确认条件）、"
        "是否有金额异常偏大/偏小的项目、预提费用计提依据是否充分。"
    ),
    "overall-opinion": (
        "请生成K4-1审定表底部的审计综合意见。综合评价其他流动负债科目整体的"
        "完整性（是否存在少计负债）、存在性（各项目确认条件是否仍满足）、"
        "计价和分摊（金额计量准确性）、分类（流动vs非流动）、列报与披露的恰当性。"
        "说明是否发现需要调整的重大事项，审定数与未审数的主要差异原因，"
        "对报表层面影响的结论。强调负债类完整性认定的审计关注。"
    ),
}


@router.post("/api/workpapers/{wp_id}/k4/ai-generate")
async def k4_ai_generate(
    wp_id: str,
    body: K4AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> K4AiGenerateResponse:
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
        return K4AiGenerateResponse(content="", sources=[])
    return K4AiGenerateResponse(content=result, sources=[])


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
        logger.warning("K4 AI: project context 加载失败: %s", e)
    return ctx
