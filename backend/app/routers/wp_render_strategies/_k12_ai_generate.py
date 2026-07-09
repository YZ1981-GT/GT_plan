"""K12 营业外收入 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/k12/ai-generate

sections: non-operating-eval / overall-opinion

损益类底稿AI辅助要点：
- 营业外收入分类评价（来源分析+分类正确性评价）
- 总体审计意见

科目6301营业外收入（损益类/贷方科目！取发生额非余额）
营业外收入 = 与日常活动无关的利得（vs 其他收益6117/K10 = 与日常活动相关）

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

router = APIRouter(tags=["k12-ai"])


class K12AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class K12AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "non-operating-eval",
    "overall-opinion",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 K12《营业外收入》。
科目6301营业外收入（**损益类/贷方科目**）。

营业外收入核心规则：
1. **损益类取发生额！**非期末余额。贷方=收入增加，借方=收入冲回/红冲
2. 净发生额=贷方发生-借方发生（正数=净收入）
3. 审定数=未审数+AJE+RJE
4. 营业外收入的本质：与日常活动无关的利得
5. 分类判断核心：与日常活动无关→营业外收入(6301/K12)；与日常活动相关→其他收益(6117/K10)
6. 营业外收入来源分类：
   - 政府补助（与日常活动无关的部分）
   - 债务重组利得
   - 资产盘盈（现金/固定资产盘盈）
   - 罚款收入（违约金/赔偿金）
   - 捐赠利得
   - 无法支付的应付款项
   - 其他（确实无法归入以上类别的利得）
7. 偶发性/持续性分析：营业外收入应为偶发性（非经常性损益），持续性收入需关注分类正确性
8. 政府补助分类依据CAS16：与资产相关/与收益相关；与日常活动相关→其他收益(6117)

适用准则：CAS16政府补助、CAS12债务重组、CAS30财务报表列报。
输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "non-operating-eval": (
        "请生成K12营业外收入分类评价，分析科目6301各来源的分类正确性。"
        "需涵盖：\n"
        "1) 营业外收入来源构成分析\n"
        "   - 政府补助（与日常活动无关部分）：金额/占比/依据文件\n"
        "   - 债务重组利得：交易对手/重组方案/确认时点\n"
        "   - 资产盘盈：盘盈资产类别/金额/审批手续\n"
        "   - 罚款收入：来源/金额/是否有法律依据\n"
        "   - 捐赠利得/无法支付款项/其他\n"
        "2) 分类正确性评价\n"
        "   - 各项收入是否确属「与日常活动无关」（核心判断）\n"
        "   - 是否存在应计入其他收益(6117)却误入营业外收入的项目\n"
        "   - 政府补助分类是否符合CAS16（与资产/收益相关+与日常活动相关性）\n"
        "3) 偶发性/持续性分析\n"
        "   - 各项收入是否具有偶发性（非经常性损益特征）\n"
        "   - 连续多期出现的项目是否需要重分类\n"
        "4) 期间归属正确性（收入确认时点是否恰当）\n"
        "5) 分类评价结论（分类是否正确/是否需要重分类调整）"
    ),
    "overall-opinion": (
        "请生成K12营业外收入底稿总体审计意见。"
        "需涵盖：\n"
        "1) 科目概况（6301营业外收入本期发生额/审定数/重大程度）\n"
        "2) 来源构成及合理性评价\n"
        "3) 分类正确性结论（与日常活动无关 vs 其他收益6117/K10 的界定）\n"
        "4) 偶发性/非经常性损益界定评价\n"
        "5) 同比变动分析及原因说明\n"
        "6) 与相关科目联动（其他收益K10/政府补助/债务重组）\n"
        "7) 总体审计结论（是否存在重大错报/审计调整建议）\n"
        "8) 剩余审计风险评估"
    ),
}


@router.post("/api/workpapers/{wp_id}/k12/ai-generate")
async def k12_ai_generate(
    wp_id: str,
    body: K12AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> K12AiGenerateResponse:
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
        return K12AiGenerateResponse(content="", sources=[])
    return K12AiGenerateResponse(content=result, sources=[])


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
        logger.warning("K12 AI: project context 加载失败: %s", e)
    return ctx
