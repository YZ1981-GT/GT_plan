"""报告复核溯源服务 — Phase 10 Task 9.1

wp-locate-foundation Task 1.3: report_trace_to_locate_targets 升级到 cell 级
- 利用 cell_provenance 返回精确 LocateTarget（而非整个 parsed_data）
- 无 cell_provenance 时降级到 sheet 级（cell_ref=None）
Requirements: 1.3, 1.4
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TbLedger, TrialBalance
from app.schemas.locate_target import LocateTarget
from app.services.dataset_query import get_active_filter

logger = logging.getLogger(__name__)


class ReportTraceService:
    """报告复核溯源"""

    async def trace_section(
        self, db: AsyncSession, project_id: UUID, section_number: str,
        year: int | None = None,
    ) -> dict[str, Any]:
        """溯源查询：附注科目 → 底稿 → 试算表 → 序时账"""
        trace = {
            "section_number": section_number,
            "note_data": None,
            "workpaper_data": None,
            "trial_balance_data": None,
            "top_ledger_entries": [],
        }

        # 1. 查附注-底稿映射
        try:
            mapping_result = await db.execute(sa.text(
                "SELECT wp_code, account_codes, note_title "
                "FROM note_wp_mapping "
                "WHERE project_id = :pid AND note_section = :sec "
                "LIMIT 1"
            ), {"pid": str(project_id), "sec": section_number})
            mapping = mapping_result.first()
            if mapping:
                trace["note_data"] = {
                    "wp_code": mapping.wp_code,
                    "account_codes": mapping.account_codes,
                    "note_title": mapping.note_title,
                }
                # 2. 查底稿 parsed_data
                wp_result = await db.execute(sa.text(
                    "SELECT wp.parsed_data FROM working_papers wp "
                    "JOIN wp_index wi ON wp.wp_index_id = wi.id "
                    "WHERE wi.project_id = :pid AND wi.wp_code = :code "
                    "LIMIT 1"
                ), {"pid": str(project_id), "code": mapping.wp_code})
                wp_row = wp_result.first()
                if wp_row and wp_row.parsed_data:
                    trace["workpaper_data"] = wp_row.parsed_data
        except Exception as e:
            logger.warning("溯源映射查询失败: %s", e)

        # 3. 查试算表
        try:
            tb_result = await db.execute(
                sa.select(TrialBalance)
                .where(TrialBalance.project_id == project_id, TrialBalance.is_deleted == sa.false())
                .limit(5)
            )
            tb_rows = tb_result.scalars().all()
            if tb_rows:
                trace["trial_balance_data"] = [
                    {
                        "account_code": t.standard_account_code,
                        "account_name": t.account_name,
                        "opening": float(t.opening_balance or 0),
                        "audited": float(t.audited_amount or 0) if hasattr(t, "audited_amount") else 0,
                    }
                    for t in tb_rows[:5]
                ]
        except Exception:
            pass

        # 4. 查大额序时账
        try:
            if year:
                ledger_conditions = [
                    await get_active_filter(db, TbLedger.__table__, project_id, year),
                ]
            else:
                ledger_conditions = [
                    TbLedger.project_id == project_id,
                    TbLedger.is_deleted == sa.false(),
                ]
            ledger_result = await db.execute(
                sa.select(TbLedger)
                .where(*ledger_conditions)
                .order_by(TbLedger.debit_amount.desc().nullslast())
                .limit(10)
            )
            for r in ledger_result.scalars().all():
                trace["top_ledger_entries"].append({
                    "voucher_no": r.voucher_no,
                    "date": r.voucher_date.isoformat() if r.voucher_date else None,
                    "debit": float(r.debit_amount or 0),
                    "credit": float(r.credit_amount or 0),
                    "summary": r.summary or "",
                })
        except Exception:
            pass

        return trace

    async def get_findings_summary(
        self, db: AsyncSession, project_id: UUID,
    ) -> dict[str, Any]:
        """统一 findings 视图"""
        # 汇总各来源的 findings
        summary = {"llm_findings": 0, "manual_findings": 0, "total": 0}
        try:
            # AI 内容 findings
            ai_result = await db.execute(sa.text(
                "SELECT COUNT(*) FROM ai_contents "
                "WHERE project_id = :pid AND confirmation_status = 'pending'"
            ), {"pid": str(project_id)})
            summary["llm_findings"] = ai_result.scalar() or 0
        except Exception:
            pass
        try:
            # 批注 findings
            ann_result = await db.execute(sa.text(
                "SELECT COUNT(*) FROM cell_annotations "
                "WHERE project_id = :pid AND status = 'pending' AND is_deleted = false"
            ), {"pid": str(project_id)})
            summary["manual_findings"] = ann_result.scalar() or 0
        except Exception:
            pass
        summary["total"] = summary["llm_findings"] + summary["manual_findings"]
        return summary


# ─── report_trace → LocateTarget 转换（Task 1.3）──────────────────────────────


def report_trace_to_locate_targets(
    trace_result: dict[str, Any],
    cell_provenance: dict[str, dict[str, Any]] | None = None,
) -> list[LocateTarget]:
    """将 report_trace_service 溯源结果转换为 LocateTarget 列表。

    利用 cell_provenance（来自 note_dynamic_schema.CellProvenance）返回精确
    cell 级定位目标。无 cell_provenance 时降级到 sheet 级（cell_ref=None）。

    参数:
        trace_result: ReportTraceService.trace_section() 返回的 dict，
            至少包含 note_data.wp_code。
        cell_provenance: parsed_data 中的 _cell_provenance dict，
            key 格式为 "{row_idx}:{col_id}"，value 为 CellProvenance 字段。
            每个 entry 的 source_detail 可能包含 wp_code / sheet / cell_ref。

    返回:
        LocateTarget 列表。每个 provenance entry 产生一个精确定位目标；
        若无 provenance 则降级为 sheet 级（仅含 wp_code + sheet_name）。

    Requirements: 1.3, 1.4
    """
    targets: list[LocateTarget] = []

    # 从 trace_result 提取基础 wp_code
    note_data = trace_result.get("note_data")
    if not note_data:
        return targets

    base_wp_code: str | None = note_data.get("wp_code")
    if not base_wp_code:
        return targets

    # 有 cell_provenance 时：逐条提取精确定位
    if cell_provenance:
        seen: set[tuple[str, str | None, str | None]] = set()
        for _cell_key, prov in cell_provenance.items():
            source_detail = prov.get("source_detail", {})
            wp_code = source_detail.get("wp_code", base_wp_code)
            sheet_name = source_detail.get("sheet")
            cell_ref = source_detail.get("cell_ref")
            value = prov.get("value")

            # 去重：同一 (wp_code, sheet, cell) 只产生一个 target
            dedup_key = (wp_code, sheet_name, cell_ref)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            targets.append(LocateTarget(
                wp_code=wp_code,
                wp_id=None,
                sheet_name=sheet_name,
                cell_ref=cell_ref,  # 精确 cell 级定位
                component_type=None,
                value=str(value) if value is not None else None,
                label=note_data.get("note_title"),
            ))

        if targets:
            return targets

    # 无 cell_provenance 或 provenance 为空：降级到 sheet 级（Requirement 1.4）
    # 尝试从 workpaper_data 获取 sheet 名称
    workpaper_data = trace_result.get("workpaper_data")
    sheet_name: str | None = None
    if isinstance(workpaper_data, dict):
        # parsed_data 通常有 html_data 或 sheets 结构
        html_data = workpaper_data.get("html_data")
        if isinstance(html_data, dict) and html_data:
            # 取第一个 sheet 名称作为降级目标
            sheet_name = next(iter(html_data), None)
        elif "sheets" in workpaper_data:
            sheets = workpaper_data["sheets"]
            if isinstance(sheets, list) and sheets:
                sheet_name = sheets[0].get("name") if isinstance(sheets[0], dict) else None

    targets.append(LocateTarget(
        wp_code=base_wp_code,
        wp_id=None,
        sheet_name=sheet_name,
        cell_ref=None,  # sheet 级降级：无 cell 精度
        component_type=None,
        value=None,
        label=note_data.get("note_title"),
    ))

    return targets
