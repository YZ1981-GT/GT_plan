"""团队委派服务

Phase 9 Task 1.4: 项目团队委派 CRUD + 通知推送
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.staff_models import ProjectAssignment, StaffMember
from app.models.core import Notification, Project

logger = logging.getLogger(__name__)


class AssignmentService:
    """项目团队委派服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_assignments(self, project_id: UUID) -> list[dict]:
        """获取项目的团队委派列表"""
        q = (
            sa.select(
                ProjectAssignment,
                StaffMember.name.label("staff_name"),
                StaffMember.title.label("staff_title"),
                StaffMember.employee_no,
            )
            .join(StaffMember, ProjectAssignment.staff_id == StaffMember.id)
            .where(
                ProjectAssignment.project_id == project_id,
                ProjectAssignment.is_deleted == False,  # noqa
            )
            .order_by(ProjectAssignment.assigned_at)
        )
        rows = (await self.db.execute(q)).all()
        results = []
        for row in rows:
            pa = row[0]
            results.append({
                "id": str(pa.id),
                "project_id": str(pa.project_id),
                "staff_id": str(pa.staff_id),
                "role": pa.role,
                "assigned_cycles": pa.assigned_cycles,
                "assigned_at": str(pa.assigned_at) if pa.assigned_at else None,
                "staff_name": row.staff_name,
                "staff_title": row.staff_title,
                "employee_no": row.employee_no,
            })
        return results

    async def save_assignments(
        self,
        project_id: UUID,
        assignments: list[dict],
        assigned_by: UUID | None = None,
    ) -> list[ProjectAssignment]:
        """批量保存委派（先软删除旧的，再插入新的）"""
        now = datetime.now(timezone.utc)

        # 软删除现有委派
        await self.db.execute(
            sa.update(ProjectAssignment)
            .where(
                ProjectAssignment.project_id == project_id,
                ProjectAssignment.is_deleted == False,  # noqa
            )
            .values(is_deleted=True, deleted_at=now)
        )

        # 插入新委派
        created = []
        for a in assignments:
            pa = ProjectAssignment(
                project_id=project_id,
                staff_id=a["staff_id"],
                role=a["role"],
                assigned_cycles=a.get("assigned_cycles"),
                assigned_at=now,
                assigned_by=assigned_by,
            )
            self.db.add(pa)
            created.append(pa)

        await self.db.flush()

        # 发送通知给被委派人员
        await self._send_assignment_notifications(project_id, created)

        return created

    async def _send_assignment_notifications(
        self, project_id: UUID, assignments: list[ProjectAssignment]
    ) -> None:
        """给被委派人员发送通知"""
        # 获取项目名称
        proj = (await self.db.execute(
            sa.select(Project.name).where(Project.id == project_id)
        )).scalar_one_or_none()
        project_name = proj or "未知项目"

        for pa in assignments:
            # 查找人员关联的 user_id
            staff = (await self.db.execute(
                sa.select(StaffMember.user_id, StaffMember.name)
                .where(StaffMember.id == pa.staff_id)
            )).one_or_none()

            if staff and staff.user_id:
                role_map = {
                    "signing_partner": "签字合伙人",
                    "manager": "项目经理",
                    "auditor": "审计员",
                    "qc": "质控人员",
                }
                role_cn = role_map.get(pa.role, pa.role)
                cycles = ", ".join(pa.assigned_cycles) if pa.assigned_cycles else "全部"

                notif = Notification(
                    recipient_id=staff.user_id,
                    message_type="ASSIGNMENT_CREATED",
                    title=f"您已被委派到项目「{project_name}」",
                    content=f"角色：{role_cn}，负责循环：{cycles}",
                    related_object_type="project",
                    related_object_id=project_id,
                )
                self.db.add(notif)

    async def get_my_assignments(self, user_id: UUID) -> list[dict]:
        """获取当前用户被委派的项目列表"""
        q = (
            sa.select(
                ProjectAssignment,
                Project.name.label("project_name"),
                Project.client_name,
                Project.status.label("project_status"),
            )
            .join(StaffMember, ProjectAssignment.staff_id == StaffMember.id)
            .join(Project, ProjectAssignment.project_id == Project.id)
            .where(
                StaffMember.user_id == user_id,
                ProjectAssignment.is_deleted == False,  # noqa
                Project.is_deleted == False,  # noqa
            )
            .order_by(ProjectAssignment.assigned_at.desc())
        )
        rows = (await self.db.execute(q)).all()
        return [
            {
                "project_id": str(row[0].project_id),
                "project_name": row.project_name,
                "client_name": row.client_name,
                "project_status": row.project_status,
                "role": row[0].role,
                "assigned_cycles": row[0].assigned_cycles,
                "assigned_at": str(row[0].assigned_at) if row[0].assigned_at else None,
            }
            for row in rows
        ]
