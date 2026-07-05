"""D2 应收账款 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/d2/ai-generate
Body: { section: string, existingContent: string, relatedContext: object }

支持 sections:
- adj-note / adj-conclusion: 审定表说明/结论
- policy-evaluation: 坏账政策评价
- analysis-note: 分析程序说明
- detail-note: 明细表审计说明
- writeoff-analysis: 转回核销分析
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.llm_client import chat_completion

logger = logging.getLogger(__name__)

router = APIRouter(tags=["d2-ai"])


# ═══════════════════════════════════════════════════════════════════════════════
# Request / Response
# ═══════════════════════════════════════════════════════════════════════════════


class D2AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class D2AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


# ═══════════════════════════════════════════════════════════════════════════════
# 支持的 section 列表及对应 prompt 模板
# ═══════════════════════════════════════════════════════════════════════════════

_SUPPORTED_SECTIONS = {
    "adj-note",
    "adj-conclusion",
    "policy-evaluation",
    "analysis-note",
    "detail-note",
    "writeoff-analysis",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 D2《应收账款》。
你需要根据提供的底稿数据和审计准则要求，生成专业、简洁、可直接使用的审计文本。

科目特征：1122 应收账款，借方科目/资产类。核心关注：账龄分析、坏账准备计提、ECL预期信用损失、函证、截止测试、关联方识别。

输出要求：
- 语言：中文
- 风格：审计专业用语，客观陈述事实和结论
- 如需引用具体数据但无法获取，使用 [待填] 占位
- 直接输出正文内容，不要输出标题
- 简洁明了，适合审计底稿使用"""

