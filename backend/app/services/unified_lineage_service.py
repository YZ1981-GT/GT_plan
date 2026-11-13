"""统一溯源服务 — wp-traceability-panel Task 1.1

收口 3 个 trace service（wp_trace / report_trace / version_line）到统一端点，
统一输出 LocateTarget 格式。不重写现有 trace service，只做入口收口。

Requirements: 1.1, 1.2, 1.3
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import logging
from typing import Any, Literal, TypeVar
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment_lineage_model import AttachmentLineage
from app.models.attachment_models import Attachment
from app.schemas.locate_target import LocateTarget, LocateTargetSchema, trace_item_to_locate_target
from app.services.attachment_lineage_schema import (
    AttachmentLineageMigrationPending,
    lineage_project_column_ready,
)
from app.services.report_trace_service import ReportTraceService, report_trace_to_locate_targets
from app.services.tb_row_lineage import TbLineageYearRequired, tb_row_upstream
from app.services.version_line_service import version_line_service
from app.services.wp_trace_service import trace_downstream, trace_upstream

logger = logging.getLogger(__name__)

# 支持的对象类型
ObjectType = Literal["wp_cell", "report_row", "note_cell", "deliverable_section", "tb_row", "adjustment"]
Direction = Literal["both", "upstream", "downstream"]
_T = TypeVar("_T")

#: 只有这三类对象有 wp_trace 来源（ADR-FHIC-16）；tb_row 另有自己的试算表行子源（``tb_row_lineage``，
#: spec voucher-workflow-linkage-lineage-closure R8.1），adjustment 没有可委托的溯源来源。
_SOURCE_BY_OBJECT_TYPE: dict[ObjectType, str] = {
    "wp_cell": "workpaper",
    "report_row": "report",
    "note_cell": "disclosure",
}

#: 溯源对象类型 → 附件关联的 ``target_type``（ADR-FHIC-13）；不在表中的类型按原值精确匹配（ADR-FHIC-16）
_ATTACHMENT_TARGET_TYPE: dict[str, str] = {
    "wp_cell": "wp_cell", "report_row": "report_row", "note_cell": "note_section",
    "deliverable_section": "deliverable_section",
}

_SOURCE_LABELS = {
    "wp_trace_upstream": "上游底稿溯源",
    "wp_trace_downstream": "下游底稿溯源",
    "report_trace": "附注报表溯源",
    "version_line": "版本链溯源",
    "attachments": "附件溯源",
    "tb_row": "试算表行溯源",
}


def _trace_identifier(object_type: ObjectType, object_id: str) -> str:
    """把统一对象标识转换为旧 trace service 所需标识。"""
    if object_type == "wp_cell":
        return object_id.split("!", 1)[0]
    return object_id


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
        """查询各独立子源；任一子源失败只标记 ``partial``，不污染后续查询。"""
        current = self._build_current_target(object_type, object_id)
        upstream: list[LocateTarget] = []
        downstream: list[LocateTarget] = []
        errors: list[dict[str, Any]] = []
        source = _SOURCE_BY_OBJECT_TYPE.get(object_type)
        identifier = _trace_identifier(object_type, object_id)

        if source and direction in ("both", "upstream"):
            upstream.extend(await self._run_source(
                "wp_trace_upstream",
                lambda: self._query_wp_upstream(project_id, source, identifier),
                errors,
                [],
            ))

        # 试算表行：构成 / 已批准调整 / 发布底稿 / 抽凭挂凭（spec voucher-workflow-linkage-lineage-closure R8.1）
        if object_type == "tb_row" and direction in ("both", "upstream"):
            upstream.extend(await self._run_source(
                "tb_row",
                lambda: tb_row_upstream(self.db, project_id, object_id, year),
                errors,
                [],
            ))

        # trace_section 只接受附注章节；report_row 已由 wp_trace 的 report 来源处理。
        if object_type == "note_cell" and direction in ("both", "upstream"):
            upstream.extend(await self._run_source(
                "report_trace",
                lambda: self._query_report_trace(project_id, identifier, year),
                errors,
                [],
            ))

        if source and direction in ("both", "downstream"):
            downstream.extend(await self._run_source(
                "wp_trace_downstream",
                lambda: self._query_wp_downstream(project_id, source, identifier),
                errors,
                [],
            ))
            downstream.extend(await self._run_source(
                "version_line",
                lambda: self._query_version_line(project_id, object_type),
                errors,
                [],
            ))

        # 附件不是 wp_trace 来源；tb_row / adjustment 仍按请求 object_type 原值精确匹配附件类型。
        attachments = await self._run_source(
            "attachments",
            lambda: self._query_attachments(project_id, object_type, object_id),
            errors,
            [],
        )

        return {
            "current": LocateTargetSchema.from_dataclass(current).model_dump(),
            "upstream": [LocateTargetSchema.from_dataclass(t).model_dump() for t in upstream],
            "downstream": [LocateTargetSchema.from_dataclass(t).model_dump() for t in downstream],
            "attachments": attachments,
            "partial": bool(errors),
            "errors": errors,
        }

    async def _run_source(
        self,
        source_name: str,
        operation: Callable[[], Awaitable[_T]],
        errors: list[dict[str, Any]],
        fallback: _T,
    ) -> _T:
        """在独立 SAVEPOINT 中运行一个子源，并把失败转为用户可见错误。

        不使用 ``SELECT 1`` 探针：旧 trace service 吞掉异常后，
        ``begin_nested()`` 的 ``commit`` 会因保存点 aborted 而失败，
        ``__aexit__`` 自动 ``rollback`` 再上抛，足以检测并恢复。
        """
        try:
            async with self.db.begin_nested():
                value = await operation()
            return value
        except Exception as exc:  # noqa: BLE001 —— 上下文管理器已回滚该保存点，可安全继续其他子源
            error = self._source_error(source_name, exc)
            errors.append(error)
            logger.warning("统一溯源子源 %s 查询失败: %s", source_name, exc)
            return fallback

    @staticmethod
    def _source_error(source_name: str, exc: Exception) -> dict[str, Any]:
        if isinstance(exc, AttachmentLineageMigrationPending):
            return {"source": source_name, "status": exc.status_code, **exc.to_detail()}
        if isinstance(exc, TbLineageYearRequired):
            return {"source": source_name, "status": exc.status_code, "error_code": exc.error_code,
                    "message": exc.message}
        detail = str(exc).strip() or type(exc).__name__
        label = _SOURCE_LABELS.get(source_name, source_name)
        # 附注 → 底稿映射的两类配置错误要和「查询失败」分开：前者需要修注册表 / 项目映射，重试没有用
        from app.services.note_readiness_service import NoteRegistryUnavailable, ProjectNoteMappingInvalid

        if isinstance(exc, NoteRegistryUnavailable):
            return {"source": source_name, "status": 503, "error_code": "REGISTRY_UNAVAILABLE",
                    "message": f"{label}不可用：附注与底稿对应注册表无法读取：{detail[:200]}"}
        if isinstance(exc, ProjectNoteMappingInvalid):
            return {"source": source_name, "status": 422, "error_code": "PROJECT_MAPPING_INVALID",
                    "message": f"{label}不可用：{detail[:200]}"}
        return {
            "source": source_name,
            "status": 500,
            "error_code": "LINEAGE_SOURCE_FAILED",
            "message": f"{label}查询失败：{type(exc).__name__}：{detail[:200]}",
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
        self, project_id: UUID, source: str, identifier: str,
    ) -> list[LocateTarget]:
        """委托 ``trace_upstream``，参数形状由签名守卫锁定。"""
        result = await trace_upstream(self.db, project_id, source, identifier)
        return [trace_item_to_locate_target(item) for item in result.items]

    async def _query_wp_downstream(
        self, project_id: UUID, source: str, identifier: str,
    ) -> list[LocateTarget]:
        """委托 ``trace_downstream``，参数形状由签名守卫锁定。"""
        result = await trace_downstream(self.db, project_id, source, identifier)
        return [trace_item_to_locate_target(item) for item in result.items]

    async def _query_report_trace(
        self, project_id: UUID, section_number: str, year: int | None,
    ) -> list[LocateTarget]:
        """仅为 note_cell 委托 ``ReportTraceService.trace_section``。

        使用无 ``join_transaction_mode`` 的裸会话调 ``trace_section``：原会话的
        ``join_transaction_mode="create_savepoint"`` 把每条 SQL 包在隐式保存点里，下层（如章节映射
        ``resolve_section_workpapers`` 取报表行映射那一段）吞掉的异常会被完全隔离，``_run_source`` 的
        ``begin_nested()`` commit 不会失败。改用裸会话后，PG 异常直接使 ``begin_nested()`` 的保存点进入
        aborted 状态，commit 失败 → rollback → 报告 ``partial``（ADR-FHIC-16）。``trace_section`` 自身
        不再吞异常（spec voucher-workflow-linkage-lineage-closure R8.2），失败照常上抛到 ``_run_source``。
        """
        conn = await self.db.connection()
        bare = AsyncSession(bind=conn, join_transaction_mode="rollback_only")
        try:
            trace_result = await ReportTraceService().trace_section(
                bare, project_id, section_number, year,
            )
        finally:
            await bare.close()
        return report_trace_to_locate_targets(trace_result)

    async def _query_version_line(
        self, project_id: UUID, object_type: ObjectType,
    ) -> list[LocateTarget]:
        """委托 version_line_service 查询版本链。"""
        vl_type_map = {
            "wp_cell": "workpaper",
            "report_row": "report",
            "note_cell": "note",
        }
        items = await version_line_service.query_lineage(
            self.db, project_id, object_type=vl_type_map[object_type]
        )
        return [
            LocateTarget(
                wp_code=item.get("object_id", ""),
                label=f"v{item.get('version_no', '?')} ({item.get('created_at', '')})",
            )
            for item in items[:5]
        ]

    async def _query_attachments(
        self, project_id: UUID, object_type: ObjectType, object_id: str
    ) -> list[dict[str, Any]]:
        """统一附件子源：底稿读权威关系，输出域读 AttachmentLineage。"""
        from app.services.attachment_trace_service import AttachmentTraceService

        return await AttachmentTraceService(self.db).for_object(
            project_id, object_type, object_id,
        )
