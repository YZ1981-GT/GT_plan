"""Phase 15: 四级任务树服务

unit → account → workpaper → evidence 四级层级管理
"""
import uuid
import logging
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select, func, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase15_models import TaskTreeNode
from app.models.phase15_enums import TaskNodeStatus
from app.services.trace_event_service import trace_event_service, generate_trace_id

logger = logging.getLogger(__name__)

# 合法状态迁移
VALID_TRANSITIONS = {
    (TaskNodeStatus.pending, TaskNodeStatus.in_progress),
    (TaskNodeStatus.in_progress, TaskNodeStatus.blocked),
    (TaskNodeStatus.blocked, TaskNodeStatus.in_progress),
    (TaskNodeStatus.in_progress, TaskNodeStatus.done),
}


class TaskTreeService:

    async def list_nodes(
        self,
        db: AsyncSession,
        project_id: uuid.UUID,
        node_level: Optional[str] = None,
        status: Optional[str] = None,
        assignee_id: Optional[uuid.UUID] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        stmt = select(TaskTreeNode).where(TaskTreeNode.project_id == project_id)
        if node_level:
            stmt = stmt.where(TaskTreeNode.node_level == node_level)
        if status:
            stmt = stmt.where(TaskTreeNode.status == status)
        if assignee_id:
            stmt = stmt.where(TaskTreeNode.assignee_id == assignee_id)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = stmt.order_by(TaskTreeNode.created_at.asc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(stmt)
        nodes = result.scalars().all()

        return {
            "items": [self._to_dict(n) for n in nodes],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def get_node(self, db: AsyncSession, node_id: uuid.UUID) -> TaskTreeNode:
        stmt = select(TaskTreeNode).where(TaskTreeNode.id == node_id)
        result = await db.execute(stmt)
        node = result.scalar_one_or_none()
        if not node:
            raise HTTPException(status_code=404, detail="TASK_NODE_NOT_FOUND")
        return node

    async def transit_status(
        self,
        db: AsyncSession,
        node_id: uuid.UUID,
        next_status: str,
        operator_id: uuid.UUID,
    ) -> dict:
        node = await self.get_node(db, node_id)
        transition = (node.status, next_status)

        if transition not in VALID_TRANSITIONS:
            raise HTTPException(
                status_code=409,
                detail={
                    "error_code": "TASK_STATUS_INVALID_TRANSITION",
                    "message": f"不允许从 {node.status} 迁移到 {next_status}",
                    "from_status": node.status,
                    "to_status": next_status,
                }
            )

        old_status = node.status
        node.status = next_status
        await db.flush()

        trace_id = generate_trace_id()
        await trace_event_service.write(
            db=db,
            project_id=node.project_id,
            event_type="task_status_changed",
            object_type="task_tree_node",
            object_id=node.id,
            actor_id=operator_id,
            action=f"transit:{old_status}->{next_status}",
            from_status=old_status,
            to_status=next_status,
            trace_id=trace_id,
        )

        return self._to_dict(node)

    async def reassign(
        self,
        db: AsyncSession,
        node_id: uuid.UUID,
        assignee_id: uuid.UUID,
        operator_id: uuid.UUID,
        reason_code: str,
    ) -> dict:
        node = await self.get_node(db, node_id)
        old_assignee = node.assignee_id
        node.assignee_id = assignee_id
        await db.flush()

        # 继承规则：unit/account 级转派同步更新子节点
        if node.node_level in ("unit", "account"):
            stmt = (
                sa_update(TaskTreeNode)
                .where(TaskTreeNode.parent_id == node.id)
                .values(assignee_id=assignee_id)
            )
            await db.execute(stmt)
            await db.flush()

        trace_id = generate_trace_id()
        await trace_event_service.write(
            db=db,
            project_id=node.project_id,
            event_type="task_reassigned",
            object_type="task_tree_node",
            object_id=node.id,
            actor_id=operator_id,
            action=f"reassign:{old_assignee}->{assignee_id}",
            reason_code=reason_code,
            trace_id=trace_id,
        )

        return self._to_dict(node)

    async def get_stats(self, db: AsyncSession, project_id: uuid.UUID) -> dict:
        stmt = (
            select(
                TaskTreeNode.node_level,
                TaskTreeNode.status,
                func.count().label("count"),
            )
            .where(TaskTreeNode.project_id == project_id)
            .group_by(TaskTreeNode.node_level, TaskTreeNode.status)
        )
        result = await db.execute(stmt)
        rows = result.all()
        stats = {}
        for level, status, count in rows:
            if level not in stats:
                stats[level] = {}
            stats[level][status] = count
        return stats

    def _to_dict(self, node: TaskTreeNode) -> dict:
        return {
            "id": str(node.id),
            "project_id": str(node.project_id),
            "node_level": node.node_level,
            "parent_id": str(node.parent_id) if node.parent_id else None,
            "ref_id": str(node.ref_id),
            "status": node.status,
            "assignee_id": str(node.assignee_id) if node.assignee_id else None,
            "due_at": node.due_at.isoformat() if node.due_at else None,
            "meta": node.meta,
        }


task_tree_service = TaskTreeService()
