"""K6 持有待售资产和负债 — AI 辅助生成端点

POST /api/workpapers/{wp_id}/k6/ai-generate

sections: classification-conclusion / impairment-conclusion / no-longer-eval / overall-opinion

科目 1481 持有待售资产（借方/资产类） + 2605 持有待售负债（贷方/负债类）。
核心认定：分类(CAS42五条件) + 计价(减值孰低法) + 存在性(不再满足重分类)。
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

router = APIRouter(tags=["k6-ai"])


class K6AiGenerateRequest(BaseModel):
    section: str
    existingContent: str = ""
    relatedContext: dict[str, Any] = {}


class K6AiGenerateResponse(BaseModel):
    content: str
    sources: list[str] = []


_SUPPORTED_SECTIONS = {
    "classification-conclusion",
    "impairment-conclusion",
    "no-longer-eval",
    "overall-opinion",
}

_SYSTEM_PROMPT = """你是一位资深注册会计师（CPA），正在协助编制审计底稿 K6《持有待售资产和负债》。
科目1481持有待售资产（借方/资产类）+ 2605持有待售负债（贷方/负债类）。

核心关注：
- **混合口径**：
  - 持有待售资产（借方/资产类）：期末 = 期初 + 增加 - 减少 - 减值
  - 持有待售负债（贷方/负债类）：期末 = 期初 + 增加 - 减少
- **CAS42五条件分类判断**：
  ① 可立即出售（在当前状态下可立即出售）
  ② 已就出售作出决议（管理层已作出书面决议）
  ③ 已与购买方签订不可撤销转让协议
  ④ 出售预计一年内完成
  ⑤ 售价合理，不太可能变更或撤销
  全部满足 → 分类为持有待售；任一不满足 → 不得分类
- **减值孰低法**：
  - 公允价值净额 = 公允价值 - 预计出售费用
  - 减值金额 = MAX(0, 账面价值 - 公允价值净额)
  - 处置组减值先抵减商誉，再按比例分摊至组内非流动资产
- **不再满足持有待售条件**：
  - 按较低者计量：可收回金额 vs 假设从未分类的账面价值
  - 差额计入当期损益
- 分类为持有待售后停止折旧/摊销

相关准则：CAS42持有待售的非流动资产、处置组和终止经营。

输出要求：中文、审计专业用语、直接输出正文、简洁适合底稿。"""

_SECTION_PROMPTS: dict[str, str] = {
    "classification-conclusion": (
        "请生成K6-4初始确认检查表的分类判断结论。综合评价："
        "①逐条核对CAS42五条件是否满足（可立即出售/已作出决议/已签协议/一年内完成/售价合理）"
        "②分类判断结果（全部满足→分类为持有待售/存在不满足→不得分类）"
        "③分类日确定的合理性（五条件同时满足之日）"
        "④分类后是否已停止折旧/摊销"
        "⑤初始计量金额的正确性（以分类日账面价值与公允价值净额孰低者计量）"
        "⑥对审计意见的影响及后续程序建议。"
        "确保符合CAS42分类判断框架。"
    ),
    "impairment-conclusion": (
        "请生成K6-5减值准备测试表的审计结论。综合评价："
        "①公允价值确定方法的合理性（市场法/收益法/成本法）"
        "②预计出售费用的估计是否恰当（中介费/税费/其他直接费用）"
        "③公允价值净额 = 公允价值 - 出售费用 计算是否正确"
        "④减值金额 = MAX(0, 账面价值 - 公允价值净额) 孰低法是否正确"
        "⑤与K6-1审定表减值准备行的交叉验证是否相符"
        "⑥处置组减值分摊的合理性（先抵商誉、再按比例）"
        "⑦后续期间公允价值恢复时减值转回的处理。"
    ),
    "no-longer-eval": (
        "请生成K6-7不再满足持有待售检查表的评价结论。综合评价："
        "①不再满足持有待售条件的原因（出售计划变更/协议解除/超出一年/市场变化）"
        "②重分类日的确定是否正确"
        "③重分类后计量金额的正确性："
        "  - 可收回金额（公允价值减出售费用净额 vs 使用价值孰高）"
        "  - 假设从未分类的账面价值（补提应折旧/摊销后的金额）"
        "  - 按两者较低计量"
        "④差额（调整金额）是否正确计入当期损益"
        "⑤后续是否恢复正常折旧/摊销"
        "⑥对审计意见的影响及后续程序建议。"
    ),
    "overall-opinion": (
        "请生成K6-1审定表底部的审计综合意见。综合评价持有待售资产和负债科目整体的"
        "分类正确性（CAS42五条件是否满足）、计价和分摊（减值孰低法计量是否恰当）、"
        "存在性（持有待售分类是否仍满足）、完整性（是否遗漏应分类的项目）、"
        "列报与披露的恰当性（CAS42披露要求）。"
        "说明是否发现需要调整的重大事项，审定数与未审数的主要差异原因。"
        "重点评价：五条件分类判断的合理性、减值孰低法计量的充分性、"
        "处置组分摊的正确性、不再满足重分类处理的恰当性。"
    ),
}


@router.post("/api/workpapers/{wp_id}/k6/ai-generate")
async def k6_ai_generate(
    wp_id: str,
    body: K6AiGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> K6AiGenerateResponse:
    if not getattr(settings, "WP_AI_SERVICE_ENABLED", True):
        raise HTTPException(503, "AI 服务未启用")
    if body.section not in _SUPPORTED_SECTIONS:
        raise HTTPException(400, f"不支持的 section: {body.section}。支持: {sorted(_SUPPORTED_SECTIONS)}")

    project_context = await _load_project_context(wp_id, db)
    user_prompt = _build_user_prompt(body.section, body.existingContent, body.relatedContext, project_context)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    result = await chat_completion(messages=messages, temperature=0.3, max_tokens=2000)
    if isinstance(result, str) and result.startswith("["):
        return K6AiGenerateResponse(content="", sources=[])
    return K6AiGenerateResponse(content=result, sources=[])


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
    except Exception as e:
        logger.warning("K6 AI: project context 加载失败: %s", e)
    return ctx
