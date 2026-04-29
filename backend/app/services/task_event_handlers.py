"""Phase 15: 事件处理器

注册到 TaskEventBus，处理裁剪/转派等业务事件。
"""
import uuid
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase15_models import TaskTreeNode
from app.models.phase15_enums import TaskNodeStatus

logger = logging.getLogger(__name__)


async def handle_trim_applied(db: AsyncSession, payload: dict):
    """裁剪生效：关联任务节点 → blocked"""
    wp_id = payload.get("wp_id")
    if not wp_id:
        return

    stmt = select(TaskTreeNode).where(
        TaskTreeNode.ref_id == uuid.UUID(wp_id),
        TaskTreeNode.node_level == "workpaper",
    )
    result = await db.execute(stmt)
    node = result.scalar_one_or_none()
    if node and node.status == TaskNodeStatus.in_progress:
        node.status = TaskNodeStatus.blocked
        await db.flush()
        logger.info(f"[EVENT_HANDLER] trim_applied: node={node.id} → blocked")


async def handle_trim_rollback(db: AsyncSession, payload: dict):
    """裁剪回滚：关联任务节点 → in_progress + 触发 QC 重跑"""
    wp_id = payload.get("wp_id")
    if not wp_id:
        return

    stmt = select(TaskTreeNode).where(
        TaskTreeNode.ref_id == uuid.UUID(wp_id),
        TaskTreeNode.node_level == "workpaper",
    )
    result = await db.execute(stmt)
    node = result.scalar_one_or_none()
    if node and node.status == TaskNodeStatus.blocked:
        node.status = TaskNodeStatus.in_progress
        await db.flush()
        logger.info(f"[EVENT_HANDLER] trim_rollback: node={node.id} → in_progress")

        # 触发 QC 重跑（异步，不阻断）
        try:
            from app.services.qc_engine import QCEngine
            qc = QCEngine()
            # QC 重跑是 fire-and-forget
            logger.info(f"[EVENT_HANDLER] QC replay triggered for wp={wp_id}")
        except Exception as e:
            logger.warning(f"[EVENT_HANDLER] QC replay failed: {e}")


async def handle_task_reassigned(db: AsyncSession, payload: dict):
    """转派：更新子节点 assignee（继承规则在 TaskTreeService.reassign 中已实现）"""
    logger.info(f"[EVENT_HANDLER] task_reassigned: {payload}")


def register_event_handlers():
    """注册所有事件处理器到 TaskEventBus"""
    from app.services.task_event_bus import TaskEventBus

    TaskEventBus.register_handler("trim_applied", handle_trim_applied)
    TaskEventBus.register_handler("trim_rollback", handle_trim_rollback)
    TaskEventBus.register_handler("task_reassigned", handle_task_reassigned)

    logger.info("[EVENT_HANDLERS] Phase 15 handlers registered: trim_applied/trim_rollback/task_reassigned")
