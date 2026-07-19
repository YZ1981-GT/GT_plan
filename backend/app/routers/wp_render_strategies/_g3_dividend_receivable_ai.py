"""G3 应收股利 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/g3/ai/{section}

sections: dividend-calc-conclusion / overdue-evaluation / overall-opinion
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

router = APIRouter(tags=["g3-ai"])

# AI 生成超时（秒）
_AI_TIMEOUT = 30.0


class G3AiGenerateRequest(BaseModel):
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class G3AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 G3《应收股利》。
科目1131应收股利（借方/资产类）。
核心关注：股利测算准确性（持股数量×每股股利）、实际分红率合理性
（分红总额/净利润×100%）、长期未收回风险评估（逾期>180天→高风险 / >90天→中风险）、
被投资方经营状况与分红能力分析。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "adjudication-note": (
        "请生成G3-1审定表的审计说明，概述对应收股利（1131）各被投资方期初/期末审定程序、"
        "与试算平衡表勾稽情况、拟调整事项及影响。"
    ),
    "adjudication-conclusion": (
        "请生成G3-1审定表的审计结论，按A/B/C口径评价科目1131审定数与试算勾稽结果。"
    ),
    "detail-note": (
        "请生成G3-2明细表的审计说明，概述持股比例、分红方案、应收股利核算及逾期关注事项。"
    ),
    "detail-conclusion": (
        "请生成G3-2明细表的审计结论，按A/B/C口径评价明细完整性与计价准确性。"
    ),
    "adjustment-note": (
        "请生成G3-3调整分录的审计说明，概述调整依据、AJE/RJE性质及对审定表影响。"
    ),
    "adjustment-conclusion": (
        "请生成G3-3调整分录的审计结论，评价借贷平衡与依据充分性。"
    ),
    "dividend-calc-note": (
        "请生成G3-4测算及检查表的审计说明，覆盖三条程序："
        "（1）增加测算：持股数量×每股股利与账面已计差异；"
        "（2）减少检查：本期减少与收现/其他转出核对；"
        "（3）期后收回抽查及异常事项。"
    ),
    "dividend-calc-conclusion": (
        "请生成G3-4测算及检查表的审计结论，按A/B/C口径评价："
        "测算差异（账面已计−测算）是否重大、减少核对是否闭环、"
        "期后收回是否支持期末余额存在性；注明拟调整及交叉索引事项。"
    ),
    "overdue-note": (
        "请生成G3-5长期未收回检查的审计说明，概述逾期识别、可收回性评估及风险等级划分依据。"
    ),
    "overdue-evaluation": (
        "请生成G3-5长期未收回检查的审计评价，分析长期未收回应收股利的回收风险、"
        "被投资方经营状况、历史分红记录、预计可收回性，"
        "以及风险等级划分（逾期>180天→高风险、>90天→中风险）的合理性。"
    ),
    "disclosure-listed-note": (
        "请生成G3上市公司附注披露说明初稿，按被投资方列示应收股利期初/期末余额，"
        "并与审定数勾稽。"
    ),
    "disclosure-soe-note": (
        "请生成G3国企附注披露说明初稿，简要列示应收股利期初/期末余额及主要构成，"
        "并与审定数勾稽。"
    ),
    "overall-opinion": (
        "请生成G3应收股利的整体审计意见，综合股利测算准确性、实际分红率合理性、"
        "长期未收回风险评估各方面，形成对科目1131列报与披露的总体结论。"
    ),
}

_SUPPORTED_SECTIONS = set(_SECTION_PROMPTS.keys())


@router.post("/api/workpapers/{wp_id}/g3/ai/{section}")
async def g3_ai_generate(
    wp_id: str,
    section: str,
    body: G3AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> G3AiGenerateResponse:
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
        return G3AiGenerateResponse(content="", sources=[])
    return G3AiGenerateResponse(content=result, sources=[])


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
        logger.warning("G3 AI: project context 加载失败: %s", e)
    return ctx
