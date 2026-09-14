"""K10 其他收益 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/k10/ai-generate

sections: grant-reconcile-conclusion / receivable-grant-eval / overall-opinion

损益类底稿AI辅助要点：
- 政府补助核对结论（K10-4，与K7递延收益分摊一致性）
- 应收补助评价（K10-5，收款权利确凿性/预期可收回/确认时点）
- 总体审计意见

科目6117其他收益（损益类/贷方科目！取发生额非余额）
其他收益 = 与日常活动相关的政府补助（vs 营业外收入6301/K12 = 与日常活动无关）

Requirements: 4.1, 7.1
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

router = APIRouter(tags=["k10-ai"])


class K10AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class K10AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "grant-reconcile-conclusion",
    "receivable-grant-eval",
    "overall-opinion",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 K10《其他收益》。
科目6117其他收益（**损益类/贷方科目**）。

其他收益核心规则：
1. **损益类取发生额！**非期末余额。贷方=收益增加，借方=收益冲回/红冲
2. 净发生额=贷方发生-借方发生（正数=净收益）
3. 审定数=未审数+AJE+RJE
4. 其他收益的本质：与日常活动相关的政府补助
5. 分类判断核心：与日常活动相关→其他收益(6117/K10)；与日常活动无关→营业外收入(6301/K12)
6. 其他收益来源分类：
   - 即征即退增值税（与收益相关的政府补助）
   - 财政贴息（与资产/收益相关的政府补助）
   - 研发补助（研发费加计扣除等）
   - 稳岗补贴
   - 产业扶持资金
   - 递延收益分摊计入（K7递延收益本期摊入）
   - 其他与日常活动相关的政府补助
7. 政府补助核对要点：
   - 合计计入=直接计入+递延分摊
   - 递延分摊须与K7递延收益(2401)本期分摊一致
   - 分类正确性：与日常活动相关性判断
8. 适用准则：CAS16政府补助（2017修订）、CAS30财务报表列报
9. 与日常活动相关的判断标准：与企业正常经营业务密切相关的补助

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "grant-reconcile-conclusion": (
        "请生成K10-4政府补助核对结论，分析政府补助确认的完整性和与K7递延收益分摊的一致性。"
        "需涵盖：\n"
        "1) 政府补助确认完整性分析\n"
        "   - 本期计入其他收益的政府补助总额\n"
        "   - 直接计入部分：各项补助的确认时点和依据\n"
        "   - 递延分摊部分：与递延收益本期分摊的对应关系\n"
        "2) 与K7递延收益(2401)一致性核对\n"
        "   - K7本期递延收益转入其他收益的金额\n"
        "   - K10-4中递延分摊计入金额与K7的差额\n"
        "   - 差额原因分析（如有差异）\n"
        "3) 分类正确性评价\n"
        "   - 各项补助是否确属「与日常活动相关」\n"
        "   - 是否存在应计入营业外收入(6301)却误入其他收益的项目\n"
        "   - CAS16第十一条分类依据\n"
        "4) 核对结论（一致/存在差异需调整）"
    ),
    "receivable-grant-eval": (
        "请生成K10-5应收政府补助评价，分析应收补助的确认合规性。"
        "需涵盖：\n"
        "1) 应收政府补助概况\n"
        "   - 各项应收补助的批文依据\n"
        "   - 收款权利确凿性判断（是否已满足补助条件）\n"
        "2) 预期可收回性评估\n"
        "   - 各项补助的发放主体（财政局/科技局/工信局等）\n"
        "   - 历史回收率/发放进度\n"
        "   - 是否需要计提减值\n"
        "3) 确认时点合规性\n"
        "   - 是否满足CAS16第五条补助确认条件\n"
        "   - 满足附加条件/合理保证的判断依据\n"
        "4) 应收补助评价结论"
    ),
    "overall-opinion": (
        "请生成K10其他收益底稿总体审计意见。"
        "需涵盖：\n"
        "1) 科目概况（6117其他收益本期发生额/审定数/重大程度）\n"
        "2) 收益来源构成及合理性评价\n"
        "3) 分类正确性结论（与日常活动相关 vs 营业外收入6301/K12 的界定）\n"
        "4) 政府补助核对结论（与K7递延收益一致性）\n"
        "5) 同比变动分析及原因说明\n"
        "6) 应收补助确认评价\n"
        "7) 与相关科目联动（营业外收入K12/递延收益K7）\n"
        "8) 总体审计结论（是否存在重大错报/审计调整建议）\n"
        "9) 剩余审计风险评估"
    ),
}


@router.post("/api/workpapers/{wp_id}/k10/ai-generate")
async def k10_ai_generate(
    wp_id: str,
    body: K10AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> K10AiGenerateResponse:
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
        return K10AiGenerateResponse(content="", sources=[])
    return K10AiGenerateResponse(content=result, sources=[])


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
        logger.warning("K10 AI: project context 加载失败: %s", e)
    return ctx
