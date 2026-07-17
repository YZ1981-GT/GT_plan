"""F2 计价/跌价组 — AI 辅助生成."""

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

router = APIRouter(tags=["f2-val-ai"])


class F2ValAiRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class F2ValAiResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED = {
    "valuation-conclusion",
    "valuation-note",
    "impairment-evaluation",
    "reversal-evaluation",
    "fairness-evaluation",
    "cost-analysis",
    "labor-analysis",
    "allocation-note",
    "allocation-conclusion",
    "impairment-note",
    "impairment-conclusion",
    "obsolete-note",
    "obsolete-conclusion",
    "inspection-sampling-note",
    "inspection-audit-note",
    "inspection-conclusion",
}

_PROMPTS: dict[str, str] = {
    "valuation-conclusion": "请生成F2-38~40计价测试的总体审计结论。",
    "valuation-note": (
        "请根据底稿数据起草F2-38~40计价方法测试的「审计说明」，"
        "概述抽样与重新计算程序、各测试项目的差异分析与核对结果、"
        "计价方法运用的准确性与一贯性，以及拟调整/未调整事项及其影响，语气客观、适合直接填入底稿。"
    ),
    "impairment-evaluation": "请生成F2-47跌价准备NRV测试的审计评价结论。",
    "reversal-evaluation": "请生成F2-49跌价转回的审计评价结论。",
    "fairness-evaluation": "请生成F2-52关联采购公允性评价结论。",
    "cost-analysis": "请生成F2-41~44生产成本分析的审计结论。",
    "labor-analysis": "请生成F2-42直接人工分析的审计结论。",
    "allocation-note": (
        "请根据底稿数据起草F2-44「抽查×月×车间生产成本分配表」的「审计说明」，"
        "说明抽查月份/车间的选取、分配标准（产量/工时/定额成本等）的合理性与一贯性、"
        "分配额合计与成本池的勾稽情况、应计单位成本与入库单价核对结果及异常处理，"
        "语气客观、适合直接填入底稿。"
    ),
    "allocation-conclusion": (
        "请生成F2-44生产成本分配表的正式审计结论，采用A/B/C结论口径："
        "A未见异常；B除重大不符应调整外其余未见异常；C重大未调整或范围受限不可确认。"
        "结合分配勾稽差异与单价核对异常情况判断，只输出结论正文。"
    ),
    "impairment-note": (
        "请根据底稿数据起草F2-47「存货跌价准备测试表」的审计说明，"
        "说明样本范围、可变现净值测算程序、售价及完工成本等依据、库龄勾稽结果、"
        "账面计提与审计测算差异及异常处理，并说明与F2-48长库龄明细的勾稽关系。"
        "语气客观、适合直接填入底稿。"
    ),
    "impairment-conclusion": (
        "请生成F2-47存货跌价准备测试的正式审计结论，采用A/B/C结论口径："
        "A跌价准备计提充分、准确，未见异常；B除应调整事项外其余未见异常；"
        "C存在重大未调整差异或审计范围受限，无法确认。"
        "结合应计提、账面计提、审计调整及异常样本情况判断，只输出结论正文。"
    ),
    "obsolete-note": (
        "请根据底稿数据起草F2-48「长库龄/呆滞/超过保质期存货明细表」的「审计说明」，"
        "说明长库龄、呆滞、冷背、过时及超保质期存货的识别过程（库龄分析、盘点观察、管理层访谈等）、"
        "减值迹象分析、已计提跌价金额与减值迹象的匹配性，以及与F2-47跌价测试的勾稽关系，"
        "语气客观、适合直接填入底稿。"
    ),
    "obsolete-conclusion": (
        "请生成F2-48长库龄/呆滞/超保质期存货明细表的正式审计结论，采用A/B/C结论口径："
        "A未见异常；B除重大不符应调整外其余未见异常；C重大未调整或范围受限不可确认。"
        "结合长库龄项数、减值迹象及跌价计提充分性判断，只输出结论正文。"
    ),
    "inspection-sampling-note": (
        "请根据底稿数据起草F2-33/34检查表「样本选取标准与规模」中的抽样过程说明，"
        "写明测试总体概况、抽样方法、样本量及工具/引擎使用情况，适合直接填入底稿。"
    ),
    "inspection-audit-note": (
        "请根据检查覆盖率、异常笔数等数据起草F2-33/34「审计说明」，"
        "说明检查比例是否充分、有无扩大样本或关注事项，语气客观。"
    ),
    "inspection-conclusion": (
        "请生成存货检查表(F2-33/34)的正式审计结论，采用A/B/C结论口径："
        "A未见异常；B除重大不符应调整外其余未见异常；C重大未调整或范围受限不可确认。"
        "只输出结论正文。"
    ),
}

_SYSTEM = """你是一位资深注册会计师，协助编制F2存货计价/跌价/检查底稿。
输出中文审计专业用语，直接输出正文，简洁适合底稿。"""


@router.post("/api/workpapers/{wp_id}/f2-val/ai-generate")
async def f2_val_ai_generate(
    wp_id: str,
    body: F2ValAiRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> F2ValAiResponse:
    if not getattr(settings, "WP_AI_SERVICE_ENABLED", True):
        raise HTTPException(503, "AI 服务未启用")
    if body.section not in _SUPPORTED:
        raise HTTPException(400, f"不支持的 section: {body.section}")

    ctx = await _load_ctx(wp_id, db)
    parts = [f"## 任务\n{_PROMPTS.get(body.section, '请生成审计文本。')}\n"]
    if ctx.get("client_name"):
        parts.append(f"客户：{ctx['client_name']}  年度：{ctx.get('audit_year', '')}\n")
    if body.relatedContext:
        lines = "\n".join(f"- {k}: {v}" for k, v in body.relatedContext.items() if v is not None)
        if lines:
            parts.append(f"## 底稿数据\n{lines}\n")
    if body.existingContent:
        parts.append(f"## 已有内容\n{body.existingContent[:2000]}\n请补充完善。")
    else:
        parts.append("请根据以上信息生成专业初稿。")

    result = await chat_completion(
        messages=[{"role": "system", "content": _SYSTEM}, {"role": "user", "content": "\n".join(parts)}],
        temperature=0.3,
        max_tokens=2000,
    )
    if isinstance(result, str) and result.startswith("["):
        return F2ValAiResponse(content="", sources=[])
    return F2ValAiResponse(content=result, sources=[])


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
        logger.warning("F2 val AI context: %s", e)
    return {}
