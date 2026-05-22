"""EQCR 快照服务 — 聚合项目数据生成只读快照供 EQCR 独立复核使用。

快照数据结构:
{
    "workpapers": [...],
    "reports": {...},
    "adjustments": [...],
    "vr_results": [...],
    "metadata": { "snapshot_version": 1, "total_workpapers": N, "signed_workpapers": N }
}
"""

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import Adjustment
from app.models.report_models import FinancialReport
from app.models.workpaper_models import WpIndex, WorkingPaper


async def _aggregate_workpapers(db: AsyncSession, project_id: uuid.UUID) -> list[dict]:
    """聚合项目底稿状态数据。"""
    result = await db.execute(
        select(
            WorkingPaper.id,
            WpIndex.wp_code,
            WorkingPaper.status,
            WorkingPaper.review_status,
            WorkingPaper.file_version,
            WorkingPaper.updated_at,
        )
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == False,  # noqa: E712
        )
    )
    rows = result.all()
    return [
        {
            "wp_id": str(r.id),
            "wp_code": r.wp_code,
            "status": r.status.value if hasattr(r.status, "value") else str(r.status),
            "review_status": (
                r.review_status.value
                if hasattr(r.review_status, "value")
                else str(r.review_status)
            ),
            "version": r.file_version,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]


async def _aggregate_reports(
    db: AsyncSession, project_id: uuid.UUID, year: int
) -> dict[str, list[dict]]:
    """聚合项目报表数据（按报表类型分组）。"""
    result = await db.execute(
        select(FinancialReport).where(
            FinancialReport.project_id == project_id,
            FinancialReport.year == year,
            FinancialReport.is_deleted == False,  # noqa: E712
        )
    )
    reports = result.scalars().all()
    grouped: dict[str, list[dict]] = {}
    for r in reports:
        rtype = r.report_type.value if hasattr(r.report_type, "value") else str(r.report_type)
        if rtype not in grouped:
            grouped[rtype] = []
        grouped[rtype].append(
            {
                "row_code": r.row_code,
                "row_name": r.row_name,
                "current_period_amount": (
                    float(r.current_period_amount) if r.current_period_amount else None
                ),
                "prior_period_amount": (
                    float(r.prior_period_amount) if r.prior_period_amount else None
                ),
            }
        )
    return grouped


async def _aggregate_adjustments(
    db: AsyncSession, project_id: uuid.UUID, year: int
) -> list[dict]:
    """聚合项目调整分录数据。"""
    result = await db.execute(
        select(Adjustment).where(
            Adjustment.project_id == project_id,
            Adjustment.year == year,
            Adjustment.is_deleted == False,  # noqa: E712
        )
    )
    adjustments = result.scalars().all()
    return [
        {
            "id": str(a.id),
            "adjustment_type": (
                a.adjustment_type.value
                if hasattr(a.adjustment_type, "value")
                else str(a.adjustment_type)
            ),
            "adjustment_no": a.adjustment_no,
            "account_code": a.account_code,
            "account_name": a.account_name,
            "debit_amount": float(a.debit_amount) if a.debit_amount else None,
            "credit_amount": float(a.credit_amount) if a.credit_amount else None,
            "review_status": (
                a.review_status.value
                if hasattr(a.review_status, "value")
                else str(a.review_status)
            ),
            "description": a.description,
        }
        for a in adjustments
    ]


async def _aggregate_vr_results(
    db: AsyncSession, project_id: uuid.UUID, year: int
) -> list[dict]:
    """聚合项目校验规则结果。

    VR 结果存储在 consistency_gate 服务中，这里查询 note_validation_results 表
    作为 VR 数据来源。如果表不存在或无数据，返回空列表。
    """
    from app.models.report_models import NoteValidationResult

    try:
        result = await db.execute(
            select(NoteValidationResult).where(
                NoteValidationResult.project_id == project_id,
                NoteValidationResult.year == year,
            )
        )
        vr_rows = result.scalars().all()
        return [
            {
                "rule_id": str(v.id),
                "passed": getattr(v, "passed", None),
                "severity": getattr(v, "severity", None),
            }
            for v in vr_rows
        ]
    except Exception:
        # 表可能不存在或字段不匹配，降级返回空
        return []


def _build_metadata(workpapers: list[dict]) -> dict:
    """构建快照元数据。"""
    total = len(workpapers)
    signed = sum(1 for wp in workpapers if wp.get("status") == "signed")
    return {
        "snapshot_version": 1,
        "total_workpapers": total,
        "signed_workpapers": signed,
    }


async def create_snapshot(
    db: AsyncSession,
    project_id: uuid.UUID,
    year: int,
    user_id: uuid.UUID,
) -> dict:
    """创建 EQCR 快照。

    聚合底稿+报表+AJE+VR 数据，写入 eqcr_snapshots 表。
    如果已存在 is_current=True 的快照，先将其标记为 False。

    Returns:
        新创建的快照记录（dict 形式）
    """
    from sqlalchemy import text as sql_text

    # 1. 聚合数据
    workpapers = await _aggregate_workpapers(db, project_id)
    reports = await _aggregate_reports(db, project_id, year)
    adjustments = await _aggregate_adjustments(db, project_id, year)
    vr_results = await _aggregate_vr_results(db, project_id, year)
    metadata = _build_metadata(workpapers)

    snapshot_data = {
        "workpapers": workpapers,
        "reports": reports,
        "adjustments": adjustments,
        "vr_results": vr_results,
        "metadata": metadata,
    }

    # 2. 将旧的 is_current=True 快照标记为 False
    await db.execute(
        sql_text(
            "UPDATE eqcr_snapshots SET is_current = FALSE "
            "WHERE project_id = :pid AND year = :year AND is_current = TRUE"
        ),
        {"pid": str(project_id), "year": year},
    )

    # 3. 插入新快照
    snapshot_id = uuid.uuid4()
    now = datetime.utcnow()
    await db.execute(
        sql_text(
            "INSERT INTO eqcr_snapshots (id, project_id, year, created_by, created_at, snapshot_data, is_current) "
            "VALUES (:id, :pid, :year, :uid, :now, :data::jsonb, TRUE)"
        ),
        {
            "id": str(snapshot_id),
            "pid": str(project_id),
            "year": year,
            "uid": str(user_id),
            "now": now,
            "data": __import__("json").dumps(snapshot_data, ensure_ascii=False),
        },
    )
    await db.commit()

    return {
        "id": str(snapshot_id),
        "project_id": str(project_id),
        "year": year,
        "created_by": str(user_id),
        "created_at": now.isoformat(),
        "snapshot_data": snapshot_data,
        "is_current": True,
    }


async def get_current_snapshot(
    db: AsyncSession,
    project_id: uuid.UUID,
    year: int,
) -> dict | None:
    """获取当前有效快照。

    Returns:
        快照记录（dict）或 None（无快照时）
    """
    from sqlalchemy import text as sql_text

    result = await db.execute(
        sql_text(
            "SELECT id, project_id, year, created_by, created_at, snapshot_data, is_current "
            "FROM eqcr_snapshots "
            "WHERE project_id = :pid AND year = :year AND is_current = TRUE "
            "LIMIT 1"
        ),
        {"pid": str(project_id), "year": year},
    )
    row = result.mappings().first()
    if row is None:
        return None

    import json

    snapshot_data = row["snapshot_data"]
    if isinstance(snapshot_data, str):
        snapshot_data = json.loads(snapshot_data)

    return {
        "id": str(row["id"]),
        "project_id": str(row["project_id"]),
        "year": row["year"],
        "created_by": str(row["created_by"]),
        "created_at": (
            row["created_at"].isoformat()
            if hasattr(row["created_at"], "isoformat")
            else str(row["created_at"])
        ),
        "snapshot_data": snapshot_data,
        "is_current": row["is_current"],
    }


async def refresh_snapshot(
    db: AsyncSession,
    project_id: uuid.UUID,
    year: int,
    user_id: uuid.UUID,
) -> dict:
    """刷新快照：将旧快照标记为非当前，创建新快照。

    与 create_snapshot 逻辑相同，但语义上是"刷新"（EQCR 合伙人主动触发）。

    Returns:
        新创建的快照记录（dict 形式）
    """
    return await create_snapshot(db, project_id, year, user_id)
