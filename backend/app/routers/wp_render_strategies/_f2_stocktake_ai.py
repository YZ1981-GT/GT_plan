"""F2 存货监盘 — AI 辅助生成."""

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

router = APIRouter(tags=["f2-st-ai"])

_SUPPORTED = {
    "stocktake-questionnaire",
    "stocktake-questionnaire-field",
    "stocktake-plan",
    "stocktake-plan-field",
    "stocktake-summary",
    "stocktake-summary-field",
    "stocktake-reconcile",
    "stocktake-reconcile-field",
    "stocktake-sample",
    "stocktake-sample-field",
    "stocktake-rollforward",
    "stocktake-rollforward-field",
}

_PROMPTS: dict[str, str] = {
    "stocktake-questionnaire": "请生成 F2-21 存货监盘计划问卷的总体结论（地点覆盖、人员组织、计划适当性、缺陷与风险应对，可索引至 F2-21A/F2-22）。",
    "stocktake-questionnaire-field": (
        "请针对 F2-21 盘点计划问卷中的单道题目，根据已了解的盘点安排与风险信息，"
        "起草简洁、可直接写入底稿的回答（2~6 句，勿编造无法从上下文得出的具体数据）。"
    ),
    "stocktake-plan": (
        "请生成 F2-22 监盘计划结论（2~6 句）：概括目的、范围裁剪、人员分工与抽盘覆盖安排是否适当。"
    ),
    "stocktake-plan-field": (
        "请针对 F2-22 存货监盘计划（对齐 G2-6-2）中的单个字段，起草可直接写入该文本框的内容。"
        "2~8 句，专业简洁；勿输出 JSON/Markdown 标题；勿编造上下文没有的具体金额或百分比。"
    ),
    "stocktake-summary": (
        "请按 G2-6-1 结构生成 F2-23 存货监盘小结："
        "目的/范围/地点/时间/分工/盘点方法/情况汇总（含覆盖率）/分地点结果/结论。"
    ),
    "stocktake-summary-field": (
        "请针对 F2-23 存货监盘小结（对齐 G2-6-1）中的单个字段，起草可直接写入该文本框的内容。"
        "2~8 句，专业简洁；未结账时可说明金额暂不确定；勿编造上下文没有的具体数据。"
    ),
    "stocktake-reconcile": (
        "请按 F2-24 结构生成账面余额与仓储台账（ERP）核对结论："
        "说明是否完成资产负债表日双向核对；若盘点日异于截止日是否另做盘点日核对；"
        "结合「差异行摘要」评价重大差异原因与是否需调整；给出 A/B/C 式结论。"
        "勿编造摘要中未出现的品名或数量。"
    ),
    "stocktake-reconcile-field": (
        "请针对 F2-24 账面与仓储台账核对中的单个字段，起草可直接写入该文本框的内容。"
        "2~8 句，专业简洁；可引用差异行摘要中的品名与差额；勿编造上下文没有的具体数量或金额。"
    ),
    "stocktake-sample": (
        "请按 F2-25 双向抽盘结构生成审计结论："
        "说明记录→实物（存在）与实物→记录（完整）的抽盘覆盖；"
        "结合差异行摘要分析账面/企业盘点/审计抽盘三方差异及原因；品质状况对跌价的影响；给出 A/B/C 式结论。"
        "勿编造摘要中未出现的品名或数量。"
    ),
    "stocktake-sample-field": (
        "请针对 F2-25 抽盘结果汇总中的单个字段，起草可直接写入该文本框的内容。"
        "2~8 句，专业简洁；可结合差异行摘要；勿编造上下文没有的具体数量。"
    ),
    "stocktake-rollforward": (
        "请生成 F2-26 存货盘点倒轧表的审计说明/结论。"
        "区分盘点日相对截止日的方向（日后倒推：D=A+发出−入库；日前顺推：D=A+入库−发出）；"
        "结合差异行摘要评价收发期间核实、数量/金额差异及是否调整；给出 A/B/C 式结论。"
        "勿编造摘要中未出现的品名或数量。"
    ),
    "stocktake-rollforward-field": (
        "请针对 F2-26 盘点倒轧表中的单个字段，起草可直接写入该文本框的内容。"
        "2~6 句，专业简洁；可结合倒轧方向与差异行摘要；勿编造上下文没有的具体数量。"
    ),
}