_SECTION_PROMPTS: dict[str, str] = {
    "adj-note": "请生成D2-1审定表的审计说明，基于应收账款变动数据、SUMIF分类汇总和分析程序结果，说明本期应收账款审定情况。",
    "adj-conclusion": "请生成D2-1审定表的审计结论，综合审计程序结果对应收账款余额真实性/完整性/计价与分摊/列报给出结论。",
    "policy-evaluation": "请基于被审计单位实际情况和CAS22金融工具准则要求，评价其应收账款坏账准备计提政策及预期信用损失模型的恰当性。",
    "analysis-note": "请基于D2-5分析程序结果（周转率/周转天数/变动趋势等异常项），生成分析程序审计说明。",
    "detail-note": "请基于D2-2明细表数据（客户集中度、账龄分布、信用风险分类），生成明细表审计说明。",
    "writeoff-analysis": "请基于D2-11转回核销明细（转回原因/核销原因/金额趋势），分析坏账准备转回与核销的合理性并给出评价。",
}


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/api/workpapers/{wp_id}/d2/ai-generate")
async def d2_ai_generate(
    wp_id: str,
    body: D2AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> D2AiGenerateResponse:
    """D2 应收账款 AI 辅助生成"""

    if not getattr(settings, "WP_AI_SERVICE_ENABLED", True):
        raise HTTPException(503, "AI 服务未启用")

    if body.section not in _SUPPORTED_SECTIONS:
        raise HTTPException(
            400,
            f"不支持的 section: {body.section}。支持: {sorted(_SUPPORTED_SECTIONS)}",
        )

    project_context = await _load_project_context(wp_id, db)
    cross_context = await _load_d2_cross_context(wp_id, db)

    user_prompt = _build_user_prompt(
        section=body.section,
        existing_content=body.existingContent,
        related_context=body.relatedContext,
        project_context=project_context,
        cross_context=cross_context,
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    result = await chat_completion(
        messages=messages,
        temperature=0.3,
        max_tokens=2000,
    )

    if isinstance(result, str) and result.startswith("["):
        return D2AiGenerateResponse(content="", sources=[])

    return D2AiGenerateResponse(content=result, sources=[])


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════


def _build_user_prompt(
    section: str,
    existing_content: str,
    related_context: dict[str, Any],
    project_context: dict,
    cross_context: dict[str, Any] | None = None,
) -> str:
    parts: list[str] = []

    section_guidance = _SECTION_PROMPTS.get(section, "请生成审计底稿文本。")
    parts.append(f"## 任务\n{section_guidance}\n")

    ctx_lines = []
    if project_context.get("client_name"):
        ctx_lines.append(f"客户名称：{project_context['client_name']}")
    if project_context.get("audit_year"):
        ctx_lines.append(f"审计年度：{project_context['audit_year']}年")
    if project_context.get("business_category"):
        ctx_lines.append(f"业务类别：{project_context['business_category']}")
    if ctx_lines:
        parts.append("## 项目信息\n" + "\n".join(ctx_lines) + "\n")

    if related_context:
        ctx_str = "\n".join(f"- {k}: {v}" for k, v in related_context.items() if v)
        if ctx_str:
            parts.append(f"## 底稿数据\n{ctx_str}\n")

    if cross_context:
        cross_lines = []
        if cross_context.get("detail_row_count"):
            cross_lines.append(f"D2-2明细行数：{cross_context['detail_row_count']}")
        if cross_context.get("receivable_total"):
            cross_lines.append(f"应收账款期末审定合计：{cross_context['receivable_total']}")
        if cross_context.get("bad_debt_total"):
            cross_lines.append(f"坏账准备期末审定合计：{cross_context['bad_debt_total']}")
        if cross_context.get("ecl_single_total"):
            cross_lines.append(f"D2-9单项ECL应计提合计：{cross_context['ecl_single_total']}")
        if cross_context.get("policy_non_compliant"):
            cross_lines.append(f"D2-8政策不合规段数：{cross_context['policy_non_compliant']}")
        if cross_lines:
            parts.append("## 跨Sheet联动摘要\n" + "\n".join(cross_lines) + "\n")

    if existing_content:
        parts.append(f"## 已有内容（请补充完善）\n{existing_content[:2000]}\n")
        parts.append("请基于以上信息补充完善已有内容。保留合理部分，纠正不当表述。")
    else:
        parts.append("请根据以上信息生成专业初稿。")

    return "\n".join(parts)


async def _load_project_context(wp_id: str, db: AsyncSession) -> dict:
    """从 working_paper → project 获取上下文"""
    import sqlalchemy as sa

    ctx: dict = {
        "client_name": "",
        "audit_year": "",
        "business_category": "",
    }
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
        logger.warning("D2 AI: project context 加载失败: %s", e)
    return ctx


async def _load_d2_cross_context(wp_id: str, db: AsyncSession) -> dict[str, Any]:
    """从 checklist_responses 加载 D2 跨 sheet 摘要供 AI 引用"""
    import json
    import sqlalchemy as sa

    ctx: dict[str, Any] = {}
    try:
        result = await db.execute(
            sa.text("""
                SELECT item_id, remark
                FROM checklist_responses
                WHERE workpaper_id = :wp_id
                  AND item_id LIKE 'D2-%'
            """),
            {"wp_id": wp_id},
        )
        rows = {r.item_id: r.remark for r in result.fetchall() if r.remark}

        detail_raw = rows.get("D2-detail-rows")
        if detail_raw:
            try:
                detail = json.loads(detail_raw)
                if isinstance(detail, list):
                    ctx["detail_row_count"] = len(detail)
                    ctx["receivable_total"] = sum(
                        float(x.get("currentAudited") or 0) for x in detail if isinstance(x, dict)
                    )
            except json.JSONDecodeError:
                pass

        for key, target in [
            ("D2-bd-individual-rows", "bad_debt_individual"),
            ("D2-bd-aging-rows", "bad_debt_aging"),
            ("D2-bd-customer-rows", "bad_debt_customer"),
        ]:
            raw = rows.get(key)
            if not raw:
                continue
            try:
                bd_rows = json.loads(raw)
                if isinstance(bd_rows, list):
                    fixed = next((x for x in bd_rows if isinstance(x, dict) and x.get("isFixed")), None)
                    if fixed:
                        ctx[target] = float(fixed.get("currentAudited") or 0)
            except json.JSONDecodeError:
                pass

        if any(k.startswith("bad_debt_") for k in ctx):
            ctx["bad_debt_total"] = sum(
                ctx.get(k, 0) for k in ("bad_debt_individual", "bad_debt_aging", "bad_debt_customer")
            )

        ecl_raw = rows.get("D2-ecl-single-rows")
        if ecl_raw:
            try:
                ecl_rows = json.loads(ecl_raw)
                if isinstance(ecl_rows, list):
                    ctx["ecl_single_total"] = sum(
                        float(x.get("shouldProvision") or 0) for x in ecl_rows if isinstance(x, dict)
                    )
            except json.JSONDecodeError:
                pass

        policy_raw = rows.get("D2-policy-paragraphs")
        if policy_raw:
            try:
                paras = json.loads(policy_raw)
                if isinstance(paras, list):
                    ctx["policy_non_compliant"] = sum(
                        1 for p in paras if isinstance(p, dict) and p.get("conclusion") == "N"
                    )
            except json.JSONDecodeError:
                pass
    except Exception as e:
        logger.warning("D2 AI: cross context 加载失败: %s", e)
    return ctx
