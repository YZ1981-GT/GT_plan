"""Phase 14: 统一过程留痕服务

对齐 v2 WP-ENT-01 / 5.9.3 D-01 / A-02
所有关键动作通过此服务写入 trace_events 表。
Phase 15/16 事件也通过此服务写入。
"""
import uuid
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase14_models import TraceEvent
from app.models.phase14_enums import TraceReplayLevel

logger = logging.getLogger(__name__)


def generate_trace_id() -> str:
    """生成 trace_id

    格式: trc_{yyyyMMddHHmmss}_{uuid_short_12}
    示例: trc_20260428143500_a1b2c3d4e5f6
    """
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    short_uuid = uuid.uuid4().hex[:12]
    return f"trc_{ts}_{short_uuid}"


class TraceEventService:
    """统一过程留痕服务"""

    async def write(
        self,
        db: AsyncSession,
        project_id: uuid.UUID,
        event_type: str,
        object_type: str,
        object_id: uuid.UUID,
        actor_id: uuid.UUID,
        action: str,
        actor_role: Optional[str] = None,
        decision: Optional[str] = None,
        reason_code: Optional[str] = None,
        from_status: Optional[str] = None,
        to_status: Optional[str] = None,
        before_snapshot: Optional[dict] = None,
        after_snapshot: Optional[dict] = None,
        content_hash: Optional[str] = None,
        version_no: Optional[int] = None,
        trace_id: Optional[str] = None,
    ) -> str:
        """写入 trace_events，返回 trace_id

        写入失败不阻断主业务，仅记录错误日志。
        """
        if trace_id is None:
            trace_id = generate_trace_id()

        try:
            event = TraceEvent(
                project_id=project_id,
                event_type=event_type,
                object_type=object_type,
                object_id=object_id,
                actor_id=actor_id,
                actor_role=actor_role,
                action=action,
                decision=decision,
                reason_code=reason_code,
                from_status=from_status,
                to_status=to_status,
                before_snapshot=before_snapshot,
                after_snapshot=after_snapshot,
                content_hash=content_hash,
                version_no=version_no,
                trace_id=trace_id,
            )
            db.add(event)
            await db.flush()
            return trace_id
        except Exception as e:
            logger.error(
                f"[TRACE_WRITE_FAIL] event_type={event_type} "
                f"object_type={object_type} object_id={object_id} "
                f"trace_id={trace_id} error={e}"
            )
            # 写入失败不阻断主业务
            return trace_id

    async def replay(
        self,
        db: AsyncSession,
        trace_id: str,
        level: str = "L1",
    ) -> dict:
        """按 trace_id 查询完整事件链

        L1: 事件摘要（who/what/when）
        L2: 含 before/after snapshot
        L3: 含 content_hash 可复算校验
        """
        stmt = (
            select(TraceEvent)
            .where(TraceEvent.trace_id == trace_id)
            .order_by(TraceEvent.created_at.asc())
        )
        result = await db.execute(stmt)
        events = result.scalars().all()

        if not events:
            return {
                "trace_id": trace_id,
                "events": [],
                "replay_status": "broken",
            }

        event_list = []
        for e in events:
            item = {
                "id": str(e.id),
                "event_type": e.event_type,
                "object_type": e.object_type,
                "object_id": str(e.object_id),
                "actor_id": str(e.actor_id),
                "actor_role": e.actor_role,
                "action": e.action,
                "decision": e.decision,
                "reason_code": e.reason_code,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            if level in (TraceReplayLevel.L2, TraceReplayLevel.L3, "L2", "L3"):
                item["from_status"] = e.from_status
                item["to_status"] = e.to_status
                item["before_snapshot"] = e.before_snapshot
                item["after_snapshot"] = e.after_snapshot
                item["version_no"] = e.version_no
            if level in (TraceReplayLevel.L3, "L3"):
                item["content_hash"] = e.content_hash
            event_list.append(item)

        return {
            "trace_id": trace_id,
            "events": event_list,
            "replay_status": "complete",
        }

    async def query(
        self,
        db: AsyncSession,
        project_id: uuid.UUID,
        event_type: Optional[str] = None,
        object_type: Optional[str] = None,
        object_id: Optional[uuid.UUID] = None,
        actor_id: Optional[uuid.UUID] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        """按项目/对象/时间/角色检索 trace 事件"""
        stmt = select(TraceEvent).where(TraceEvent.project_id == project_id)

        if event_type:
            stmt = stmt.where(TraceEvent.event_type == event_type)
        if object_type:
            stmt = stmt.where(TraceEvent.object_type == object_type)
        if object_id:
            stmt = stmt.where(TraceEvent.object_id == object_id)
        if actor_id:
            stmt = stmt.where(TraceEvent.actor_id == actor_id)

        # count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        # paginate
        stmt = stmt.order_by(TraceEvent.created_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(stmt)
        events = result.scalars().all()

        return {
            "items": [
                {
                    "id": str(e.id),
                    "event_type": e.event_type,
                    "object_type": e.object_type,
                    "object_id": str(e.object_id),
                    "actor_id": str(e.actor_id),
                    "actor_role": e.actor_role,
                    "action": e.action,
                    "decision": e.decision,
                    "reason_code": e.reason_code,
                    "trace_id": e.trace_id,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in events
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }


# 全局单例
trace_event_service = TraceEventService()
