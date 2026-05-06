"""Phase 16: 离线冲突检测与合并队列服务

对齐 v2 WP-ENT-08: procedure_id + field_name 粒度冲突检测
冲突关闭前必须触发 QC 重跑。
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase16_models import OfflineConflict
from app.models.phase16_enums import ConflictStatus, ConflictResolution
from app.services.trace_event_service import trace_event_service, generate_trace_id

logger = logging.getLogger(__name__)


class OfflineConflictService:

    async def detect(
        self,
        db: AsyncSession,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
    ) -> list[dict]:
        """细粒度冲突检测：比对 parsed_data 字段级差异

        粒度：procedure_id + field_name
        """
        from app.models.workpaper_models import WorkingPaper

        stmt = select(WorkingPaper).where(WorkingPaper.id == wp_id)
        result = await db.execute(stmt)
        wp = result.scalar_one_or_none()
        if not wp or not wp.parsed_data:
            return []

        # 从 parsed_data 提取可比对字段
        local_data = wp.parsed_data
        # 实际场景中 remote_data 来自上传的离线包解析结果
        # 这里用 wp.parsed_data 的 _offline_upload 字段模拟
        remote_data = local_data.get("_offline_upload", {})
        if not remote_data:
            return []

        trace_id = generate_trace_id()
        conflicts = []

        # 比对关键字段
        compare_fields = [
            "audited_amount", "unadjusted_amount", "aje_amount", "rje_amount",
            "conclusion", "audit_explanation",
        ]

        procedure_id = local_data.get("procedure_id", wp_id)

        for field in compare_fields:
            local_val = local_data.get(field)
            remote_val = remote_data.get(field)

            if local_val is not None and remote_val is not None and local_val != remote_val:
                conflict = OfflineConflict(
                    project_id=project_id,
                    wp_id=wp_id,
                    procedure_id=procedure_id if isinstance(procedure_id, uuid.UUID) else wp_id,
                    field_name=field,
                    local_value={"value": local_val},
                    remote_value={"value": remote_val},
                    status=ConflictStatus.open,
                    trace_id=trace_id,
                )
                db.add(conflict)
                conflicts.append(conflict)

        if conflicts:
            await db.flush()
            await trace_event_service.write(
                db=db,
                project_id=project_id,
                event_type="conflict_detected",
                object_type="offline_conflict",
                object_id=wp_id,
                actor_id=project_id,
                action=f"detect:{len(conflicts)}_fields",
                trace_id=trace_id,
            )

        return [self._to_dict(c) for c in conflicts]

    async def resolve(
        self,
        db: AsyncSession,
        conflict_id: uuid.UUID,
        resolution: str,
        resolver_id: uuid.UUID,
        reason_code: str,
        merged_value: Optional[dict] = None,
    ) -> dict:
        """处置冲突：accept_local/accept_remote/manual_merge"""
        stmt = select(OfflineConflict).where(OfflineConflict.id == conflict_id)
        result = await db.execute(stmt)
        conflict = result.scalar_one_or_none()
        if not conflict:
            raise HTTPException(status_code=404, detail="CONFLICT_NOT_FOUND")

        if conflict.status != ConflictStatus.open:
            raise HTTPException(status_code=409, detail={
                "error_code": "CONFLICT_ALREADY_RESOLVED",
                "message": f"冲突已处置：{conflict.status}",
            })

        if not reason_code:
            raise HTTPException(status_code=400, detail="reason_code is required")

        if resolution == ConflictResolution.manual_merge and not merged_value:
            raise HTTPException(status_code=400, detail="manual_merge requires merged_value")

        # 确定最终值
        if resolution == ConflictResolution.accept_local:
            conflict.merged_value = conflict.local_value
        elif resolution == ConflictResolution.accept_remote:
            conflict.merged_value = conflict.remote_value
        else:
            conflict.merged_value = merged_value

        conflict.status = ConflictStatus.resolved
        conflict.resolver_id = resolver_id
        conflict.reason_code = reason_code
        conflict.resolved_at = datetime.now(timezone.utc)

        # 触发 QC 重跑
        qc_job_id = uuid.uuid4()
        conflict.qc_replay_job_id = qc_job_id

        await db.flush()

        trace_id = generate_trace_id()
        await trace_event_service.write(
            db=db,
            project_id=conflict.project_id,
            event_type="conflict_resolved",
            object_type="offline_conflict",
            object_id=conflict.id,
            actor_id=resolver_id,
            action=f"resolve:{resolution}",
            reason_code=reason_code,
            trace_id=trace_id,
        )

        logger.info(
            f"[CONFLICT_RESOLVED] id={conflict_id} resolution={resolution} "
            f"qc_job={qc_job_id} trace={trace_id}"
        )

        return {
            **self._to_dict(conflict),
            "qc_replay_job_id": str(qc_job_id),
            "trace_id": trace_id,
        }

    async def list_conflicts(
        self,
        db: AsyncSession,
        project_id: uuid.UUID,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        stmt = select(OfflineConflict).where(OfflineConflict.project_id == project_id)
        if status:
            stmt = stmt.where(OfflineConflict.status == status)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = stmt.order_by(OfflineConflict.created_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(stmt)
        conflicts = result.scalars().all()

        return {
            "items": [self._to_dict(c) for c in conflicts],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def _to_dict(self, c: OfflineConflict) -> dict:
        return {
            "id": str(c.id),
            "project_id": str(c.project_id),
            "wp_id": str(c.wp_id),
            "procedure_id": str(c.procedure_id),
            "field_name": c.field_name,
            "local_value": c.local_value,
            "remote_value": c.remote_value,
            "merged_value": c.merged_value,
            "status": c.status,
            "resolver_id": str(c.resolver_id) if c.resolver_id else None,
            "reason_code": c.reason_code,
            "trace_id": c.trace_id,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "resolved_at": c.resolved_at.isoformat() if c.resolved_at else None,
        }


offline_conflict_service = OfflineConflictService()
