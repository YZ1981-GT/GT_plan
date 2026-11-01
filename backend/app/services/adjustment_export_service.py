"""调整分录完整 Excel 导出与 EQCR 快照投影。

四张工作表：汇总、明细、复核历史、处理与证据。
EQCR 快照的调整载荷也由本模块的 ``build_snapshot_projection`` 生成，
替代旧 ``eqcr_snapshot_service._aggregate_adjustments`` 的行级快照。
"""
from __future__ import annotations

import logging
from collections import defaultdict
from decimal import Decimal
from io import BytesIO
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import (
    Adjustment,
    AdjustmentEntry,
    AdjustmentType,
    ReviewStatus,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 统一投影：列表 + 富化 + 处理 + 风险 + 复核历史 + 证据
# ---------------------------------------------------------------------------

async def _load_full_groups(
    db: AsyncSession, project_id: UUID, year: int,
    adjustment_type: AdjustmentType | None = None,
) -> list[dict[str, Any]]:
    """分页取全部分录组并富化。"""
    from app.services.adjustment_service import AdjustmentService
    from app.services.adjustment_list_enrich import enrich_adjustment_list

    svc = AdjustmentService(db)
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        res = await svc.list_entries(
            project_id, year, adjustment_type=adjustment_type,
            page=page, page_size=500,
        )
        batch = res.get("items", []) if isinstance(res, dict) else list(res)
        items.extend(batch)
        if not batch or not isinstance(res, dict) or len(items) >= int(res.get("total") or 0):
            break
        page += 1
    try:
        await enrich_adjustment_list(db, project_id, items, year=year)
    except Exception as exc:  # noqa: BLE001
        logger.warning("导出富化失败 project=%s: %s", project_id, exc)
    return items


async def _load_review_history(
    db: AsyncSession, project_id: UUID, group_ids: list[UUID],
) -> dict[str, list[dict[str, Any]]]:
    """按组加载复核任务历史。"""
    from app.models.adjustment_review_models import AdjustmentReviewTask

    if not group_ids:
        return {}
    rows = list((await db.execute(sa.select(AdjustmentReviewTask).where(
        AdjustmentReviewTask.project_id == project_id,
        AdjustmentReviewTask.entry_group_id.in_(group_ids),
    ).order_by(
        AdjustmentReviewTask.entry_group_id,
        AdjustmentReviewTask.submitted_at,
        AdjustmentReviewTask.id,
    ))).scalars().all())
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in rows:
        out[str(task.entry_group_id)].append({
            "task_id": str(task.id),
            "status": task.status,
            "required_level": task.required_level,
            "revision": task.revision,
            "group_content_revision": task.group_content_revision,
            "assigned_reviewer_ids": [str(v) for v in (task.assigned_reviewer_ids or [])],
            "submitted_by": str(task.submitted_by),
            "submitted_at": task.submitted_at.isoformat() if task.submitted_at else None,
            "submit_note": task.submit_note,
            "decided_by": str(task.decided_by) if task.decided_by else None,
            "decided_at": task.decided_at.isoformat() if task.decided_at else None,
            "decision_reason": task.decision_reason,
        })
    return dict(out)


async def _load_evidence_refs(
    db: AsyncSession, project_id: UUID, year: int, group_ids: list[UUID],
) -> dict[str, list[dict[str, Any]]]:
    """按组加载活动证据引用。"""
    from app.services.adjustment_evidence_service import active_adjustment_evidence

    out: dict[str, list[dict[str, Any]]] = {}
    for gid in group_ids:
        try:
            refs = await active_adjustment_evidence(
                db, project_id=project_id, year=year, entry_group_id=gid,
            )
            if refs:
                out[str(gid)] = refs
        except Exception:  # noqa: BLE001
            pass
    return out


# ---------------------------------------------------------------------------
# 组装完整投影
# ---------------------------------------------------------------------------

async def build_full_projection(
    db: AsyncSession, project_id: UUID, year: int,
) -> dict[str, Any]:
    """构建包含四域信息的完整分录投影。"""
    aje = await _load_full_groups(db, project_id, year, AdjustmentType.aje)
    rje = await _load_full_groups(db, project_id, year, AdjustmentType.rje)
    all_items = aje + rje
    group_ids = [UUID(it["entry_group_id"]) for it in all_items if it.get("entry_group_id")]
    review_history = await _load_review_history(db, project_id, group_ids)
    evidence = await _load_evidence_refs(db, project_id, year, group_ids)
    for item in all_items:
        gid = str(item.get("entry_group_id", ""))
        item["review_history"] = review_history.get(gid, [])
        item["evidence_refs"] = evidence.get(gid, [])
    return {
        "aje": aje,
        "rje": rje,
        "aje_count": len(aje),
        "rje_count": len(rje),
        "total_count": len(all_items),
    }


# ---------------------------------------------------------------------------
# EQCR 快照投影
# ---------------------------------------------------------------------------

async def build_snapshot_projection(
    db: AsyncSession, project_id: UUID, year: int,
) -> list[dict[str, Any]]:
    """替代旧 ``_aggregate_adjustments``，复用完整投影。"""
    projection = await build_full_projection(db, project_id, year)
    return projection["aje"] + projection["rje"]


# ---------------------------------------------------------------------------
# Excel 四表导出
# ---------------------------------------------------------------------------

def _status_label(raw: Any) -> str:
    labels = {"draft": "草稿", "pending_review": "待复核", "approved": "已批准", "rejected": "已驳回"}
    value = str(getattr(raw, "value", raw) or "")
    return labels.get(value, value)


def _treatment_label(item: dict) -> str:
    treatment = item.get("treatment")
    if not treatment:
        return ""
    status = treatment.get("status", "")
    labels = {
        "include_in_working_tb": "纳入工作试算表",
        "client_booked": "客户已入账" if treatment.get("effective") else "已入账·未生效",
        "unadjusted_misstatement": "不予更正",
        "pending_internal_review": "待内部复核",
        "awaiting_workpaper_publish": "待底稿发布",
    }
    return labels.get(status, status)


def export_excel(projection: dict[str, Any], year: int) -> BytesIO:
    """生成四张工作表的 Excel。"""
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill

    wb = openpyxl.Workbook()
    header_fill = PatternFill(start_color="F4F0FA", end_color="F4F0FA", fill_type="solid")
    header_font = Font(bold=True, size=11)

    def _header(ws, headers: list[str]) -> None:
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=h)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")

    # ── Sheet 1: 汇总 ────────────────────────────────────────────────
    ws_summary = wb.active
    ws_summary.title = "汇总"
    _header(ws_summary, [
        "编号", "类型", "摘要", "借方合计", "贷方合计", "来源", "阶段",
        "复核状态", "编制人", "最终处理", "重要性比例%", "风险层级", "性质风险",
    ])
    row_idx = 2
    for item in projection["aje"] + projection["rje"]:
        risk = item.get("risk") or {}
        ws_summary.cell(row=row_idx, column=1, value=item.get("adjustment_no", ""))
        ws_summary.cell(row=row_idx, column=2, value="AJE" if str(item.get("adjustment_type", "")).lower() == "aje" else "RJE")
        ws_summary.cell(row=row_idx, column=3, value=item.get("description", ""))
        ws_summary.cell(row=row_idx, column=4, value=float(item.get("total_debit") or 0))
        ws_summary.cell(row=row_idx, column=5, value=float(item.get("total_credit") or 0))
        ws_summary.cell(row=row_idx, column=6, value="底稿" if item.get("origin") == "workpaper" else "手工")
        ws_summary.cell(row=row_idx, column=7, value="预审" if item.get("audit_phase") == "preliminary" else "年审")
        ws_summary.cell(row=row_idx, column=8, value=_status_label(item.get("review_status")))
        ws_summary.cell(row=row_idx, column=9, value=item.get("creator_name", ""))
        ws_summary.cell(row=row_idx, column=10, value=_treatment_label(item))
        ws_summary.cell(row=row_idx, column=11, value=float(risk.get("performance_ratio") or 0))
        ws_summary.cell(row=row_idx, column=12, value="合伙人" if risk.get("required_level") == "partner" else "经理")
        ws_summary.cell(row=row_idx, column=13, value="、".join(f.get("label", "") for f in risk.get("risk_flags", [])))
        row_idx += 1

    # ── Sheet 2: 明细 ────────────────────────────────────────────────
    ws_detail = wb.create_sheet("明细")
    _header(ws_detail, [
        "编号", "类型", "摘要", "科目编码", "科目名称", "借方金额", "贷方金额",
        "来源", "所属循环", "编制人",
    ])
    row_idx = 2
    for item in projection["aje"] + projection["rje"]:
        adj_type = "AJE" if str(item.get("adjustment_type", "")).lower() == "aje" else "RJE"
        for li in item.get("line_items", []):
            ws_detail.cell(row=row_idx, column=1, value=item.get("adjustment_no", ""))
            ws_detail.cell(row=row_idx, column=2, value=adj_type)
            ws_detail.cell(row=row_idx, column=3, value=item.get("description", ""))
            ws_detail.cell(row=row_idx, column=4, value=li.get("standard_account_code", ""))
            ws_detail.cell(row=row_idx, column=5, value=li.get("account_name", ""))
            ws_detail.cell(row=row_idx, column=6, value=float(li.get("debit_amount") or 0))
            ws_detail.cell(row=row_idx, column=7, value=float(li.get("credit_amount") or 0))
            ws_detail.cell(row=row_idx, column=8, value="底稿" if item.get("origin") == "workpaper" else "手工")
            ws_detail.cell(row=row_idx, column=9, value=item.get("source_wp_code", ""))
            ws_detail.cell(row=row_idx, column=10, value=item.get("creator_name", ""))
            row_idx += 1

    # ── Sheet 3: 复核历史 ────────────────────────────────────────────
    ws_review = wb.create_sheet("复核历史")
    _header(ws_review, [
        "编号", "轮次", "状态", "层级要求", "指定复核人", "提交人", "提交时间",
        "提交备注", "决定人", "决定时间", "决定原因",
    ])
    row_idx = 2
    for item in projection["aje"] + projection["rje"]:
        for task in item.get("review_history", []):
            ws_review.cell(row=row_idx, column=1, value=item.get("adjustment_no", ""))
            ws_review.cell(row=row_idx, column=2, value=task.get("revision", 1))
            ws_review.cell(row=row_idx, column=3, value=task.get("status", ""))
            ws_review.cell(row=row_idx, column=4, value="合伙人" if task.get("required_level") == "partner" else "经理")
            ws_review.cell(row=row_idx, column=5, value="、".join(task.get("assigned_reviewer_ids", [])))
            ws_review.cell(row=row_idx, column=6, value=task.get("submitted_by", ""))
            ws_review.cell(row=row_idx, column=7, value=task.get("submitted_at", ""))
            ws_review.cell(row=row_idx, column=8, value=task.get("submit_note", ""))
            ws_review.cell(row=row_idx, column=9, value=task.get("decided_by", ""))
            ws_review.cell(row=row_idx, column=10, value=task.get("decided_at", ""))
            ws_review.cell(row=row_idx, column=11, value=task.get("decision_reason", ""))
            row_idx += 1

    # ── Sheet 4: 处理与证据 ──────────────────────────────────────────
    ws_evidence = wb.create_sheet("处理与证据")
    _header(ws_evidence, [
        "编号", "最终处理", "客户入账凭证", "证据类型", "证据说明", "证据版本", "关联时间",
    ])
    row_idx = 2
    for item in projection["aje"] + projection["rje"]:
        treatment = item.get("treatment") or {}
        booking = item.get("client_booking") or {}
        refs = item.get("evidence_refs", [])
        if not refs:
            ws_evidence.cell(row=row_idx, column=1, value=item.get("adjustment_no", ""))
            ws_evidence.cell(row=row_idx, column=2, value=_treatment_label(item))
            ws_evidence.cell(row=row_idx, column=3, value="、".join(booking.get("voucher_keys", [])))
            row_idx += 1
        else:
            for ref in refs:
                ws_evidence.cell(row=row_idx, column=1, value=item.get("adjustment_no", ""))
                ws_evidence.cell(row=row_idx, column=2, value=_treatment_label(item))
                ws_evidence.cell(row=row_idx, column=3, value="、".join(booking.get("voucher_keys", [])))
                ws_evidence.cell(row=row_idx, column=4, value=ref.get("evidence_type", ""))
                ws_evidence.cell(row=row_idx, column=5, value=ref.get("label", ""))
                ws_evidence.cell(row=row_idx, column=6, value=str(ref.get("target_version", "")))
                ws_evidence.cell(row=row_idx, column=7, value=ref.get("created_at", ""))
                row_idx += 1

    # 列宽
    for ws in [ws_summary, ws_detail, ws_review, ws_evidence]:
        for col_letter in "ABCDEFGHIJKLM":
            ws.column_dimensions[col_letter].width = 16

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
