"""统一溯源服务 — wp-traceability-panel Task 1.1

收口 3 个 trace service（wp_trace / report_trace / version_line）到统一端点，
统一输出 LocateTarget 格式。不重写现有 trace service，只做入口收口。

Requirements: 1.1, 1.2, 1.3
"""

from __future__ import annotations

import logging
from typing import Any, Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.locate_target import LocateTarget, LocateTargetSchema, trace_item_to_locate_target
from app.services.report_trace_service import ReportTraceService, report_trace_to_locate_targets
from app.services.version_line_service import version_line_service
from app.services.wp_trace_service import trace_downstream, trace_upstream

logger = logging.getLogger(__name__)

# 支持的对象类型
ObjectType = Literal["wp_cell", "report_row", "note_cell", "tb_row", "adjustment"]
Direction = Literal["both", "upstream", "downstream"]


class UnifiedLineageService:
    """统一溯源服务：委托 3 个 trace service，统一输出 LocateTarget。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def query_lineage(
        self,
        project_id: UUID,
        object_type: ObjectType,
        object_id: str,
        direction: Direction = "both",
        year: int | None = None,
    ) -> dict[str, Any]:
        """统一溯源查询。

        返回:
            {
                "current": LocateTargetSchema,
                "upstream": [LocateTargetSchema, ...],
                "downstream": [LocateTargetSchema, ...],
                "attachments": [AttachmentRef, ...]
            }
        """
        current = self._build_current_target(object_type, object_id)
        upstream: list[LocateTarget] = []
        downstream: list[LocateTarget] = []
        attachments: list[dict[str, Any]] = []

        # 委托 wp_trace_service
        if direction in ("both", "upstream"):
            upstream.extend(await self._query_wp_upstream(project_id, object_type, object_id, year))

        if direction in ("both", "downstream"):
            downstream.extend(await self._query_wp_downstream(project_id, object_type, object_id, year))

        # 委托 report_trace_service
        if object_type in ("report_row", "note_cell"):
            report_targets = await self._query_report_trace(project_id, object_type, object_id, year)
            if direction in ("both", "upstream"):
                upstream.extend(report_targets)

        # 委托 version_line_service（版本链作为下游参考）
        if direction in ("both", "downstream"):
            version_targets = await self._query_version_line(project_id, object_type, object_id)
            downstream.extend(version_targets)

        # 查询关联附件
        attachments = await self._query_attachments(project_id, object_type, object_id)

        return {
            "current": LocateTargetSchema.from_dataclass(current).model_dump(),
            "upstream": [LocateTargetSchema.from_dataclass(t).model_dump() for t in upstream],
            "downstream": [LocateTargetSchema.from_dataclass(t).model_dump() for t in downstream],
            "attachments": attachments,
        }

    def _build_current_target(self, object_type: ObjectType, object_id: str) -> LocateTarget:
        """构建当前节点的 LocateTarget。"""
        # 从 object_id 解析 wp_code（格式可能是 "D2-1!B5" 或纯 UUID）
        wp_code = object_id
        cell_ref = None
        sheet_name = None

        if "!" in object_id:
            parts = object_id.split("!")
            wp_code = parts[0]
            cell_ref = parts[1] if len(parts) > 1 else None
        elif ":" in object_id:
            # 格式 "wp_code:sheet:cell"
            parts = object_id.split(":")
            wp_code = parts[0]
            sheet_name = parts[1] if len(parts) > 1 else None
            cell_ref = parts[2] if len(parts) > 2 else None

        return LocateTarget(
            wp_code=wp_code,
            sheet_name=sheet_name,
            cell_ref=cell_ref,
            label=f"{object_type}:{object_id}",
        )

    async def _query_wp_upstream(
        self, project_id: UUID, object_type: ObjectType, object_id: str, year: int | None
    ) -> list[LocateTarget]:
        """委托 wp_trace_service.trace_upstream。"""
        targets: list[LocateTarget] = []
        try:
            # wp_trace_service 接受 identifier 格式
            identifier = object_id
            result = await trace_upstream(self.db, project_id, identifier)
            for item in result.items:
                targets.append(trace_item_to_locate_target(item))
        except Exception as e:
            logger.debug("wp_trace upstream 查询失败: %s", e)
        return targets

    async def _query_wp_downstream(
        self, project_id: UUID, object_type: ObjectType, object_id: str, year: int | None
    ) -> list[LocateTarget]:
        """委托 wp_trace_service.trace_downstream。"""
        targets: list[LocateTarget] = []
        try:
            identifier = object_id
            result = await trace_downstream(self.db, project_id, identifier)
            for item in result.items:
                targets.append(trace_item_to_locate_target(item))
        except Exception as e:
            logger.debug("wp_trace downstream 查询失败: %s", e)
        return targets

    async def _query_report_trace(
        self, project_id: UUID, object_type: ObjectType, object_id: str, year: int | None
    ) -> list[LocateTarget]:
        """委托 report_trace_service。"""
        targets: list[LocateTarget] = []
        try:
            svc = ReportTraceService()
            # 对于 note_cell 类型，使用 section_number 查询
            section_number = object_id.split("!")[0] if "!" in object_id else object_id
            trace_result = await svc.trace_section(self.db, project_id, section_number, year)
            targets.extend(report_trace_to_locate_targets(trace_result))
        except Exception as e:
            logger.debug("report_trace 查询失败: %s", e)
        return targets

    async def _query_version_line(
        self, project_id: UUID, object_type: ObjectType, object_id: str
    ) -> list[LocateTarget]:
        """委托 version_line_service 查询版本链。"""
        targets: list[LocateTarget] = []
        try:
            # version_line 按 object_type 查询
            vl_type_map = {
                "wp_cell": "workpaper",
                "report_row": "report",
                "note_cell": "note",
                "tb_row": "trial_balance",
                "adjustment": "adjustment",
            }
            vl_type = vl_type_map.get(object_type, "workpaper")
            items = await version_line_service.query_lineage(
                self.db, project_id, object_type=vl_type
            )
            # 版本链条目转为 LocateTarget（仅作为参考信息）
            for item in items[:5]:  # 限制返回数量
                targets.append(LocateTarget(
                    wp_code=item.get("object_id", ""),
                    label=f"v{item.get('version_no', '?')} ({item.get('created_at', '')})",
                ))
        except Exception as e:
            logger.debug("version_line 查询失败: %s", e)
        return targets

    async def _query_attachments(
        self, project_id: UUID, object_type: ObjectType, object_id: str
    ) -> list[dict[str, Any]]:
        """查询关联附件（attachment_lineage 表）。"""
        attachments: list[dict[str, Any]] = []
        try:
            import sqlalchemy as sa
            result = await self.db.execute(sa.text(
                "SELECT al.id, al.attachment_id, al.target_type, al.target_id, "
                "al.target_ref, al.created_at, wa.file_name, wa.file_type "
                "FROM attachment_lineage al "
                "LEFT JOIN wp_attachments wa ON wa.id = al.attachment_id "
                "WHERE al.target_type = :target_type AND al.target_ref LIKE :ref_pattern "
                "ORDER BY al.created_at DESC LIMIT 20"
            ), {
                "target_type": object_type,
                "ref_pattern": f"%{object_id}%",
            })
            for row in result.fetchall():
                attachments.append({
                    "id": str(row.id),
                    "attachment_id": str(row.attachment_id),
                    "target_type": row.target_type,
                    "target_ref": row.target_ref,
                    "file_name": row.file_name,
                    "file_type": row.file_type,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                })
        except Exception as e:
            # attachment_lineage 表可能尚未创建
            logger.debug("附件关联查询失败（表可能不存在）: %s", e)
        return attachments
