"""项目级配置中心路由

Requirements: 31.1-31.4

端点:
  GET  /api/projects/{pid}/config  — 获取项目配置
  PUT  /api/projects/{pid}/config  — 更新项目配置
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import Project, User

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/config",
    tags=["project-config"],
)


class ProjectConfigResponse(BaseModel):
    """项目配置响应"""
    report_standard: str | None = None  # soe / listed
    report_scope: str | None = None  # consolidated / standalone
    # consolidation_type 已移除（consol-tree-three-code-autobuild 需求 4.3）：
    # 合并方式由下级企业的与上级关系自动识别，见合并企业树接口的 mode 字段。
    amount_unit: str | None = None  # yuan / wan / qian
    note_template_type: str | None = None  # auto / soe / listed
    export_preferences: dict | None = None


class ProjectConfigUpdate(BaseModel):
    """项目配置更新请求"""
    report_standard: str | None = Field(None, description="报表标准: soe/listed")
    report_scope: str | None = Field(None, description="报表范围: consolidated/standalone")
    # 保留字段仅为显式拒写（需求 4.5）：传入非空值 ⇒ 400，而不是被静默忽略
    consolidation_type: str | None = Field(
        None, description="已停用：合并方式由下级企业的与上级关系自动识别，传入即 400",
    )
    amount_unit: str | None = Field(None, description="金额单位: yuan/wan/qian")
    note_template_type: str | None = Field(None, description="附注模板: auto/soe/listed")
    export_preferences: dict | None = Field(None, description="导出格式偏好")


@router.get("")
async def get_project_config(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取项目配置

    Requirements: 31.1
    """
    stmt = select(Project).where(Project.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    return {
        "report_standard": getattr(project, "template_type", None) or "soe",
        "report_scope": getattr(project, "report_scope", None) or "standalone",
        "amount_unit": getattr(project, "amount_unit", None) or "yuan",
        "note_template_type": "auto",
        "export_preferences": {},
    }


@router.put("")
async def update_project_config(
    project_id: UUID,
    body: ProjectConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新项目配置

    配置变更时自动标记受影响产物为 stale。
    Requirements: 31.1-31.4
    """
    stmt = select(Project).where(Project.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 需求 4.5：合并方式不再手工设置（先于任何写入校验，保证整单拒绝、无半写）
    if body.consolidation_type is not None:
        raise HTTPException(
            status_code=400,
            detail="合并方式由下级企业的与上级关系自动识别，不再手工设置",
        )

    changed_fields = []

    if body.report_standard is not None and hasattr(project, "template_type"):
        if project.template_type != body.report_standard:
            project.template_type = body.report_standard
            changed_fields.append("report_standard")

    if body.report_scope is not None and hasattr(project, "report_scope"):
        if project.report_scope != body.report_scope:
            project.report_scope = body.report_scope
            changed_fields.append("report_scope")

    if body.amount_unit is not None and hasattr(project, "amount_unit"):
        project.amount_unit = body.amount_unit
        changed_fields.append("amount_unit")

    await db.flush()

    # consol-tree-three-code-autobuild 需求 7.2：报表类型变化改变企业树（合并 ↔ 单户）⇒ 重算派生链接
    if "report_scope" in changed_fields:
        from app.services.group_links import sync_group_links_for

        await sync_group_links_for(db, project)

    # Mark affected artifacts as stale if report_standard / report_scope changed
    stale_count = 0
    if (
        "report_standard" in changed_fields
        or "report_scope" in changed_fields
    ):
        try:
            from app.services.report_note_sync_service import ReportNoteSyncService
            sync_svc = ReportNoteSyncService(db)
            # Get year from project context (use current year as default)
            from datetime import datetime
            year = datetime.now().year
            stale_count = await sync_svc.mark_notes_stale_for_report_change(project_id, year)
        except Exception as e:
            logger.warning("Failed to mark stale on config change: %s", e)

    await db.commit()

    return {
        "message": "配置已更新",
        "changed_fields": changed_fields,
        "stale_artifacts_marked": stale_count,
    }
