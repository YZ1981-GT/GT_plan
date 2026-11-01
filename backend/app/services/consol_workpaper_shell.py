"""薄底稿壳：为合并项目幂等创建 A3-CONSOL 的 WpIndex + WorkingPaper（批 6 / ADR-CRW-006）。

业务 JSON 不写 `parsed_data`（合并数据以 `consol_worksheet_data`、`consol_trial`、
`financial_report` 和 `consol_note_data` 为权威）。`file_path` 指向最近 immutable artifact。
壳接入负责人、复核、附件证据、回收站和归档；通用 `EvidenceLink.wp_id` 可直接引用本壳。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WpIndex, WorkingPaper, WpSourceType, WpFileStatus

WP_CODE = "A3-CONSOL"
WP_NAME = "合并工作底稿"
AUDIT_CYCLE = "A"
SOURCE_TYPE = WpSourceType.template


async def ensure_consol_workpaper_shell(
    db: AsyncSession,
    project_id: UUID,
    *,
    created_by: UUID | None = None,
    artifact_path: str | None = None,
) -> dict[str, Any]:
    """幂等创建或更新合并底稿壳。返回 ``{wp_index_id, working_paper_id, created}``。

    - 首次创建 WpIndex + WorkingPaper（file_path 指向 artifact 或占位）
    - 再次调用只更新 file_path（artifact 更新时）
    - 不写 parsed_data
    """
    now = datetime.now(timezone.utc)
    index = (await db.execute(
        sa.select(WpIndex).where(
            WpIndex.project_id == project_id,
            WpIndex.wp_code == WP_CODE,
            WpIndex.is_deleted == sa.false(),
        )
    )).scalar_one_or_none()

    created = False
    if index is None:
        index = WpIndex(
            id=uuid.uuid4(),
            project_id=project_id,
            wp_code=WP_CODE,
            wp_name=WP_NAME,
            audit_cycle=AUDIT_CYCLE,
            created_at=now,
            updated_at=now,
        )
        db.add(index)
        await db.flush()
        created = True

    paper = (await db.execute(
        sa.select(WorkingPaper).where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.wp_index_id == index.id,
            WorkingPaper.is_deleted == sa.false(),
        )
    )).scalar_one_or_none()

    if paper is None:
        paper = WorkingPaper(
            id=uuid.uuid4(),
            project_id=project_id,
            wp_index_id=index.id,
            file_path=artifact_path or f"consol://{project_id}/placeholder",
            source_type=SOURCE_TYPE,
            status=WpFileStatus.draft,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        db.add(paper)
        await db.flush()
        created = True
    elif artifact_path and paper.file_path != artifact_path:
        paper.file_path = artifact_path
        paper.updated_at = now
        await db.flush()

    return {
        "wp_index_id": str(index.id),
        "working_paper_id": str(paper.id),
        "wp_code": WP_CODE,
        "created": created,
    }


async def get_consol_workpaper_shell(
    db: AsyncSession, project_id: UUID,
) -> dict[str, Any] | None:
    """读取已有壳；不存在返回 None。"""
    index = (await db.execute(
        sa.select(WpIndex).where(
            WpIndex.project_id == project_id,
            WpIndex.wp_code == WP_CODE,
            WpIndex.is_deleted == sa.false(),
        )
    )).scalar_one_or_none()
    if index is None:
        return None
    paper = (await db.execute(
        sa.select(WorkingPaper).where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.wp_index_id == index.id,
            WorkingPaper.is_deleted == sa.false(),
        )
    )).scalar_one_or_none()
    if paper is None:
        return None
    return {
        "wp_index_id": str(index.id),
        "working_paper_id": str(paper.id),
        "wp_code": WP_CODE,
        "file_path": paper.file_path,
        "status": str(getattr(paper.status, "value", paper.status)),
        "review_status": str(getattr(paper.review_status, "value", paper.review_status)),
        "assigned_to": str(paper.assigned_to) if paper.assigned_to else None,
        "reviewer": str(paper.reviewer) if paper.reviewer else None,
    }


__all__ = [
    "WP_CODE",
    "WP_NAME",
    "ensure_consol_workpaper_shell",
    "get_consol_workpaper_shell",
]
