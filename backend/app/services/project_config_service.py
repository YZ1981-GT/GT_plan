"""项目级配置服务。

服务层只负责读取、校验后的字段写入和 ``flush``；事务提交或回滚由路由拥有，
从而保证项目配置与其后续的企业树、过期标记处在同一事务中。
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.schemas.project_config import (
    ProjectConfigResponse,
    ProjectConfigUpdate,
    ProjectConfigUpdateResponse,
)

logger = logging.getLogger(__name__)


class ProjectConfigService:
    """项目配置的唯一读写服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_config(self, project_id: UUID) -> ProjectConfigResponse:
        return self._response_for(await self._load_project(project_id))

    async def update_config(
        self,
        project_id: UUID,
        config: ProjectConfigUpdate,
    ) -> ProjectConfigUpdateResponse:
        """更新项目配置并只 flush，不提交事务。"""
        project = await self._load_project(project_id)

        # 合并方式已由企业树派生；保持旧接口的显式拒绝语义，且在任何写入前失败。
        if config.consolidation_type is not None:
            raise HTTPException(
                status_code=400,
                detail="合并方式由下级企业的与上级关系自动识别，不再手工设置",
            )

        if config.report_scope is not None:
            from app.services.group_topology_lock import lock_topology_years
            from app.services.project_audit_year import resolve_project_audit_year

            year_hint = resolve_project_audit_year(project)
            await lock_topology_years(self._db, [year_hint])
            await self._db.refresh(project)
            if resolve_project_audit_year(project) != year_hint:
                raise HTTPException(status_code=409, detail="项目年度已变化，请刷新后重试")

        changed_fields: list[str] = []
        if config.report_standard is not None and project.template_type != config.report_standard:
            project.template_type = config.report_standard
            changed_fields.append("report_standard")
        if config.report_scope is not None and project.report_scope != config.report_scope:
            project.report_scope = config.report_scope
            changed_fields.append("report_scope")
        if config.amount_unit is not None and project.amount_unit != config.amount_unit:
            project.amount_unit = config.amount_unit
            changed_fields.append("amount_unit")

        await self._db.flush()

        if "report_scope" in changed_fields:
            from app.services.group_links import sync_group_links_for

            await sync_group_links_for(self._db, project)

        stale_count = await self._mark_stale_for_report_change(project_id, changed_fields)
        return ProjectConfigUpdateResponse(
            **self._response_for(project).model_dump(),
            changed_fields=changed_fields,
            stale_artifacts_marked=stale_count,
        )

    async def _load_project(self, project_id: UUID) -> Project:
        project = (
            await self._db.execute(
                select(Project).where(
                    Project.id == project_id,
                    Project.is_deleted.is_(False),
                )
            )
        ).scalar_one_or_none()
        if project is None:
            raise HTTPException(status_code=404, detail="项目不存在")
        return project

    @staticmethod
    def _response_for(project: Project) -> ProjectConfigResponse:
        """从 ORM 的明确字段构造配置响应，不做动态属性兜底。"""
        return ProjectConfigResponse(
            project_id=project.id,
            report_standard=project.template_type or "soe",
            report_scope=project.report_scope or "standalone",
            amount_unit=project.amount_unit,
            note_template_type="auto",
            export_preferences={},
        )

    async def _mark_stale_for_report_change(
        self,
        project_id: UUID,
        changed_fields: list[str],
    ) -> int:
        if not ({"report_standard", "report_scope"} & set(changed_fields)):
            return 0
        try:
            from app.services.project_audit_year import fetch_project_audit_year
            from app.services.report_note_sync_service import ReportNoteSyncService

            year = await fetch_project_audit_year(self._db, project_id)
            # 保存点：标记失败时只回滚这一步，PG 外层事务不会停在 aborted 而让配置提交失败。
            async with self._db.begin_nested():
                return await ReportNoteSyncService(self._db).mark_notes_stale_for_report_change(
                    project_id,
                    year if year is not None else 0,
                )
        except Exception as exc:  # 保留既有 best-effort 行为，配置写入不能被陈旧标记阻断。
            logger.warning("Failed to mark stale on config change: %s", exc)
            return 0
