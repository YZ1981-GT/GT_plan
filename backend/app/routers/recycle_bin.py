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


async def _cascade_delete_project(db: AsyncSession, project_id: UUID) -> None:
    """级联删除单个项目及其所有关联数据。

    使用 session_replication_role = replica 临时禁用 FK 触发器，
    直接删除所有引用该项目的子表数据，最后删项目本身。
    """
    import sqlalchemy as sa

    pid = str(project_id)

    # 临时禁用 FK 检查（当前 session 内有效）
    await db.execute(sa.text("SET session_replication_role = 'replica'"))

    try:
        # 查出所有引用 projects.id 的子表
        fk_query = sa.text("""
            SELECT DISTINCT tc.table_name, kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND ccu.table_name = 'projects'
              AND tc.table_name != 'projects'
        """)
        result = await db.execute(fk_query)
        child_tables = [(row[0], row[1]) for row in result.fetchall()]

        # 逐表删除
        for table_name, column_name in child_tables:
            try:
                await db.execute(
                    sa.text(f'DELETE FROM "{table_name}" WHERE "{column_name}" = :pid::uuid'),
                    {"pid": pid},
                )
            except Exception:
                pass

        # 处理自引用
        await db.execute(
            sa.text("UPDATE projects SET parent_project_id = NULL WHERE parent_project_id = :pid::uuid"),
            {"pid": pid},
        )

        # 删项目本身
        await db.execute(sa.text("DELETE FROM projects WHERE id = :pid::uuid"), {"pid": pid})
    finally:
        # 恢复 FK 检查
        await db.execute(sa.text("SET session_replication_role = 'origin'"))


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

    # 项目类型需要级联删除子表
    if item_type == "project":
        await _cascade_delete_project(db, item_id)
    else:
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
    """清空回收站（永久删除所有已软删除的记录）

    对于项目类型，需要按 FK 依赖顺序级联删除子表数据。
    """
    import sqlalchemy as sa

    tables = _get_recyclable_tables()

    # 如果指定了非 project 类型，直接删
    if item_type and item_type != "project" and item_type in tables:
        model = tables[item_type][0]
        if hasattr(model, "is_deleted"):
            result = await db.execute(delete(model).where(model.is_deleted == True))  # noqa: E712
            await db.commit()
            return {"message": f"已永久删除 {result.rowcount} 条记录", "deleted_count": result.rowcount}
        return {"message": "该类型不支持软删除", "deleted_count": 0}

    # 获取待删除的项目 ID 列表
    deleted_project_ids_q = select(Project.id).where(Project.is_deleted == True)  # noqa: E712
    result = await db.execute(deleted_project_ids_q)
    deleted_pids = [row[0] for row in result.fetchall()]

    deleted_count = 0

    # 1. 先删非 project 类型的软删除记录（这些通常没有复杂 FK）
    for tbl_key, (model, label, _) in tables.items():
        if tbl_key == "project":
            continue
        if not hasattr(model, "is_deleted"):
            continue
        try:
            r = await db.execute(delete(model).where(model.is_deleted == True))  # noqa: E712
            deleted_count += r.rowcount
        except Exception:
            await db.rollback()

    # 2. 级联删除已删除项目
    if deleted_pids:
        for pid in deleted_pids:
            try:
                await _cascade_delete_project(db, pid)
            except Exception:
                pass
        deleted_count += len(deleted_pids)        deleted_count += len(deleted_pids)

    await db.commit()
    return {"message": f"已永久删除 {deleted_count} 条记录", "deleted_count": deleted_count}
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
