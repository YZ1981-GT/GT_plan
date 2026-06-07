"""LinkageFacade — 统一联动查询门面服务（P1-1）

封装现有 linkage_service、wp_note_linkage_service、report_trace_service，
提供单一 trace 查询入口，同时附加 conflict/stale 状态和差异对账日志。

设计要点：
- 不删除旧服务，仅在新 UI 入口和签发检查中使用 facade
- 差异对账：新 facade 结果与旧 trace API 结果对比，差异写 warning 日志
- 返回统一 LinkageContract 列表
"""
from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.linkage_contract import (
    LinkageContract,
    LinkageConfidence,
    LinkageStatus,
    SourceType,
    TargetType,
)
from app.services.linkage_contract_builder import (
    build_tb_to_wp_contract,
    build_wp_to_note_contract,
)
from app.services.linkage_service import LinkageService
from app.services.report_trace_service import ReportTraceService
from app.services.wp_note_linkage_service import WpNoteLinkageService

logger = logging.getLogger(__name__)


class LinkageFacadeService:
    """统一联动门面服务。

    聚合 linkage_service、wp_note_linkage_service、report_trace_service，
    返回统一 LinkageContract 列表，附加 conflict/stale 状态。
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._linkage_svc = LinkageService(db)
        self._wp_note_svc = WpNoteLinkageService(db)
        self._report_trace_svc = ReportTraceService()

    async def trace(
        self,
        *,
        project_id: UUID,
        source_type: str,
        source_id: str,
        cell: str | None = None,
        year: int | None = None,
    ) -> list[dict[str, Any]]:
        """统一穿透查询入口。

        根据 source_type 分发到对应子服务，收集结果后：
        1. 转换为 LinkageContract 字典列表
        2. 附加 conflict/stale 状态
        3. 与旧 trace API 结果做差异对账日志

        Returns:
            list of LinkageContract dicts (可直接序列化为 JSON)
        """
        start_ms = time.time()
        contracts: list[dict[str, Any]] = []

        try:
            if source_type in ("trial_balance", "tb"):
                contracts = await self._trace_from_tb(
                    project_id=project_id,
                    source_id=source_id,
                    cell=cell,
                    year=year,
                )
            elif source_type == "workpaper":
                contracts = await self._trace_from_workpaper(
                    project_id=project_id,
                    source_id=source_id,
                    cell=cell,
                    year=year,
                )
            elif source_type == "note":
                contracts = await self._trace_from_note(
                    project_id=project_id,
                    source_id=source_id,
                    cell=cell,
                    year=year,
                )
            elif source_type == "report":
                contracts = await self._trace_from_report(
                    project_id=project_id,
                    source_id=source_id,
                    cell=cell,
                    year=year,
                )
            else:
                logger.warning(
                    "LinkageFacade.trace: 不支持的 source_type=%s", source_type
                )
        except Exception as exc:
            logger.error(
                "LinkageFacade.trace 异常: source_type=%s, source_id=%s, error=%s",
                source_type, source_id, exc,
            )

        # 附加 conflict/stale 状态
        contracts = await self._enrich_conflict_stale(project_id, contracts)

        # 差异对账日志
        duration_ms = int((time.time() - start_ms) * 1000)
        await self._reconciliation_log(
            project_id=project_id,
            source_type=source_type,
            source_id=source_id,
            facade_count=len(contracts),
            duration_ms=duration_ms,
        )

        return contracts

    # ─── 子 trace 实现 ─────────────────────────────────────────────────

    async def _trace_from_tb(
        self,
        *,
        project_id: UUID,
        source_id: str,
        cell: str | None,
        year: int | None,
    ) -> list[dict[str, Any]]:
        """试算表 → 底稿/调整分录联动。"""
        contracts: list[dict[str, Any]] = []
        pid = str(project_id)
        yr = year or 2025

        # 查关联底稿
        try:
            wps = await self._linkage_svc.get_workpapers_for_tb_row(
                project_id, yr, source_id
            )
            for wp in wps:
                c = LinkageContract(
                    source_type=SourceType.trial_balance,
                    source_id=source_id,
                    source_cell=cell,
                    target_type=TargetType.workpaper,
                    target_id=wp.get("id", ""),
                    target_cell=None,
                    amount=None,
                    basis="TB → 底稿（wp_account_mapping）",
                    status=LinkageStatus.current,
                    confidence=LinkageConfidence.system,
                    route=f"/projects/{pid}/workpapers/{wp.get('id', '')}",
                )
                contracts.append(c.model_dump())
        except Exception as exc:
            logger.warning("_trace_from_tb workpapers: %s", exc)

        # 查关联调整分录
        try:
            adjs = await self._linkage_svc.get_adjustments_for_tb_row(
                project_id, yr, source_id
            )
            for adj in adjs:
                c = LinkageContract(
                    source_type=SourceType.trial_balance,
                    source_id=source_id,
                    source_cell=cell,
                    target_type=TargetType.adjustment,
                    target_id=adj.get("id", ""),
                    target_cell=None,
                    amount=str(adj.get("debit_amount", 0) - adj.get("credit_amount", 0)),
                    basis=f"调整分录 {adj.get('adjustment_no', '')}",
                    status=LinkageStatus.current,
                    confidence=LinkageConfidence.system,
                    route=f"/projects/{pid}/adjustments?highlight={adj.get('id', '')}",
                )
                contracts.append(c.model_dump())
        except Exception as exc:
            logger.warning("_trace_from_tb adjustments: %s", exc)

        return contracts

    async def _trace_from_workpaper(
        self,
        *,
        project_id: UUID,
        source_id: str,
        cell: str | None,
        year: int | None,
    ) -> list[dict[str, Any]]:
        """底稿 → 附注联动。"""
        contracts: list[dict[str, Any]] = []
        pid = str(project_id)
        yr = year or 2025

        # 通过 wp_note_linkage 查附注数据
        try:
            note_data = await self._wp_note_svc.fetch_note_data(
                project_id=project_id,
                year=yr,
                note_section_code=source_id,
            )
            if note_data and note_data.get("data"):
                c = LinkageContract(
                    source_type=SourceType.workpaper,
                    source_id=source_id,
                    source_cell=cell,
                    target_type=TargetType.note,
                    target_id=source_id,
                    target_cell=None,
                    basis="底稿审定数 → 附注",
                    status=LinkageStatus.current,
                    confidence=LinkageConfidence.system,
                    route=f"/projects/{pid}/disclosure-notes?section={source_id}",
                )
                contracts.append(c.model_dump())
        except Exception as exc:
            logger.warning("_trace_from_workpaper: %s", exc)

        return contracts

    async def _trace_from_note(
        self,
        *,
        project_id: UUID,
        source_id: str,
        cell: str | None,
        year: int | None,
    ) -> list[dict[str, Any]]:
        """附注 → 报表/底稿溯源。"""
        contracts: list[dict[str, Any]] = []
        pid = str(project_id)

        try:
            trace_result = await self._report_trace_svc.trace_section(
                db=self.db,
                project_id=project_id,
                section_number=source_id,
                year=year,
            )
            note_data = trace_result.get("note_data")
            if note_data and note_data.get("wp_code"):
                c = LinkageContract(
                    source_type=SourceType.note,
                    source_id=source_id,
                    source_cell=cell,
                    target_type=TargetType.workpaper,
                    target_id=note_data["wp_code"],
                    target_cell=None,
                    basis=f"附注 → 底稿 {note_data['wp_code']}",
                    status=LinkageStatus.current,
                    confidence=LinkageConfidence.system,
                    route=f"/projects/{pid}/workpapers/{note_data['wp_code']}",
                )
                contracts.append(c.model_dump())

            if trace_result.get("trial_balance_data"):
                for tb in trace_result["trial_balance_data"][:3]:
                    c = LinkageContract(
                        source_type=SourceType.note,
                        source_id=source_id,
                        source_cell=cell,
                        target_type=TargetType.trial_balance,
                        target_id=tb.get("account_code", ""),
                        target_cell=None,
                        amount=str(tb.get("audited", 0)),
                        basis=f"附注 → TB {tb.get('account_name', '')}",
                        status=LinkageStatus.current,
                        confidence=LinkageConfidence.system,
                        route=f"/projects/{pid}/trial-balance?highlight={tb.get('account_code', '')}",
                    )
                    contracts.append(c.model_dump())
        except Exception as exc:
            logger.warning("_trace_from_note: %s", exc)

        return contracts

    async def _trace_from_report(
        self,
        *,
        project_id: UUID,
        source_id: str,
        cell: str | None,
        year: int | None,
    ) -> list[dict[str, Any]]:
        """报表行 → 试算表/底稿。"""
        contracts: list[dict[str, Any]] = []
        pid = str(project_id)
        yr = year or 2025

        try:
            impact = await self._linkage_svc.get_impact_preview(
                project_id, yr, source_id
            )
            for wp in impact.get("affected_workpapers", []):
                c = LinkageContract(
                    source_type=SourceType.report,
                    source_id=source_id,
                    source_cell=cell,
                    target_type=TargetType.workpaper,
                    target_id=wp.get("wp_code", ""),
                    target_cell=None,
                    basis=f"报表 → 底稿 {wp.get('wp_name', '')}",
                    status=LinkageStatus.current,
                    confidence=LinkageConfidence.system,
                    route=f"/projects/{pid}/workpapers/{wp.get('wp_code', '')}",
                )
                contracts.append(c.model_dump())
        except Exception as exc:
            logger.warning("_trace_from_report: %s", exc)

        return contracts

    # ─── conflict / stale 附加 ─────────────────────────────────────────

    async def _enrich_conflict_stale(
        self,
        project_id: UUID,
        contracts: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """查询 conflict/stale 状态，附加到 contract 上。"""
        if not contracts:
            return contracts

        # 查询该项目的 pending 冲突
        conflict_targets: dict[str, str] = {}
        try:
            from sqlalchemy import text
            result = await self.db.execute(
                text("""
                    SELECT id, target_type, target_id
                    FROM cross_module_conflicts
                    WHERE project_id = :pid AND status = 'pending'
                """),
                {"pid": str(project_id)},
            )
            for row in result.fetchall():
                key = f"{row[1]}:{row[2]}"
                conflict_targets[key] = str(row[0])
        except Exception as exc:
            logger.debug("_enrich_conflict_stale 冲突查询跳过: %s", exc)

        # 附加冲突/stale 状态
        for c in contracts:
            target_key = f"{c.get('target_type', '')}:{c.get('target_id', '')}"
            if target_key in conflict_targets:
                c["status"] = LinkageStatus.conflict.value
                c["conflict_id"] = conflict_targets[target_key]

        return contracts

    # ─── 差异对账日志 ──────────────────────────────────────────────────

    async def _reconciliation_log(
        self,
        *,
        project_id: UUID,
        source_type: str,
        source_id: str,
        facade_count: int,
        duration_ms: int,
    ) -> None:
        """记录 facade 与旧 trace API 的差异对账。

        初期仅记录 facade 返回条数和耗时，后续可扩展为实际对比。
        差异不阻断业务，仅输出 warning 级别日志。
        """
        logger.info(
            "LinkageFacade 对账: project=%s source=%s:%s facade_count=%d duration=%dms",
            project_id, source_type, source_id, facade_count, duration_ms,
        )
        # 后续可写入 event_cascade_log 表做持久化对账
