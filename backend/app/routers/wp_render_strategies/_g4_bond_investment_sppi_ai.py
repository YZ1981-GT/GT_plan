"""G4 债权投资(SPPI组) — AI 辅助生成端点

POST /api/workpapers/{wp_id}/g4-sppi/ai/{section}

sections:
  - business-model-conclusion   (业务模式分析结论)
  - sppi-bond-conclusion        (SPPI债券投资结论)
  - sppi-financial-conclusion   (SPPI银行理财产品结论)
  - inventory-conclusion        (盘点表结论)
  - reconciliation-conclusion   (倒轧表结论)
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

router = APIRouter(tags=["g4-sppi-ai"])

# AI 生成超时（秒）
_AI_TIMEOUT = 30.0


class G4SppiAiGenerateRequest(BaseModel):
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class G4SppiAiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 G4《债权投资》的SPPI组工作底稿。
科目1501债权投资（借方/资产类），以摊余成本计量的金融资产（CAS22分类为AC类）。

本组底稿核心关注：
- G4-5 业务模式分析：CAS22要求的业务模式三分类判定（AC/FVOCI/FVTPL）
- G4-6 合同现金流量特征分析（SPPI测试）：验证合同现金流量是否仅为对本金和利息的支付
- G4-7 有价证券盘点表：证券实物盘点记录，确认存在性
- G4-8 盘点倒轧表：将盘点日实存调节至资产负债表日，验证完整性

审计逻辑链：业务模式(AC) + SPPI通过 → 确认以摊余成本计量 → 盘点确认存在性 → 倒轧确认完整性。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "business-model-conclusion": (
        "请生成G4-5业务模式分析的审计结论，评价以下方面：\n"
        "1. 被审计单位管理债权投资的业务模式是否为'以收取合同现金流量为目标'(AC分类)\n"
        "2. 是否存在大额频繁出售、交易性管理、基于公允价值管理等非AC特征\n"
        "3. 是否需要分拆次级组合分别确定业务模式\n"
        "4. 综合判定结论及分类依据\n"
        "注意：债权投资(G4)科目应为AC分类，若非AC需提示分类异常。"
    ),
    "sppi-bond-conclusion": (
        "请生成G4-6合同现金流量特征分析（部分一：债券投资）的审计结论，评价以下方面：\n"
        "1. 各项债券投资的合同现金流量是否仅为对本金和以未偿付本金为基础的利息的支付\n"
        "2. 是否存在提前回售选择权/展期选择权/权益转换特征/杠杆因素等复杂条款\n"
        "3. 有复杂条款的投资项目其SPPI判定是否合理\n"
        "4. 整体SPPI测试结论"
    ),
    "sppi-financial-conclusion": (
        "请生成G4-6合同现金流量特征分析（部分二：银行理财产品）的审计结论，评价以下方面：\n"
        "1. 各银行理财产品是否满足'保本保收益'条件（第一步）\n"
        "2. 浮动收益部分是否属于'不现实'情形（第二步）\n"
        "3. 穿透底层资产后其SPPI特征是否满足（第三步）\n"
        "4. 三步法综合判断结论"
    ),
    "inventory-conclusion": (
        "请生成G4-7有价证券盘点表的审计结论，评价以下方面：\n"
        "1. 盘点程序执行的充分性（盘点范围、参与人员、盘点日期选择）\n"
        "2. 盘点结果与账面记录的一致性\n"
        "3. 有价证券的存在性和权属确认\n"
        "4. 盘点过程中发现的异常情况及处理"
    ),
    "reconciliation-conclusion": (
        "请生成G4-8盘点倒轧表的审计结论，评价以下方面：\n"
        "1. 盘点日到资产负债表日期间增减变动的合理性\n"
        "2. 资产负债表日实存与账面结存的差异分析\n"
        "3. 差异原因是否合理，是否需要调整\n"
        "4. 通过倒轧程序确认的有价证券完整性结论"
    ),
}

_SUPPORTED_SECTIONS = set(_SECTION_PROMPTS.keys())


@router.post("/api/workpapers/{wp_id}/g4-sppi/ai/{section}")
async def g4_sppi_ai_generate(
    wp_id: str,
    section: str,
    body: G4SppiAiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> G4SppiAiGenerateResponse:
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
        return G4SppiAiGenerateResponse(content="", sources=[])
    return G4SppiAiGenerateResponse(content=result, sources=[])


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
        logger.warning("G4 SPPI AI: project context 加载失败: %s", e)
    return ctx
