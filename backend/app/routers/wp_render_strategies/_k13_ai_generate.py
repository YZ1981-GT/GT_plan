"""K13 营业外支出 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/k13/ai-generate

sections: non-operating-eval / overall-opinion

损益类底稿AI辅助要点：
- 营业外支出分类评价（按去向分析+税前扣除性评价）
- 总体审计意见

科目6711营业外支出（损益类/借方科目！取发生额非余额）
营业外支出 = 与日常活动无关的损失（非流动资产处置损失/捐赠支出/罚款滞纳金/债务重组损失/资产盘亏损失等）

Requirements: 6.1
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

router = APIRouter(tags=["k13-ai"])


class K13AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class K13AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "non-operating-eval",
    "overall-opinion",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 K13《营业外支出》。
科目6711营业外支出（**损益类/借方科目**）。

营业外支出核心规则：
1. **损益类取发生额！**非期末余额。借方=支出增加，贷方=支出冲回/红冲
2. 净发生额=借方发生-贷方发生（正数=净支出）
3. 审定数=未审数+AJE+RJE
4. 营业外支出的本质：与日常活动无关的损失
5. 分类判断核心：与日常活动无关→营业外支出(6711/K13)；与日常活动相关→营业外成本/其他
6. 营业外支出按去向分类：
   - 非流动资产毁损报废损失（固定资产/无形资产处置净损失）
   - 捐赠支出（对外捐赠，需关注公益性捐赠税前扣除限额）
   - 罚款滞纳金（行政罚款/税收滞纳金/违约金）
   - 债务重组损失
   - 资产盘亏损失（存货/固定资产盘亏净损失）
   - 其他（确实无法归入以上类别的损失）
7. 税前扣除性是K13核心审计关注点：
   - 公益性捐赠：年度利润总额12%以内可扣除，超出部分3年结转
   - 行政罚款/税收滞纳金：不可税前扣除
   - 违约金/赔偿金：凭合法凭证可扣除
   - 资产损失：需专项申报/清单申报后方可扣除
   - 债务重组损失：符合条件可扣除
8. 偶发性/非经常性损益分析：营业外支出应为偶发性，持续性支出需关注分类正确性

适用准则：CAS12债务重组、CAS30财务报表列报、企业所得税法第十条。
输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "non-operating-eval": (
        "请生成K13营业外支出分类评价，分析科目6711各去向的分类正确性及税前扣除性。"
        "需涵盖：\n"
        "1) 营业外支出去向构成分析\n"
        "   - 非流动资产毁损报废损失：资产类别/处置方式/净损失金额/审批\n"
        "   - 捐赠支出：捐赠对象/金额/公益性捐赠票据/税前扣除额度计算\n"
        "   - 罚款滞纳金：处罚主体/金额/是否行政罚款(不可扣除)\n"
        "   - 债务重组损失：交易对手/重组方案/损失确认时点\n"
        "   - 资产盘亏损失：盘亏资产类别/金额/原因/审批手续\n"
        "   - 其他\n"
        "2) 分类正确性评价\n"
        "   - 各项支出是否确属「与日常活动无关」（核心判断）\n"
        "   - 是否存在应计入管理费用/销售费用却误入营业外支出的项目\n"
        "   - 资产处置损失分类：处置vs报废vs盘亏的界定\n"
        "3) 税前扣除性评价（K13核心关注）\n"
        "   - 各项支出的税前扣除性判断\n"
        "   - 公益性捐赠扣除限额计算（利润总额×12%）\n"
        "   - 行政罚款/税收滞纳金永久性差异确认\n"
        "   - 资产损失专项申报/清单申报状态\n"
        "4) 期间归属正确性（损失确认时点是否恰当）\n"
        "5) 分类评价结论（分类是否正确/税前扣除处理是否恰当/是否需要纳税调增）"
    ),
    "overall-opinion": (
        "请生成K13营业外支出底稿总体审计意见。"
        "需涵盖：\n"
        "1) 科目概况（6711营业外支出本期发生额/审定数/重大程度）\n"
        "2) 去向构成及合理性评价\n"
        "3) 分类正确性结论（与日常活动无关的界定）\n"
        "4) 税前扣除性总体评价\n"
        "   - 可扣除/不可扣除/限额扣除各占比\n"
        "   - 纳税调增金额及依据\n"
        "5) 同比变动分析及原因说明\n"
        "6) 与相关科目联动（所得税费用L/递延所得税N/管理费用K8）\n"
        "7) 总体审计结论（是否存在重大错报/审计调整建议）\n"
        "8) 剩余审计风险评估"
    ),
}


@router.post("/api/workpapers/{wp_id}/k13/ai-generate")
async def k13_ai_generate(
    wp_id: str,
    body: K13AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> K13AiGenerateResponse:
    if not getattr(settings, "WP_AI_SERVICE_ENABLED", True):
        raise HTTPException(503, "AI 服务未启用")

    if body.section not in _SUPPORTED_SECTIONS:
        raise HTTPException(
            400,
            f"不支持的 section: {body.section}。支持: {sorted(_SUPPORTED_SECTIONS)}",
        )

    project_context = await _load_project_context(wp_id, db)
    user_prompt = _build_user_prompt(
        body.section, body.existingContent, body.relatedContext, project_context
    )
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    result = await chat_completion(messages=messages, temperature=0.3, max_tokens=2000)
    if isinstance(result, str) and result.startswith("["):
        return K13AiGenerateResponse(content="", sources=[])
    return K13AiGenerateResponse(content=result, sources=[])


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
        logger.warning("K13 AI: project context 加载失败: %s", e)
    return ctx
