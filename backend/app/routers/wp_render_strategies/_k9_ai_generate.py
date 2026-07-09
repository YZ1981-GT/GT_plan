"""K9 管理费用 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/k9/ai-generate

sections: fluctuation-analysis / cutoff-conclusion / contract-check-eval / overall-opinion

损益类底稿AI辅助要点：
- 实质性分析（同比/环比/占收入比/异常波动识别）
- 截止测试结论（双向跨期判断）
- 合同检查评价
- 总体审计意见

Requirements: 4.6, 8.1
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

router = APIRouter(tags=["k9-ai"])


class K9AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class K9AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "fluctuation-analysis",
    "cutoff-conclusion",
    "contract-check-eval",
    "overall-opinion",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 K9《管理费用》。
科目6602管理费用（**损益类/借方科目**）。

管理费用核心规则：
1. **损益类取发生额！**非期末余额。借方=费用增加，贷方=费用冲回/结转
2. 净发生额=借方发生-贷方发生（正数=净费用）
3. 审定数=未审数+AJE+RJE
4. 实质性分析：同比变动率=(本期-上期)/上期，占收入比=费用/营业收入
5. 异常判断：|同比变动率|>阈值 需关注并说明原因
6. 截止测试双向：记账凭证→原始凭证（存在认定）+ 原始凭证→记账凭证（完整性认定）
7. 合同检查：重大费用合同（中介服务/咨询/租赁）真实性/金额匹配/审批合规

适用准则：CAS30财务报表列报、CAS14收入（关联收入占比分析）。
输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "fluctuation-analysis": (
        "请生成K9管理费用实质性分析（波动分析）结论，分析科目6602的变动情况。"
        "需涵盖：\n"
        "1) 本期发生额总体变动（同比变动率及原因分析）\n"
        "2) 各明细费用项的占比变动（职工薪酬/办公费/折旧摊销/中介机构费/研发费/税金/无形资产摊销/其他）\n"
        "3) 异常波动项目识别（|变动率|>30%的项目逐项说明）\n"
        "4) 占营业收入比变动分析（费用率趋势是否合理）\n"
        "5) 与同行业比较的合理性评价\n"
        "6) 实质性分析结论（是否发现需要进一步关注的事项）"
    ),
    "cutoff-conclusion": (
        "请生成K9管理费用截止测试结论，涵盖双向截止测试结果。"
        "需涵盖：\n"
        "1) 记账凭证→原始凭证方向测试结果（K9-6）\n"
        "   - 测试样本范围（期末±5天）\n"
        "   - 跨期项目数量及金额\n"
        "   - 是否存在重大跨期错误\n"
        "2) 原始凭证→记账凭证方向测试结果（K9-7）\n"
        "   - 测试样本范围\n"
        "   - 未及时入账项目及影响\n"
        "   - 完整性认定评价\n"
        "3) 综合截止结论（截止是否正确/是否需要调整）"
    ),
    "contract-check-eval": (
        "请生成K9管理费用合同检查评价意见。"
        "需涵盖：\n"
        "1) 重大合同检查覆盖范围（中介服务/咨询/租赁等类型覆盖率）\n"
        "2) 合同真实性验证结果\n"
        "3) 金额匹配情况（合同金额vs实际入账金额）\n"
        "4) 审批合规性检查结果\n"
        "5) 不合规项汇总及影响评估\n"
        "6) 合同检查总体结论"
    ),
    "overall-opinion": (
        "请生成K9管理费用底稿总体审计意见。"
        "需涵盖：\n"
        "1) 科目概况（6602管理费用本期发生额/审定数/重大程度）\n"
        "2) 实质性分析结论（波动是否合理/异常项是否已获取充分解释）\n"
        "3) 截止测试结论（截止是否正确）\n"
        "4) 合同检查结论（费用真实性/合规性）\n"
        "5) 与相关科目联动情况（K8销售费用/D4营业收入占比）\n"
        "6) 总体审计结论（是否存在重大错报/审计调整建议）\n"
        "7) 剩余审计风险评估"
    ),
}


@router.post("/api/workpapers/{wp_id}/k9/ai-generate")
async def k9_ai_generate(
    wp_id: str,
    body: K9AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> K9AiGenerateResponse:
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
        return K9AiGenerateResponse(content="", sources=[])
    return K9AiGenerateResponse(content=result, sources=[])


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
        logger.warning("K9 AI: project context 加载失败: %s", e)
    return ctx
