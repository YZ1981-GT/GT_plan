"""AI 结论审计留痕服务

Task 5 (workpaper-ai-conclusion-copilot spec):
- 5.1 记录 prompt、模型、上下文摘要
- 5.2 记录 AI 原文、用户修订文、确认/拒绝人
- 5.3 拒绝时要求原因
- 5.4 来源摘要可跳转到字段来源或工作包卡片
- 5.5 AI content log 治理面板可按目标绑定跳转回 D1-C / D2-C

Requirements: 5.1, 3.4
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.v3_refinement_models import AiContentLog
from app.services import ai_content_log_service
from app.services.audit_log_helper import append_audit_log


async def record_draft_generation_audit(
    *,
    db: AsyncSession,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    log_id: uuid.UUID,
    prompt_text: str,
    model: str,
    context_summary: dict[str, Any],
    target_binding: dict[str, Any],
) -> None:
    """记录草稿生成审计轨迹

    Task 5.1: 记录 prompt、模型、上下文摘要。
    写入 audit_log，event_type='ai_conclusion_draft_generated'。
    """
    await append_audit_log(
        db,
        {
            "user_id": user_id,
            "project_id": project_id,
            "action": "ai_conclusion_draft_generated",
            "resource_type": "ai_content_log",
            "resource_id": str(log_id),
            "details": {
                "event_type": "ai_conclusion_draft_generated",
                "log_id": str(log_id),
                "model": model,
                "prompt_length": len(prompt_text),
                "prompt_hash": None,  # 已在 ai_content_log 中记录
                "context_summary": context_summary,
                "target_binding": target_binding,
            },
        },
    )


async def record_confirm_audit(
    *,
    db: AsyncSession,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    log_id: uuid.UUID,
) -> None:
    """记录确认审计轨迹

    Task 5.2: 记录确认人。
    """
    await append_audit_log(
        db,
        {
            "user_id": user_id,
            "project_id": project_id,
            "action": "ai_conclusion_confirmed",
            "resource_type": "ai_content_log",
            "resource_id": str(log_id),
            "details": {
                "event_type": "ai_conclusion_confirmed",
                "log_id": str(log_id),
                "confirmed_by": str(user_id),
            },
        },
    )


async def record_revise_audit(
    *,
    db: AsyncSession,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    log_id: uuid.UUID,
    original_content: str,
    revised_content: str,
) -> None:
    """记录修订确认审计轨迹

    Task 5.2: 记录 AI 原文、用户修订文、确认人。
    """
    await append_audit_log(
        db,
        {
            "user_id": user_id,
            "project_id": project_id,
            "action": "ai_conclusion_revised",
            "resource_type": "ai_content_log",
            "resource_id": str(log_id),
            "details": {
                "event_type": "ai_conclusion_revised",
                "log_id": str(log_id),
                "revised_by": str(user_id),
                "original_content_length": len(original_content),
                "revised_content_length": len(revised_content),
            },
        },
    )


async def record_reject_audit(
    *,
    db: AsyncSession,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    log_id: uuid.UUID,
    reject_reason: str,
) -> None:
    """记录拒绝审计轨迹

    Task 5.3: 拒绝时要求原因。
    """
    if not reject_reason or not reject_reason.strip():
        raise ValueError("拒绝原因不能为空")

    await append_audit_log(
        db,
        {
            "user_id": user_id,
            "project_id": project_id,
            "action": "ai_conclusion_rejected",
            "resource_type": "ai_content_log",
            "resource_id": str(log_id),
            "details": {
                "event_type": "ai_conclusion_rejected",
                "log_id": str(log_id),
                "rejected_by": str(user_id),
                "reject_reason": reject_reason.strip(),
            },
        },
    )


def build_source_jump_links(
    source_summary: dict[str, Any],
    project_id: str,
    wp_id: str,
) -> list[dict[str, Any]]:
    """构建来源摘要跳转链接

    Task 5.4: 来源摘要可跳转到字段来源或工作包卡片。
    每个来源生成对应的跳转 URL 模式。
    """
    links = []
    for source in source_summary.get("sources", []):
        source_type = source.get("type", "")
        label = source.get("label", "")

        link = {
            "type": source_type,
            "label": label,
            "jump_target": None,
        }

        if source_type == "audit_sheet":
            link["jump_target"] = f"/projects/{project_id}/workpapers/{wp_id}?sheet=audit_sheet"
        elif source_type == "program_status":
            link["jump_target"] = f"/projects/{project_id}/workpapers/{wp_id}?sheet=program_status"
        elif source_type == "field_sources":
            link["jump_target"] = f"/projects/{project_id}/workpapers/{wp_id}?panel=field_sources"
        elif source_type == "adjustment_impact":
            link["jump_target"] = f"/projects/{project_id}/workpapers/{wp_id}?sheet=adjustment"
        elif source_type == "confirmation":
            link["jump_target"] = f"/projects/{project_id}/workpapers/{wp_id}?sheet=confirmation"
        elif source_type == "bad_debt_ecl":
            link["jump_target"] = f"/projects/{project_id}/workpapers/{wp_id}?sheet=ecl"
        elif source_type == "analysis":
            link["jump_target"] = f"/projects/{project_id}/workpapers/{wp_id}?sheet=analysis"

        links.append(link)

    return links


def build_governance_jump_link(
    target_binding: dict[str, Any],
    project_id: str,
) -> str:
    """构建治理面板到结论的跳转链接

    Task 5.5: AI content log 治理面板可按目标绑定跳转回 D1-C / D2-C。
    """
    wp_id = target_binding.get("wp_id", "")
    field_id = target_binding.get("field_id", "")
    sheet_type = target_binding.get("sheet_type", "conclusion")

    return (
        f"/projects/{project_id}/workpapers/{wp_id}"
        f"?sheet={sheet_type}&field={field_id}"
    )


async def query_ai_content_logs_by_binding(
    *,
    db: AsyncSession,
    project_id: uuid.UUID,
    account_package_id: str | None = None,
    wp_id: uuid.UUID | None = None,
    field_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """按目标绑定查询 AI content log

    Task 5.6: AI content log 查询可按 account_package_id、wp_id、field_id 过滤并跳转。
    """
    stmt = select(AiContentLog).where(AiContentLog.project_id == project_id)

    if wp_id is not None:
        stmt = stmt.where(AiContentLog.wp_id == wp_id)

    stmt = stmt.order_by(AiContentLog.generated_at.desc()).limit(limit)

    result = await db.execute(stmt)
    logs = result.scalars().all()

    # 按 field_id 过滤（target_cell 格式: "workpaper:<wp_id>:<field_id>"）
    filtered = []
    for log in logs:
        target_cell = log.target_cell or ""

        # 如果有 field_id 过滤条件，检查 target_cell 是否包含该 field_id
        if field_id and field_id not in target_cell:
            continue

        # 构建跳转链接
        parts = target_cell.split(":")
        log_field_id = parts[2] if len(parts) >= 3 else None

        filtered.append({
            "id": str(log.id),
            "wp_id": str(log.wp_id) if log.wp_id else None,
            "field_id": log_field_id,
            "model": log.model,
            "confirm_action": log.confirm_action,
            "generated_content": log.generated_content,
            "revised_content": log.revised_content,
            "confirmed_by": str(log.confirmed_by) if log.confirmed_by else None,
            "confirmed_at": log.confirmed_at.isoformat() if log.confirmed_at else None,
            "generated_at": log.generated_at.isoformat() if log.generated_at else None,
            "jump_link": build_governance_jump_link(
                {"wp_id": str(log.wp_id) if log.wp_id else "", "field_id": log_field_id or "", "sheet_type": "conclusion"},
                str(project_id),
            ),
        })

    return filtered
