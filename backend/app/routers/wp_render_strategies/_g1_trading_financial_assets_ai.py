"""G1 交易性金融资产 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/g1/ai/{section}

sections: adjudication-summary / fair-value-conclusion / sppi-analysis /
          business-model-conclusion / counting-conclusion / voucher-check-conclusion /
          derivative-conclusion / overall-opinion
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

router = APIRouter(tags=["g1-ai"])

# AI 生成超时（秒）
_AI_TIMEOUT = 30.0


class G1AiGenerateRequest(BaseModel):
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class G1AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 G1《交易性金融资产》。
科目1501交易性金融资产（借方/资产类，以公允价值计量且变动计入当期损益）。
核心关注：公允价值层级（Level1活跃市场报价/Level2可观察输入/Level3不可观察输入）计量适当性、
SPPI合同现金流量特征测试、业务模式分析（CAS22分类：FVTPL/FVOCI/AC）、
证券监盘存在性与盘点倒轧、衍生金融工具合规性、投资收益/处置损益/公允价值变动的确认正确性。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "adjudication-summary": "请生成G1-1审定表的审定汇总说明，评价交易性金融资产按投资品种（股票/基金/债券/衍生/其他）的成本、公允价值变动、处置损益审定结果，以及与试算表的勾稽差异。",
    "fair-value-conclusion": "请生成G1-6公允价值测试的审计结论，评价Level1-3公允价值计量层级划分的适当性、报价来源/估值方法的可靠性及差异超阈值项的合理性。",
    "sppi-analysis": "请生成G1-10合同现金流量特征（SPPI）测试的审计说明，分析合同条款是否仅为对本金和利息的支付、提前还款/展期条款及非标准特征对分类的影响。",
    "business-model-conclusion": "请生成G1-8业务模式分析的审计结论，评价管理层持有目的、交易频率、KPI考核关联及CAS22分类判定（持有至收取/出售/兼有）的合理性。",
    "counting-conclusion": "请生成G1-11监盘与G1-12盘点倒轧的审计结论，评价证券存在性、监盘差异及盘点日至报表日的倒轧勾稽关系。",
    "voucher-check-conclusion": "请生成G1-13凭证检查表的审计结论，评价抽查凭证的合同/结算单/报价/授权审批/账务处理核对结果及交易真实性。",
    "derivative-conclusion": "请生成G1-14衍生金融工具核查的审计评价，评估衍生工具（期权/期货/互换/远期）名义金额、保证金、套期认定及会计处理的合规性。",
    "overall-opinion": "请生成G1交易性金融资产的整体审计意见，综合公允价值计量、分类适当性、存在性、真实性各方面，形成对科目1501列报与披露的总体结论。",
}

_SUPPORTED_SECTIONS = set(_SECTION_PROMPTS.keys())


@router.post("/api/workpapers/{wp_id}/g1/ai/{section}")
async def g1_ai_generate(
    wp_id: str,
    section: str,
    body: G1AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> G1AiGenerateResponse:
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
        return G1AiGenerateResponse(content="", sources=[])
    return G1AiGenerateResponse(content=result, sources=[])


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
        logger.warning("G1 AI: project context 加载失败: %s", e)
    return ctx
