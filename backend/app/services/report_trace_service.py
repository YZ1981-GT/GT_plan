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

#: 序时账取多少笔、按什么排（写进结果的 ledger_basis，前端照原样显示）
TOP_LEDGER_LIMIT = 10


def _section_account_codes(wp_codes: tuple[str, ...]) -> list[str]:
    """章节对应底稿 → 底稿科目映射表（wp_account_mapping.json）里的标准科目，按出现顺序去重。

    读法用报表域的 ``report_stale_service.account_codes_for_wp_code``：报表域不得依赖底稿域
    （docs/architecture/domain-boundaries.json，``WpMappingService`` 属底稿域）；两者读同一份映射，
    1025 个编码逐个同值（2026-11-04 核对）。
    """
    from app.services.report_stale_service import account_codes_for_wp_code

    codes: list[str] = []
    for wp_code in wp_codes:
        for code in account_codes_for_wp_code(wp_code):
            code = str(code).strip()
            if code and code not in codes:
                codes.append(code)
    return codes


class ReportTraceService:
    """报告复核溯源"""

    async def trace_section(
        self, db: AsyncSession, project_id: UUID, section_number: str,
        year: int | None = None,
    ) -> dict[str, Any]:
        """溯源查询：附注章节 → 底稿 → 试算表 → 序时账（spec voucher-workflow-linkage-lineage-closure R8.2，design §10.2）。

        - 章节 → 底稿：附注同步注册表（项目自定义映射优先）；章节 → 科目：对应底稿在底稿科目映射表里的科目；
        - 试算表：按年度（缺省项目审计年度）+ 这些科目取，全部主体合计；原先不分年度、不分科目任取 5 行；
        - 序时账：按年度当前账套 + 科目前缀取 |借 − 贷| 最大的前 10 笔（原先不分科目、只按借方排）；
        - 取数口径写进 ``trial_balance_basis`` / ``ledger_basis``；章节没有映射、映射没有科目、项目没有审计年度时
          不取，口径里写明原因（不是「没有数据」）；
        - 查询失败照常抛出（``/report-review`` 返回 500，统一溯源记 partial），不吞成空结果（原先每段都 ``except: pass``）。
        """
        from app.services.note_readiness_service import resolve_section_workpapers

        trace: dict[str, Any] = {
            "section_number": section_number,
            "note_data": None,
            "workpaper_data": None,
            "trial_balance_data": None,
            "top_ledger_entries": [],
            "year": None,
            "account_codes": [],
            "trial_balance_basis": "",
            "ledger_basis": "",
        }

        # 1. 附注 → 底稿（S5 R2：统一读取注册表；注册表不可用 / 项目自定义映射非法照常抛出）
        resolved = await resolve_section_workpapers(db, project_id, section_number)
        if resolved.status != "mapped" or not resolved.wp_codes:
            trace["trial_balance_basis"] = trace["ledger_basis"] = "章节没有对应底稿，未取试算表与序时账"
            return trace
        trace["note_data"] = {
            "wp_code": resolved.wp_codes[0],
            "wp_codes": list(resolved.wp_codes),
            "note_title": section_number,
        }

        # 2. 底稿 parsed_data（本项目未删除的那一张）
        from app.models.workpaper_models import WorkingPaper, WpIndex

        trace["workpaper_data"] = (await db.execute(
            sa.select(WorkingPaper.parsed_data)
            .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
            .where(WpIndex.project_id == project_id, WpIndex.wp_code == resolved.wp_codes[0],
                   WorkingPaper.is_deleted == sa.false())
            .order_by(WorkingPaper.id)
            .limit(1)
        )).scalar_one_or_none() or None

        codes = _section_account_codes(tuple(resolved.wp_codes))
        trace["account_codes"] = codes
        if not codes:
            trace["trial_balance_basis"] = trace["ledger_basis"] = "章节对应底稿没有映射科目，未取试算表与序时账"
            return trace
        if year is None:
            from app.services.project_audit_year import fetch_project_audit_year

            year = await fetch_project_audit_year(db, project_id)
        if year is None:
            trace["trial_balance_basis"] = trace["ledger_basis"] = "项目未设置审计年度，未取试算表与序时账"
            return trace
        trace["year"] = year
        scope = "、".join(codes)

        # 3. 试算表：本年度、这些科目，全部主体合计
        tb = TrialBalance
        tb_rows = (await db.execute(
            sa.select(
                tb.standard_account_code, sa.func.max(tb.account_name), sa.func.sum(tb.opening_balance),
                sa.func.sum(tb.unadjusted_amount), sa.func.sum(tb.audited_amount),
            )
            .where(tb.project_id == project_id, tb.year == year, tb.is_deleted == sa.false(),
                   tb.standard_account_code.in_(codes))
            .group_by(tb.standard_account_code)
            .order_by(tb.standard_account_code)
        )).all()
        trace["trial_balance_data"] = [
            {"account_code": code, "account_name": name, "opening": float(opening or 0),
             "unadjusted": float(unadjusted or 0), "audited": float(audited or 0)}
            for code, name, opening, unadjusted, audited in tb_rows
        ]
        trace["trial_balance_basis"] = f"{year} 年度试算表，科目 {scope}，全部主体合计"

        # 4. 序时账：本年度当前账套、科目以这些科目开头，按 |借 − 贷| 降序前 10 笔
        lg = TbLedger
        net = sa.func.abs(sa.func.coalesce(lg.debit_amount, 0) - sa.func.coalesce(lg.credit_amount, 0))
        ledger_rows = (await db.execute(
            sa.select(lg)
            .where(await get_active_filter(db, lg.__table__, project_id, year, strict=True),
                   sa.or_(*[lg.account_code.startswith(c, autoescape=True) for c in codes]))
            .order_by(net.desc(), lg.voucher_date, lg.voucher_no, lg.id)
            .limit(TOP_LEDGER_LIMIT)
        )).scalars().all()
        trace["top_ledger_entries"] = [
            {"voucher_no": r.voucher_no, "date": r.voucher_date.isoformat() if r.voucher_date else None,
             "account_code": r.account_code, "debit": float(r.debit_amount or 0),
             "credit": float(r.credit_amount or 0), "summary": r.summary or ""}
            for r in ledger_rows
        ]
        trace["ledger_basis"] = f"{year} 年度当前账套序时账，科目以 {scope} 开头，按金额（借贷差的绝对值）降序前 {TOP_LEDGER_LIMIT} 笔"
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
                "SELECT COUNT(*) FROM ai_content_log "
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

    # 一个章节可对应多张底稿（注册表复数章节 / 项目自定义映射）：每张底稿一个 sheet 级目标，
    # 不能只给第一张（原先 G1 / G10 这类复数章节只能跳到第一张）。披露 sheet 只从首张底稿的数据里取得到。
    wp_codes = [c for c in (note_data.get("wp_codes") or [base_wp_code]) if c]
    if base_wp_code not in wp_codes:
        wp_codes.insert(0, base_wp_code)
    for code in dict.fromkeys(wp_codes):
        targets.append(LocateTarget(
            wp_code=code,
            wp_id=None,
            sheet_name=sheet_name if code == base_wp_code else None,
            cell_ref=None,  # sheet 级降级：无 cell 精度
            component_type=None,
            value=None,
            label=note_data.get("note_title"),
        ))

    return targets
