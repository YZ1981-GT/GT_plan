"""模板复制 API 路由

POST /api/projects/{project_id}/workpapers/template-copy
  → CopyResult | list[CopyResult]

参数:
- source_wp_id: 单底稿复制源 ID
- source_project_id + audit_cycle: 批量复制整个循环
- overwrite: 是否覆盖目标已有同 wp_code 底稿

设计原则：
- router 层统一 commit（service 只 flush）
- 单底稿复制返回 CopyResult，批量返回 list[CopyResult]

Requirements: 7.1, 7.4, 7.5
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers",
    tags=["wp-template-copy"],
)


# ─── Request Schema ───────────────────────────────────────────────────────────


class TemplateCopyRequest(BaseModel):
    """模板复制请求体"""

    source_wp_id: Optional[UUID] = Field(
        None, description="单底稿复制：源底稿 ID"
    )
    source_project_id: Optional[UUID] = Field(
        None, description="批量复制：源项目 ID"
    )
    audit_cycle: Optional[str] = Field(
        None, description="批量复制：审计循环代号"
    )
    overwrite: bool = Field(
        False, description="是否覆盖目标项目已有同 wp_code 底稿"
    )


# ─── 模板复制端点 ─────────────────────────────────────────────────────────────


@router.post("/template-copy")
async def template_copy(
    project_id: UUID,
    body: TemplateCopyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """跨项目模板复制

    两种模式：
    1. 单底稿复制：指定 source_wp_id
    2. 批量复制：指定 source_project_id + audit_cycle（复制整个循环）

    复制后：状态 draft、清除复核状态、清除业务数据保留结构。
    """
    from app.models.workpaper_models import WorkingPaper, WpIndex
    from app.services.wp_export.template_copier import TemplateCopier

    copier = TemplateCopier()

    # 获取目标项目已有 wp_code 集合
    existing_result = await db.execute(
        sa.select(WpIndex.wp_code)
        .join(WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == sa.false(),
        )
    )
    existing_codes = {row[0] for row in existing_result.all() if row[0]}

    # ─── 模式 1: 单底稿复制 ──────────────────────────────────────────────
    if body.source_wp_id:
        source_wp_data = await _load_source_wp(db, body.source_wp_id)
        if source_wp_data is None:
            raise HTTPException(status_code=404, detail="源底稿不存在")

        result = copier.copy_single(
            source_wp=source_wp_data,
            target_project_id=project_id,
            overwrite=body.overwrite,
            existing_codes=existing_codes,
        )

        # 持久化目标底稿记录
        if result.status == "copied" and hasattr(result, "target_record"):
            await _persist_copy_result(db, result, project_id)

        await db.commit()
        return result.model_dump(mode="json")

    # ─── 模式 2: 批量复制整个循环 ────────────────────────────────────────
    if body.source_project_id and body.audit_cycle:
        source_wps = await _load_source_cycle(
            db, body.source_project_id, body.audit_cycle
        )
        if not source_wps:
            raise HTTPException(
                status_code=404,
                detail=f"源项目循环 {body.audit_cycle} 下无可复制底稿",
            )

        results = copier.copy_cycle(
            source_workpapers=source_wps,
            target_project_id=project_id,
            audit_cycle=body.audit_cycle,
            overwrite=body.overwrite,
            existing_codes=existing_codes,
        )

        # 持久化所有复制成功的记录
        for r in results:
            if r.status == "copied" and hasattr(r, "target_record"):
                await _persist_copy_result(db, r, project_id)

        await db.commit()
        return [r.model_dump(mode="json") for r in results]

    # 参数不完整
    raise HTTPException(
        status_code=422,
        detail="请提供 source_wp_id（单底稿）或 source_project_id + audit_cycle（批量）",
    )


# ─── Private Helpers ──────────────────────────────────────────────────────────


async def _load_source_wp(db: AsyncSession, wp_id: UUID) -> dict | None:
    """加载源底稿数据，返回 TemplateCopier 需要的 dict 格式。"""
    from app.models.workpaper_models import WorkingPaper, WpIndex

    result = await db.execute(
        sa.select(WorkingPaper, WpIndex)
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.id == wp_id,
            WorkingPaper.is_deleted == sa.false(),
        )
    )
    row = result.first()
    if not row:
        return None

    wp, idx = row
    return {
        "wp_code": idx.wp_code,
        "wp_name": idx.wp_name or "",
        "audit_cycle": idx.audit_cycle or "",
        "status": wp.status,
        "review_status": wp.review_status.value if wp.review_status else "not_submitted",
        "is_deleted": False,
        "file_format": "xlsx",
        "data": wp.parsed_data or {},
        "schema": None,
        "wp_id": wp.id,
        "project_id": wp.project_id,
    }


async def _load_source_cycle(
    db: AsyncSession, source_project_id: UUID, audit_cycle: str
) -> list[dict]:
    """加载源项目指定循环的全部底稿。"""
    from app.models.workpaper_models import WorkingPaper, WpIndex

    result = await db.execute(
        sa.select(WorkingPaper, WpIndex)
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.project_id == source_project_id,
            WorkingPaper.is_deleted == sa.false(),
            WpIndex.audit_cycle == audit_cycle,
        )
    )
    rows = result.all()

    return [
        {
            "wp_code": idx.wp_code,
            "wp_name": idx.wp_name or "",
            "audit_cycle": idx.audit_cycle or "",
            "status": wp.status,
            "review_status": wp.review_status.value if wp.review_status else "not_submitted",
            "is_deleted": False,
            "file_format": "xlsx",
            "data": wp.parsed_data or {},
            "schema": None,
            "wp_id": wp.id,
            "project_id": wp.project_id,
        }
        for wp, idx in rows
    ]


async def _persist_copy_result(db: AsyncSession, copy_result, project_id: UUID) -> None:
    """将复制结果持久化为目标项目的 wp_index + working_paper 记录。

    简化实现：创建 wp_index 和 working_paper 记录。
    """
    import uuid as uuid_mod

    from app.models.workpaper_models import WorkingPaper, WpIndex

    target_record = getattr(copy_result, "target_record", None)
    if not target_record:
        return

    # 创建 wp_index 记录
    new_index_id = uuid_mod.uuid4()
    wp_index = WpIndex(
        id=new_index_id,
        wp_code=target_record["wp_code"],
        wp_name=target_record.get("wp_name", ""),
        audit_cycle=target_record.get("audit_cycle", ""),
        project_id=project_id,
        is_deleted=False,
    )
    db.add(wp_index)

    # 创建 working_paper 记录
    working_paper = WorkingPaper(
        id=target_record["wp_id"],
        project_id=project_id,
        wp_index_id=new_index_id,
        file_version=1,
        status="draft",
        review_status="not_submitted",
        is_deleted=False,
        file_path="",
        parsed_data=target_record.get("data", {}),
    )
    db.add(working_paper)

    await db.flush()
