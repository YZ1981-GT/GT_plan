# -*- coding: utf-8 -*-
"""回收站 API - 查询/恢复/永久删除已软删除的数据

支持：项目、底稿、附件、调整分录等所有软删除记录。
回收站容量上限可配置，超限时提示用户清理。
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.bulk_operations import BulkRequest, bulk_hard_delete
from app.core.database import get_db
from app.core.pagination import PaginationParams
from app.deps import get_current_user
from app.models.core import Project, User

router = APIRouter(prefix="/api/recycle-bin", tags=["recycle-bin"])

# 回收站容量上限（条数），超过时前端提示清理
RECYCLE_BIN_LIMIT = 500

# 支持回收站的表（表名 -> ORM 模型）
_RECYCLABLE_TABLES: dict[str, tuple] = {}


def _get_recyclable_tables() -> dict:
    """延迟加载可回收的表（避免循环导入）"""
    global _RECYCLABLE_TABLES
    if not _RECYCLABLE_TABLES:
        from app.models.core import Project
        from app.models.audit_platform_models import (
            Adjustment, TbBalance, TbLedger, TbAuxBalance, TbAuxLedger,
            AccountChart, AccountMapping, TrialBalance, ImportBatch,
        )
        from app.models.report_models import (
            FinancialReport, DisclosureNote, AuditReport, ExportTask,
        )
        from app.models.workpaper_models import (
            WorkingPaper, WpTemplate, ReviewRecord,
        )
        from app.models.attachment_models import Attachment

        _RECYCLABLE_TABLES = {
            "project": (Project, "项目", "name"),
            "adjustment": (Adjustment, "调整分录", "account_code"),
            "working_paper": (WorkingPaper, "底稿", "wp_code"),
            "attachment": (Attachment, "附件", "file_name"),
            "account_chart": (AccountChart, "科目", "account_code"),
            "account_mapping": (AccountMapping, "科目映射", "original_account_code"),
            "trial_balance": (TrialBalance, "试算表", "standard_account_code"),
            "financial_report": (FinancialReport, "报表", "row_name"),
            "disclosure_note": (DisclosureNote, "附注", "section_code"),
            "audit_report": (AuditReport, "审计报告", "title"),
            "wp_template": (WpTemplate, "底稿模板", "template_name"),
            "review_record": (ReviewRecord, "复核记录", "id"),
        }
    return _RECYCLABLE_TABLES


@router.get("")
async def list_recycle_bin(
    item_type: str | None = Query(None, description="筛选类型：project/adjustment/working_paper/attachment 等"),
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """查询回收站中的所有已删除记录"""
    tables = _get_recyclable_tables()
    items = []
    total = 0

    target_tables = {item_type: tables[item_type]} if item_type and item_type in tables else tables

    for tbl_key, (model, label, name_field) in target_tables.items():
        if not hasattr(model, "is_deleted"):
            continue

        try:
            # 计数
            count_q = select(func.count()).select_from(model).where(model.is_deleted == True)  # noqa: E712
            count_result = await db.execute(count_q)
            tbl_count = count_result.scalar() or 0
            total += tbl_count

            if tbl_count == 0:
                continue

            # 查询记录 — 优先按 deleted_at 排序，无该列则按 id 排序
            try:
                order_col = model.deleted_at.desc()
            except AttributeError:
                order_col = model.id.desc()

            q = (
                select(model)
                .where(model.is_deleted == True)  # noqa: E712
                .order_by(order_col)
                .limit(pagination.limit)
            )
            result = await db.execute(q)
            rows = result.scalars().all()

            for row in rows:
                name_val = getattr(row, name_field, None) if hasattr(row, name_field) else str(row.id)
                deleted_at = getattr(row, "deleted_at", None) or getattr(row, "updated_at", None)
                items.append({
                    "id": str(row.id),
                    "type": tbl_key,
                    "type_label": label,
                    "name": str(name_val) if name_val else str(row.id)[:8],
                    "deleted_at": deleted_at.isoformat() if deleted_at else None,
                    "project_id": str(getattr(row, "project_id", "")) if hasattr(row, "project_id") else None,
                })
        except Exception as e:
            # 单个表查询失败不阻断其他表
            import logging
            logging.getLogger(__name__).warning(f"回收站查询 {tbl_key} 失败: {e}")
            continue

    # 按删除时间排序
    items.sort(key=lambda x: x.get("deleted_at") or "", reverse=True)

    # 分页
    start = pagination.offset
    paged_items = items[start:start + pagination.page_size]

    return {
        "items": paged_items,
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
        "limit": RECYCLE_BIN_LIMIT,
        "is_over_limit": total > RECYCLE_BIN_LIMIT,
    }


@router.post("/{item_type}/{item_id}/restore")
async def restore_item(
    item_type: str,
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """恢复已删除的记录"""
    tables = _get_recyclable_tables()
    if item_type not in tables:
        raise HTTPException(status_code=400, detail=f"不支持的类型: {item_type}")

    model, label, _ = tables[item_type]
    result = await db.execute(
        select(model).where(model.id == item_id, model.is_deleted == True)  # noqa: E712
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="记录不存在或未被删除")

    row.is_deleted = False
    if hasattr(row, "deleted_at"):
        row.deleted_at = None
    await db.commit()

    return {"message": f"{label}已恢复", "id": str(item_id)}


@router.delete("/{item_type}/{item_id}")
async def permanently_delete(
    item_type: str,
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """永久删除记录（不可恢复）"""
    tables = _get_recyclable_tables()
    if item_type not in tables:
        raise HTTPException(status_code=400, detail=f"不支持的类型: {item_type}")

    model, label, _ = tables[item_type]
    result = await db.execute(
        select(model).where(model.id == item_id, model.is_deleted == True)  # noqa: E712
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="记录不存在或未被删除")

    await db.delete(row)
    await db.commit()

    return {"message": f"{label}已永久删除", "id": str(item_id)}


@router.post("/batch-delete")
async def batch_permanently_delete(
    body: BulkRequest,
    item_type: str = Query(..., description="记录类型：project/adjustment/working_paper 等"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """批量永久删除回收站中的记录（不可恢复）"""
    tables = _get_recyclable_tables()
    if item_type not in tables:
        raise HTTPException(status_code=400, detail=f"不支持的类型: {item_type}")

    model, label, _ = tables[item_type]
    result = await bulk_hard_delete(db, model, body.ids, filter_deleted=True)
    await db.commit()
    return result


@router.post("/empty")
async def empty_recycle_bin(
    item_type: str | None = Query(None, description="清空指定类型，不传则清空全部"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """清空回收站（永久删除所有已软删除的记录）"""
    tables = _get_recyclable_tables()
    target_tables = {item_type: tables[item_type]} if item_type and item_type in tables else tables

    deleted_count = 0
    errors = []
    for tbl_key, (model, label, _) in target_tables.items():
        if not hasattr(model, "is_deleted"):
            continue
        try:
            result = await db.execute(
                delete(model).where(model.is_deleted == True)  # noqa: E712
            )
            deleted_count += result.rowcount
        except Exception as exc:
            # FK 约束等错误时跳过该表，继续处理其他表
            await db.rollback()
            errors.append(f"{label}: {str(exc)[:100]}")

    await db.commit()
    resp: dict = {"message": f"已永久删除 {deleted_count} 条记录", "deleted_count": deleted_count}
    if errors:
        resp["warnings"] = errors
        resp["message"] += f"（{len(errors)} 个类型因关联数据无法清空）"
    return resp


@router.get("/stats")
async def recycle_bin_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """回收站统计（各类型数量）"""
    tables = _get_recyclable_tables()
    stats = {}
    total = 0

    for tbl_key, (model, label, _) in tables.items():
        if not hasattr(model, "is_deleted"):
            continue
        count_q = select(func.count()).select_from(model).where(model.is_deleted == True)  # noqa: E712
        count_result = await db.execute(count_q)
        count = count_result.scalar() or 0
        if count > 0:
            stats[tbl_key] = {"label": label, "count": count}
        total += count

    return {
        "total": total,
        "limit": RECYCLE_BIN_LIMIT,
        "is_over_limit": total > RECYCLE_BIN_LIMIT,
        "by_type": stats,
    }