_SYSTEM = """你是一位资深注册会计师，协助编制 F2 存货监盘系列底稿。
输出中文审计专业用语，字段级任务直接输出可粘贴正文，不要 JSON、不要代码围栏。"""


class F2StAiRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class F2StAiResponse(BaseModel):
    content: str
    sources: list[str] = []


@router.post("/api/workpapers/{wp_id}/f2-st/ai-generate")
async def f2_stocktake_ai_generate(
    wp_id: str,
    body: F2StAiRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> F2StAiResponse:
    if not getattr(settings, "WP_AI_SERVICE_ENABLED", True):
        raise HTTPException(503, "AI 服务未启用")
    if body.section not in _SUPPORTED:
        raise HTTPException(400, f"不支持的 section: {body.section}")

    ctx = await _load_ctx(wp_id, db)
    parts = [f"## 任务\n{_PROMPTS.get(body.section, '请生成监盘审计文本。')}\n"]
    if ctx.get("client_name"):
        parts.append(f"客户：{ctx['client_name']}  年度：{ctx.get('audit_year', '')}\n")
    if body.section == "stocktake-questionnaire-field":
        q_no = body.relatedContext.get("questionNo") or body.relatedContext.get("questionId") or ""
        q_label = body.relatedContext.get("questionLabel") or ""
        if q_label:
            parts.append(f"## 当前题目\n{q_no}. {q_label}\n")
    if body.section in (
        "stocktake-plan-field",
        "stocktake-summary-field",
        "stocktake-reconcile-field",
        "stocktake-sample-field",
        "stocktake-rollforward-field",
    ):
        field_label = body.relatedContext.get("fieldLabel") or body.relatedContext.get("fieldId") or ""
        if field_label:
            parts.append(f"## 当前字段\n{field_label}\n")
    if body.relatedContext:
        skip = {
            "questionNo", "questionId", "questionLabel",
            "fieldId", "fieldLabel",
            "varianceSummary", "bsVarianceSummary", "countVarianceSummary",
            "existVarianceSummary", "floorVarianceSummary",
            "afterVarianceSummary", "beforeVarianceSummary",
        }
        variance_parts = []
        for vk in (
            "varianceSummary",
            "bsVarianceSummary",
            "countVarianceSummary",
            "existVarianceSummary",
            "floorVarianceSummary",
            "afterVarianceSummary",
            "beforeVarianceSummary",
        ):
            vv = body.relatedContext.get(vk)
            if vv:
                variance_parts.append(str(vv))
        if variance_parts:
            parts.append("## 差异行摘要\n" + "\n".join(variance_parts) + "\n")
        lines = "\n".join(
            f"- {k}: {v}"
            for k, v in body.relatedContext.items()
            if v is not None and k not in skip
        )
        if lines:
            parts.append(f"## 底稿数据\n{lines}\n")
    if body.existingContent:
        parts.append(f"## 已有内容\n{body.existingContent[:2000]}\n请补充完善。")
    else:
        parts.append("请根据以上信息生成专业初稿。")

    max_tokens = (
        800
        if body.section.endswith("-field")
        else 2000
    )
    result = await chat_completion(
        messages=[{"role": "system", "content": _SYSTEM}, {"role": "user", "content": "\n".join(parts)}],
        temperature=0.3,
        max_tokens=max_tokens,
    )
    if isinstance(result, str) and result.startswith("["):
        return F2StAiResponse(content="", sources=[])
    return F2StAiResponse(content=result, sources=[])


async def _load_ctx(wp_id: str, db: AsyncSession) -> dict:
    try:
        r = await db.execute(
            sa.text("""
                SELECT p.client_name, p.audit_year FROM working_paper wp
                JOIN projects p ON wp.project_id = p.id WHERE wp.id = :wp_id
            """),
            {"wp_id": wp_id},
        )
        row = r.fetchone()
        if row:
            return {"client_name": row.client_name or "", "audit_year": str(row.audit_year or "")}
    except Exception as e:
        logger.warning("F2 stocktake AI context: %s", e)
    return {}
