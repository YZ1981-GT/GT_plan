"""I6 研发费用 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/i6/ai-generate

sections: adjudication / detail / targeted /
          i6-disclosure-listed-* / i6-disclosure-soe-*

损益类底稿AI辅助要点：
- 审计说明需强调"发生额"非"余额"
- 月度波动分析（识别异常月份）
- I6↔I2联动校验（费用化+资本化=研发总额）
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

router = APIRouter(tags=["i6-ai"])


class I6AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class I6AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "adjudication",
    "detail",
    "targeted",
    "i6-disclosure-listed",
    "i6-disclosure-soe",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 I6《研发费用》。
科目6602研发费用（**损益类/借方科目**）。

研发费用核心规则：
1. **损益类取发生额！**非期末余额。借方=费用增加，贷方=费用冲回/结转
2. 净发生额=借方发生-贷方发生（正数=净费用）
3. 审定数=未审数+AJE+RJE
4. VR-I6-01：研发费用化(I6)+研发资本化(I2)=研发总额（核心校验）
5. 月度波动>±30%需重点关注
6. 费用归集完整性（研发人员工资/材料/折旧/试验费等）

适用准则：CAS6无形资产（研发阶段划分）、CAS30财务报表列报。
输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "adjudication": (
        "请生成I6研发费用审定表的审计说明和结论，分析科目6602的变动情况。"
        "需涵盖：\n"
        "1) 本期发生额分析（借方发生/贷方发生/净发生额）\n"
        "2) 未审数与审定数的差异说明（AJE/RJE影响）\n"
        "3) 与上期同期比较（变动率及原因）\n"
        "4) 费用化与资本化划分的合理性（VR-I6-01校验）\n"
        "5) 与明细表月度合计的一致性核对\n"
        "6) 总体审计结论（是否存在重大错报）"
    ),
    "detail": (
        "请生成I6研发费用月度波动分析，关注：\n"
        "1) 各月发生额趋势（是否平稳/季节性/异常跳变）\n"
        "2) 异常月份（变动率>±30%）的可能原因（项目里程碑/人员变动/大额采购等）\n"
        "3) 费用类别构成分析（人工/材料/折旧/试验/其他）\n"
        "4) 与业务计划/预算的匹配程度\n"
        "5) 需进一步实施的审计程序建议"
    ),
    "targeted": (
        "请生成I6研发费用针对性检查意见，逐项评价：\n"
        "1) 费用归集完整性：研发活动相关支出是否全部归集到6602\n"
        "2) 人员费用分摊合理性：研发人员工时分配是否有据可依\n"
        "3) 与I2(开发支出)划分一致性：费用化/资本化界限是否清晰\n"
        "4) 费用真实性：大额支出是否有合同/发票/验收单支持\n"
        "5) 研发加计扣除合规性：享受税收优惠的项目是否符合条件"
    ),
    "i6-disclosure-listed": (
        "请生成研发费用附注披露（上市公司版本），包括：\n"
        "1) 研发费用的确认和计量政策（CAS6研发阶段划分标准）\n"
        "2) 本期研发费用发生额明细（按费用性质分类）\n"
        "3) 研发费用化与资本化金额（联动I2开发支出）\n"
        "4) 研发投入占营业收入比例\n"
        "5) 主要研发项目概况及进展\n"
        "6) 政府补助/税收优惠相关披露"
    ),
    "i6-disclosure-soe": (
        "请生成研发费用附注披露（国有企业版本），包括：\n"
        "1) 研发费用确认和计量政策\n"
        "2) 本期研发费用发生额明细\n"
        "3) 费用化/资本化金额\n"
        "4) 研发投入强度（占收入比）\n"
        "5) 国企科技创新考核指标达成情况（如适用）"
    ),
}


def _match_section(section: str) -> str | None:
    """支持通配符匹配 i6-disclosure-listed-* / i6-disclosure-soe-*"""
    if section in _SUPPORTED_SECTIONS:
        return section
    if section.startswith("i6-disclosure-listed"):
        return "i6-disclosure-listed"
    if section.startswith("i6-disclosure-soe"):
        return "i6-disclosure-soe"
    return None


@router.post("/api/workpapers/{wp_id}/i6/ai-generate")
async def i6_ai_generate(
    wp_id: str,
    body: I6AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> I6AiGenerateResponse:
    if not getattr(settings, "WP_AI_SERVICE_ENABLED", True):
        raise HTTPException(503, "AI 服务未启用")

    matched = _match_section(body.section)
    if matched is None:
        raise HTTPException(400, f"不支持的 section: {body.section}。支持: {sorted(_SUPPORTED_SECTIONS)}")

    project_context = await _load_project_context(wp_id, db)
    user_prompt = _build_user_prompt(matched, body.existingContent, body.relatedContext, project_context)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    result = await chat_completion(messages=messages, temperature=0.3, max_tokens=2000)
    if isinstance(result, str) and result.startswith("["):
        return I6AiGenerateResponse(content="", sources=[])
    return I6AiGenerateResponse(content=result, sources=[])


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
    except Exception as e:  # noqa: BLE001
        logger.warning("I6 AI: project context 加载失败: %s", e)
    return ctx
