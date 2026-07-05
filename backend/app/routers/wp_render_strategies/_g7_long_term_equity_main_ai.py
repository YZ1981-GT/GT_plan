"""G7 长期股权投资(main组) — AI 辅助生成端点

POST /api/workpapers/{wp_id}/g7-main/ai/{section}

sections:
  - adjudication-analysis   (G7-1 审定表变动分析，关注|变动率|>20%的项目)
  - disclosure-text          (根据审定数据和控制类型，生成长期股权投资相关附注披露文本)
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

router = APIRouter(tags=["g7-main-ai"])

# AI 生成超时（秒）
_AI_TIMEOUT = 30.0


class G7MainAiGenerateRequest(BaseModel):
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class G7MainAiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 G7《长期股权投资》的主组工作底稿。
科目1511长期股权投资（借方/资产类），G循环中合并会计最复杂的科目。

本组底稿核心关注长期股权投资的实质性审计程序：
- G7-1 审定表：97行按控制类型分5组（子公司成本法/合营权益法/联营权益法/合计/减值）+净值行
- G7-2 明细表：103行×54列→5区段Tab（基础信息/期初余额/本期变动/期末+减值/权益法详情）
- G7-3 调整分录汇总：AJE/RJE分录+借贷平衡
- 附注披露(上市253行/国企355行)

长期股权投资按控制类型决定后续计量方法：
1. 子公司投资：成本法（个别报表），仅在宣告分配现金股利时确认投资收益
2. 合营企业投资：权益法，按持股比例确认被投资单位净利润/OCI/其他权益变动
3. 联营企业投资：权益法，同合营企业

借方科目公式：期末未审 = 期初审定 + 借方发生额 - 贷方发生额
审定公式：审定数 = 未审数 + AJE + RJE
净值公式：净值 = 投资合计 - 减值准备

审计逻辑链：完整性→估值（成本法/权益法计量）→分类（控制类型判断）→存在性→减值→列报。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "adjudication-analysis": (
        "请分析G7-1审定表变动，关注|变动率|>20%的项目，给出审计分析意见。评价以下方面：\n"
        "1. 按控制类型（子公司/合营/联营）分组的期初期末变动合理性\n"
        "2. 子公司投资（成本法）：新增投资/处置/减值的商业实质\n"
        "3. 合营/联营投资（权益法）：权益法调整金额与被投资单位净利润的匹配性\n"
        "4. |变动率|>20%的项目重点变动原因分析及风险因素识别\n"
        "5. 投资合计与减值准备的充分性评价\n"
        "6. 净值（=合计-减值）与试算表数据(科目1511)的一致性比对\n"
        "7. 控制类型变更（如联营升级为子公司）的会计处理合规性"
    ),
    "disclosure-text": (
        "请根据审定数据和控制类型，生成长期股权投资相关附注披露文本，需包含以下内容：\n"
        "1. 会计政策说明：成本法与权益法的适用条件及计量规则\n"
        "2. 按控制类型分类汇总：子公司(成本法)/合营(权益法)/联营(权益法)期末余额\n"
        "3. 本期变动情况：新增投资/处置/权益法调整/减值计提明细\n"
        "4. 重要子公司/合营/联营企业基本信息：名称、持股比例、主营业务\n"
        "5. 权益法核算的投资收益：按被投资单位净利润×持股比例确认情况\n"
        "6. 减值准备变动：期初/计提/转回/期末及可收回金额测试方法\n"
        "7. 限制性说明：质押/冻结/受限情况（如有）\n"
        "8. 持股5%以上的被投资单位详细信息（如适用）"
    ),
}

_SUPPORTED_SECTIONS = set(_SECTION_PROMPTS.keys())


@router.post("/api/workpapers/{wp_id}/g7-main/ai/{section}")
async def g7_main_ai_generate(
    wp_id: str,
    section: str,
    body: G7MainAiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> G7MainAiGenerateResponse:
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
        return G7MainAiGenerateResponse(content="", sources=[])
    return G7MainAiGenerateResponse(content=result, sources=[])


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
        logger.warning("G7 Main AI: project context 加载失败: %s", e)
    return ctx
