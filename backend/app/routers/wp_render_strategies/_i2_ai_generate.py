"""I2 开发支出 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/i2/ai-generate

sections: cas6-suggestion / analysis-anomaly / disclosure / audit-conclusion
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

router = APIRouter(tags=["i2-ai"])


class I2AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class I2AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "cas6-suggestion",
    "analysis-anomaly",
    "disclosure",
    "audit-conclusion",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 I2《开发支出》。
科目1704开发支出（借方/资产类）。
核心关注：CAS6无形资产准则第9条资本化五条件（技术可行性/完成意图/使用或出售能力/未来经济利益/资源充足）、
资本化时点判断、研究vs开发阶段划分、I6↔I2双向联动（费用化+资本化=研发总额）、
资本化完成→I1无形资产转入联动、4类检查表（材料/人员/工时/委外）、截止性测试。

CAS6第9条：企业内部研究开发项目开发阶段的支出，同时满足下列条件的，才能确认为无形资产：
（一）完成该无形资产以使其能够使用或出售在技术上具有可行性；
（二）具有完成该无形资产并使用或出售的意图；
（三）无形资产产生经济利益的方式，包括能够证明运用该无形资产生产的产品存在市场或无形资产自身存在市场，
     无形资产将在内部使用的，应当证明其有用性；
（四）有足够的技术、财务资源和其他资源支持，以完成该无形资产的开发，并有能力使用或出售该无形资产；
（五）归属于该无形资产开发阶段的支出能够可靠地计量。

资产类公式：期末=期初+借方-贷方（科目1704）。
三角勾稽：期末=期初+增加(资本化)-减少(转无形+转费用)。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "cas6-suggestion": (
        "请根据提供的研发项目信息，逐条评估CAS6第9条资本化五条件：\n"
        "① 技术可行性：项目是否已通过技术论证/小试/中试等阶段\n"
        "② 完成意图：管理层是否有明确的开发完成和商业化计划\n"
        "③ 使用或出售能力：是否存在目标市场或内部使用场景\n"
        "④ 未来经济利益：预期经济利益的实现路径和可能性\n"
        "⑤ 资源充足：技术团队/财务资源/设备条件是否满足\n\n"
        "对每一条件给出建议判断（满足/不满足/需进一步核实）及支撑理由。"
    ),
    "analysis-anomaly": (
        "请分析开发支出实质性分析中的异常波动原因，关注：\n"
        "1) 各研发项目开发支出的同比变动率是否合理\n"
        "2) 变动异常的项目是否有合理的业务解释\n"
        "3) 差异超过重要性水平的项目需特别说明\n"
        "4) 新增/终止研发项目对总额的影响\n"
        "5) 费用化与资本化比例的变动趋势是否合理\n"
        "6) 是否存在可能的操纵资本化时点的迹象"
    ),
    "disclosure": (
        "请生成开发支出附注披露的文字描述部分，包括：\n"
        "1) 研究开发支出的确认和计量政策\n"
        "2) 研究阶段与开发阶段的划分标准\n"
        "3) 资本化条件的具体判断标准\n"
        "4) 本期研发投入总额及费用化/资本化构成\n"
        "5) 主要研发项目概况及进展\n"
        "6) 期末开发支出余额构成\n"
        "7) 本期转入无形资产的项目明细"
    ),
    "audit-conclusion": (
        "请生成I2开发支出审定表的审计结论，评价以下方面：\n"
        "1) 开发支出科目整体的完整性、存在性和计价准确性\n"
        "2) CAS6资本化条件的判断是否恰当\n"
        "3) 资本化时点的确定是否准确\n"
        "4) 三角勾稽校验是否通过\n"
        "5) 费用化+资本化=研发总额校验（VR-I6-01）\n"
        "6) 转入无形资产金额与I1增加检查表是否一致\n"
        "7) 是否发现需要调整的重大事项"
    ),
}


@router.post("/api/workpapers/{wp_id}/i2/ai-generate")
async def i2_ai_generate(
    wp_id: str,
    body: I2AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> I2AiGenerateResponse:
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
        return I2AiGenerateResponse(content="", sources=[])
    return I2AiGenerateResponse(content=result, sources=[])


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
        logger.warning("I2 AI: project context 加载失败: %s", e)
    return ctx
