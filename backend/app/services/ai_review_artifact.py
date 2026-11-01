"""耐久批量复核的逐项产物持久化。

Finding 与 item 终态使用调用方同一事务；ID 由 generation_id 派生，重试不会
创建第二组记录。这里不提交事务，最终 lease fence 失败时调用方会整体回滚。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_models import AIConfirmationStatus, AIContent, AIContentType


def finding_id(generation_id: UUID, ordinal: int) -> UUID:
    return uuid5(NAMESPACE_URL, f"gt-ai-task:{generation_id}:finding:{ordinal}")


async def persist_review_findings(
    db: AsyncSession,
    *,
    project_id: UUID,
    workpaper_id: UUID,
    job_id: UUID,
    generation_id: UUID,
    wp_code: str,
    sheet_name: str,
    model_used: str,
    prompt_source: str,
    findings: list[Any],
) -> list[dict[str, Any]]:
    """写入可更新状态/可导出的 finding，并返回使用同一稳定 ID 的响应。"""
    result: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    for ordinal, finding in enumerate(findings):
        stable_id = finding_id(generation_id, ordinal)
        data_sources = {
            "sheet_name": sheet_name,
            "risk_level": finding.risk_level,
            "pass_status": str(finding.pass_status),
            "category": finding.category,
            "session_id": str(job_id),
            "job_id": str(job_id),
            "generation_id": str(generation_id),
            "finding_status": "pending",
            "wp_code": wp_code,
            "sheet_location": finding.sheet_location,
            "suggestion": finding.suggestion,
            "prompt_source": prompt_source,
        }
        existing = await db.get(AIContent, stable_id)
        if existing is None:
            db.add(AIContent(
                id=stable_id,
                project_id=project_id,
                workpaper_id=workpaper_id,
                content_type=AIContentType.review_finding,
                content_text=finding.description,
                data_sources=data_sources,
                generation_model=model_used,
                generation_time=now,
                confidence_level=None,
                confirmation_status=AIConfirmationStatus.pending,
                is_deleted=False,
            ))
        elif (
            existing.project_id != project_id
            or existing.workpaper_id != workpaper_id
            or existing.content_text != finding.description
            or (existing.data_sources or {}).get("generation_id") != str(generation_id)
        ):
            raise RuntimeError("复核 finding 稳定 ID 与既有产物冲突")
        result.append({
            "id": str(stable_id),
            "description": finding.description,
            "risk_level": finding.risk_level,
            "pass_status": finding.pass_status,
            "category": finding.category,
            "sheet_location": finding.sheet_location,
            "suggestion": finding.suggestion,
        })
    await db.flush()
    return result
