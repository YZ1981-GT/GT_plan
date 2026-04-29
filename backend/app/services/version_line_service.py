"""Phase 16: 版本链服务

统一版本戳写入与查询，保证 version_no 连续递增。
"""
import uuid
import logging
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase16_models import VersionLineStamp
from app.services.trace_event_service import generate_trace_id

logger = logging.getLogger(__name__)


class VersionLineService:

    async def write_stamp(
        self,
        db: AsyncSession,
        project_id: uuid.UUID,
        object_type: str,
        object_id: uuid.UUID,
        version_no: int,
        source_snapshot_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> dict:
        """写入版本戳，连续性守卫：version_no 必须 = max+1"""
        if trace_id is None:
            trace_id = generate_trace_id()

        # 查询当前最大版本号
        stmt = (
            select(func.max(VersionLineStamp.version_no))
            .where(VersionLineStamp.project_id == project_id)
            .where(VersionLineStamp.object_type == object_type)
            .where(VersionLineStamp.object_id == object_id)
        )
        result = await db.execute(stmt)
        max_version = result.scalar() or 0

        if version_no != max_version + 1:
            raise HTTPException(status_code=409, detail={
                "error_code": "VERSION_LINE_GAP",
                "message": f"版本号不连续：当前最大={max_version}，提交={version_no}",
                "expected": max_version + 1,
                "actual": version_no,
            })

        stamp = VersionLineStamp(
            project_id=project_id,
            object_type=object_type,
            object_id=object_id,
            version_no=version_no,
            source_snapshot_id=source_snapshot_id,
            trace_id=trace_id,
        )
        db.add(stamp)
        await db.flush()

        return {
            "id": str(stamp.id),
            "object_type": object_type,
            "object_id": str(object_id),
            "version_no": version_no,
            "trace_id": trace_id,
        }

    async def query_lineage(
        self,
        db: AsyncSession,
        project_id: uuid.UUID,
        object_type: Optional[str] = None,
        object_id: Optional[uuid.UUID] = None,
    ) -> list:
        stmt = select(VersionLineStamp).where(VersionLineStamp.project_id == project_id)
        if object_type:
            stmt = stmt.where(VersionLineStamp.object_type == object_type)
        if object_id:
            stmt = stmt.where(VersionLineStamp.object_id == object_id)
        stmt = stmt.order_by(VersionLineStamp.object_type, VersionLineStamp.object_id, VersionLineStamp.version_no.asc())

        result = await db.execute(stmt)
        stamps = result.scalars().all()
        return [
            {
                "id": str(s.id),
                "object_type": s.object_type,
                "object_id": str(s.object_id),
                "version_no": s.version_no,
                "source_snapshot_id": s.source_snapshot_id,
                "trace_id": s.trace_id,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in stamps
        ]

    async def get_latest_version(
        self,
        db: AsyncSession,
        project_id: uuid.UUID,
        object_type: str,
        object_id: uuid.UUID,
    ) -> int:
        stmt = (
            select(func.max(VersionLineStamp.version_no))
            .where(VersionLineStamp.project_id == project_id)
            .where(VersionLineStamp.object_type == object_type)
            .where(VersionLineStamp.object_id == object_id)
        )
        result = await db.execute(stmt)
        return result.scalar() or 0


version_line_service = VersionLineService()
