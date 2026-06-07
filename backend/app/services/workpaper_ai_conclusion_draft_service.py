"""AI 结论草稿生成服务

Task 2.2–2.5 (workpaper-ai-conclusion-copilot spec):
- 调用既有 AI 服务生成结论草稿
- 写入 ai_content_log_service（pending 状态）
- 目标绑定：account_package_id, wp_id, sheet_type=conclusion, field_id
- 返回 pending log id、目标绑定和来源摘要

Requirements: 1.1, 1.2, 1.3, 2.1, 2.5
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import ai_content_log_service
from app.services.llm_client import chat_completion
from app.services.workpaper_ai_conclusion_context_service import (
    AIConclusionContext,
    WorkpaperAIConclusionContextService,
)
from app.services.workpaper_ai_conclusion_prompts import build_conclusion_prompt

logger = logging.getLogger(__name__)


@dataclass
class ConclusionDraftResult:
    """结论草稿生成结果"""

    log_id: uuid.UUID
    target_binding: dict[str, Any]
    source_summary: dict[str, Any]
    missing: list[dict[str, Any]]
    generated_content: str


async def generate_conclusion_draft(
    *,
    db: AsyncSession,
    project_id: uuid.UUID,
    account_package_id: str,
    wp_id: uuid.UUID,
    field_id: str,
    user_id: uuid.UUID,
    account_name: str | None = None,
) -> ConclusionDraftResult:
    """生成 AI 结论草稿并写入 ai_content_log

    流程：
    1. build_context 组装结构化上下文
    2. build_conclusion_prompt 构造 prompt
    3. chat_completion 调用 LLM
    4. ai_content_log_service.create 写入 pending 日志
    5. 返回 log_id、目标绑定和来源摘要

    Args:
        db: 数据库会话
        project_id: 项目 UUID
        account_package_id: 工作包 ID（如 D1_fixed_assets）
        wp_id: 底稿 UUID
        field_id: 目标字段 ID（如 d1.conclusion.overall_conclusion）
        user_id: 触发生成的用户 UUID
        account_name: 科目名称（可选，缺失时从 package_id 推断）

    Returns:
        ConclusionDraftResult 包含 log_id、目标绑定、来源摘要和 missing
    """
    # 1. 组装上下文
    context_service = WorkpaperAIConclusionContextService(db)
    context = await context_service.build_context(project_id, account_package_id)

    # 推断科目名称
    if not account_name:
        account_name = account_package_id.replace("_", " ").title()

    # 2. 构造 prompt
    context_dict = context.to_dict()
    prompt_text = build_conclusion_prompt(
        account_name=account_name,
        account_package_id=account_package_id,
        context=context_dict,
        missing=context.missing,
    )
    prompt_hash = hashlib.sha256(prompt_text.encode()).hexdigest()

    # 3. 调用 LLM（含离线降级）
    messages = [
        {"role": "system", "content": prompt_text},
        {"role": "user", "content": f"请为 {account_name} 科目生成 {context.conclusion_sheet} 结论草稿。"},
    ]
    try:
        ai_response = await chat_completion(messages=messages, temperature=0.3, max_tokens=2000)
    except Exception as e:
        logger.warning("LLM unavailable, returning structured outline: %s", e)
        ai_response = _build_fallback_outline(context, account_name)

    # 4. 写入 ai_content_log（pending 状态）
    content_hash = hashlib.sha256(ai_response.encode()).hexdigest()

    # target_cell 格式：workpaper:<wp_id>:<field_id>
    target_cell = f"workpaper:{wp_id}:{field_id}"

    ai_log = await ai_content_log_service.create(
        db=db,
        project_id=project_id,
        user_id=user_id,
        instance_type="workpaper",
        instance_id=wp_id,
        target_cell=field_id,
        model="qwen3.5-27b",
        prompt_hash=prompt_hash,
        content_hash=content_hash,
        generated_content=ai_response,
        confidence=None,
        wp_id=wp_id,
    )

    # 5. 构建目标绑定和来源摘要
    target_binding = {
        "account_package_id": account_package_id,
        "wp_id": str(wp_id),
        "sheet_type": "conclusion",
        "field_id": field_id,
    }

    source_summary = _build_source_summary(context)

    return ConclusionDraftResult(
        log_id=ai_log.id,
        target_binding=target_binding,
        source_summary=source_summary,
        missing=context.missing,
        generated_content=ai_response,
    )


def _build_source_summary(context: AIConclusionContext) -> dict[str, Any]:
    """构建来源摘要（供 UI 展示引用了哪些数据源）"""
    sources: list[dict[str, Any]] = []

    if context.audit_sheet_summary:
        sources.append({
            "type": "audit_sheet",
            "label": "审定表",
            "available": True,
        })

    if context.program_status_summary:
        sources.append({
            "type": "program_status",
            "label": "程序状态",
            "available": True,
            "detail": {
                "total": context.program_status_summary.get("total", 0),
                "completed": context.program_status_summary.get("completed", 0),
            },
        })

    if context.field_sources:
        sources.append({
            "type": "field_sources",
            "label": "字段来源",
            "available": True,
        })

    if context.adjustment_impact:
        sources.append({
            "type": "adjustment_impact",
            "label": "调整影响",
            "available": True,
        })

    if context.confirmation_summary:
        sources.append({
            "type": "confirmation",
            "label": "函证摘要",
            "available": True,
        })

    if context.bad_debt_ecl:
        sources.append({
            "type": "bad_debt_ecl",
            "label": "坏账/ECL",
            "available": True,
        })

    if context.analysis_summary:
        sources.append({
            "type": "analysis",
            "label": "分析程序",
            "available": True,
        })

    return {
        "wp_code": context.wp_code,
        "conclusion_sheet": context.conclusion_sheet,
        "sources": sources,
        "source_count": len(sources),
    }


def _build_fallback_outline(context: AIConclusionContext, account_name: str) -> str:
    """LLM 不可用时生成结构化结论模板（中文）

    基于已有上下文数据填充框架，而非留空。
    """
    lines: list[str] = []
    lines.append(f"# {account_name} 科目结论草稿（离线模板）\n")
    lines.append("> ⚠️ 本草稿由离线模板生成，LLM 服务暂不可用。请在 LLM 恢复后重新生成。\n")

    # 1. 审计目标
    lines.append("## 一、审计目标\n")
    lines.append(f"验证 {account_name} 科目期末余额的存在性、完整性、准确性和列报。\n")

    # 2. 已执行程序
    lines.append("## 二、已执行程序\n")
    if context.program_status_summary:
        total = context.program_status_summary.get("total", 0)
        completed = context.program_status_summary.get("completed", 0)
        pending = context.program_status_summary.get("pending", 0)
        lines.append(f"- 程序总数：{total}")
        lines.append(f"- 已完成：{completed}")
        lines.append(f"- 待执行：{pending}")
        rate = context.program_status_summary.get("completion_rate", 0)
        lines.append(f"- 完成率：{rate:.0%}\n")
    else:
        lines.append("- （程序状态数据不可用）\n")

    # 3. 关键发现
    lines.append("## 三、关键发现\n")
    if context.audit_sheet_summary:
        lines.append("- 审定表数据已获取，待人工补充差异分析。")
    if context.adjustment_impact and context.adjustment_impact.get("has_adjustments"):
        lines.append("- 存在审计调整分录，需关注调整对期末余额的影响。")
    if context.confirmation_summary and context.confirmation_summary.get("status") != "not_applicable":
        lines.append("- 函证数据已获取，待补充覆盖率和差异金额分析。")
    if context.bad_debt_ecl and context.bad_debt_ecl.get("has_ecl_data"):
        lines.append("- 坏账/ECL 分析数据已获取，待补充减值测算结论。")
    lines.append("")

    # 4. 结论
    lines.append("## 四、结论\n")
    lines.append("（待 LLM 生成具体结论，或由审计人员手工填写。）\n")

    # 5. 缺失资料
    lines.append("## 五、缺失资料\n")
    if context.missing:
        for item in context.missing:
            source = item.get("source", "未知")
            reason = item.get("reason", "")
            impact = item.get("impact", "")
            lines.append(f"- [{source}] {reason}：{impact}")
    else:
        lines.append("- （无缺失资料）")
    lines.append("")

    return "\n".join(lines)
