"""I5 其他非流动资产 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/i5/ai-generate

sections: adjudication / note / conclusion / detail /
          i5-disclosure-listed-* / i5-disclosure-soe-* /
          classification / maturity / recoverability
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

router = APIRouter(tags=["i5-ai"])


class I5AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class I5AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "adjudication",
    "note",
    "conclusion",
    "detail",
    "i5-disclosure-listed",
    "i5-disclosure-soe",
    "classification",
    "maturity",
    "recoverability",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 I5《其他非流动资产》。
其他非流动资产（借方/资产类）。注意：本项无标准科目映射，金额需按客户实际明细科目编制。

其他非流动资产核心规则：
1. 期末余额=期初+增加-减少（标准资产类三角勾稽）
2. 审定数=未审数+AJE+RJE
3. 常见项目类型：预付工程款、预付设备款、合同资产（非流动）、待抵扣进项税、预缴所得税（超1年）
4. 分类正确性：区分流动/非流动资产（预计1年内变现/收回→归入流动资产）
5. 期限适当性：定期复核是否仍满足非流动条件
6. 可回收性评估：关注长期未结转项目的减值迹象

适用准则：CAS30财务报表列报（流动/非流动分类）、CAS8资产减值。
输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "adjudication": (
        "请生成I5其他非流动资产审定表的审计说明，分析其他非流动资产的变动情况。"
        "需涵盖：期初到期末的变动分析（增加/减少的构成及原因）、"
        "三角勾稽验证（期末=期初+增加-减少）、"
        "未审数与审定数的差异说明（有无调整事项）、"
        "与明细表合计的核对结果。"
    ),
    "note": (
        "请生成I5其他非流动资产审定表的审计说明备注，补充以下信息：\n"
        "1) 各明细项目的业务背景简述\n"
        "2) 大额变动项目的具体原因\n"
        "3) 与其他科目/底稿的勾稽关系\n"
        "4) 需关注的后续事项或风险提示"
    ),
    "conclusion": (
        "请生成I5其他非流动资产审定表的审计结论，评价：\n"
        "1) 存在性（各项目是否真实存在、是否有合同/凭证支持）\n"
        "2) 完整性（是否所有应记录的其他非流动资产均已入账）\n"
        "3) 计价准确性（期末余额是否正确、有无减值迹象）\n"
        "4) 分类恰当性（流动/非流动划分是否正确）\n"
        "说明审定数与试算平衡表是否一致、是否存在需调整事项。"
    ),
    "detail": (
        "请生成I5其他非流动资产明细表的分析说明，关注：\n"
        "1) 各项目金额的合理性（与业务规模匹配）\n"
        "2) 长期挂账项目（超过预期结转期限）的回收风险\n"
        "3) 本期新增大额项目的业务实质\n"
        "4) 本期减少项目的结转去向（转入固定资产/费用/退回等）\n"
        "5) 明细合计与审定表的勾稽一致性"
    ),
    "i5-disclosure-listed": (
        "请生成其他非流动资产附注披露（上市公司版本），包括：\n"
        "1) 其他非流动资产的确认和计量政策\n"
        "2) 各类别明细及期初/期末余额\n"
        "3) 本期增减变动情况\n"
        "4) 受限资产情况（如有抵押/质押）\n"
        "5) 与关联方相关的其他非流动资产（如有）"
    ),
    "i5-disclosure-soe": (
        "请生成其他非流动资产附注披露（国有企业版本），包括：\n"
        "1) 其他非流动资产的确认和计量政策\n"
        "2) 各类别明细及期初/期末余额\n"
        "3) 本期增减变动情况\n"
        "4) 受限资产说明\n"
        "5) 国有资产特殊监管要求（如适用）"
    ),
    "classification": (
        "请生成I5其他非流动资产分类正确性检查意见：\n"
        "1) 各项目是否满足非流动资产定义（预计持有超过1年）\n"
        "2) 是否存在应重分类为流动资产的项目\n"
        "3) 是否存在应归入其他科目的项目（如预付账款/其他应收款）\n"
        "4) 合同资产非流动部分的划分依据是否充分\n"
        "5) 分类依据（合同条款/管理层意图）是否有书面证据"
    ),
    "maturity": (
        "请生成I5其他非流动资产期限适当性检查意见：\n"
        "1) 各项目预计收回/结转时间是否仍超过1年\n"
        "2) 长期挂账项目（>2年）是否需重新评估分类\n"
        "3) 是否存在即将到期（<12个月）应转为流动资产的项目\n"
        "4) 预计时点判断的依据（合同约定/工程进度/政策文件）"
    ),
    "recoverability": (
        "请生成I5其他非流动资产可回收性评估意见：\n"
        "1) 是否存在减值迹象（对方经营困难/项目搁置/政策变化等）\n"
        "2) 长期未结转项目的回收可能性评估\n"
        "3) 是否需计提减值准备\n"
        "4) 管理层对可回收性的说明是否合理\n"
        "5) 后续期间收回情况（截至审计报告日的回款证据）"
    ),
}


def _match_section(section: str) -> str | None:
    """支持通配符匹配 i5-disclosure-listed-* / i5-disclosure-soe-*"""
    if section in _SUPPORTED_SECTIONS:
        return section
    if section.startswith("i5-disclosure-listed"):
        return "i5-disclosure-listed"
    if section.startswith("i5-disclosure-soe"):
        return "i5-disclosure-soe"
    return None


@router.post("/api/workpapers/{wp_id}/i5/ai-generate")
async def i5_ai_generate(
    wp_id: str,
    body: I5AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> I5AiGenerateResponse:
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
        return I5AiGenerateResponse(content="", sources=[])
    return I5AiGenerateResponse(content=result, sources=[])


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
        logger.warning("I5 AI: project context 加载失败: %s", e)
    return ctx
