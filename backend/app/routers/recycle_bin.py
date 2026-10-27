# -*- coding: utf-8 -*-
"""回收站 API - 查询/恢复/永久删除已软删除的数据

支持：项目、底稿、附件、调整分录等所有软删除记录。
回收站容量上限可配置，超限时提示用户清理。

spec procedure-trim-generation-delegation-chain 需求 3.5：
- 底稿按 ``wp_index`` 列出（名称 = 编码 + 底稿名），恢复时 ``wp_index`` 与名下 ``working_paper`` 两层一起恢复；
  仍在程序裁剪中标为不执行的底稿不能直接恢复（先在程序裁剪中恢复执行，会自动从回收站恢复）。
- 底稿不支持彻底删除（409）：两层软删保留审计轨迹，硬删还会撞复核意见 / 附件 / 任务等外键。
- 列表与统计只含当前用户是成员的项目（admin 全部），不属于任何项目的记录只给 admin；恢复 / 彻底删除校验
  该行所属项目的编制权限；清空只给 admin。原先全部端点只校验登录，任何人可恢复 / 删除任何项目的数据。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.bulk_operations import BulkRequest, bulk_hard_delete
from app.core.database import get_db
from app.core.pagination import PaginationParams
from app.deps import assert_project_permission, get_current_user
from app.models.core import Project, ProjectUser, User

router = APIRouter(prefix="/api/recycle-bin", tags=["recycle-bin"])

# 回收站容量上限（条数），超过时前端提示清理
RECYCLE_BIN_LIMIT = 500

#: 底稿：两层软删，不支持彻底删除
WORKPAPER_TYPE = "working_paper"
WORKPAPER_PURGE_FORBIDDEN = {
    "error": "workpaper_purge_forbidden",
    "message": "底稿不支持彻底删除：移入回收站的底稿保留编制内容与审计轨迹，需要时可随时恢复",
}

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
            WpIndex, WpTemplate, ReviewRecord,
        )
        from app.models.attachment_models import Attachment

        _RECYCLABLE_TABLES = {
            "project": (Project, "项目", "name"),
            "adjustment": (Adjustment, "调整分录", "account_code"),
            # 底稿按索引列出（编码 + 名称）；原按 working_paper 列出，该表没有编码列 ⇒ 只显示 id 前 8 位
            WORKPAPER_TYPE: (WpIndex, "底稿", "wp_code"),
            "attachment": (Attachment, "附件", "file_name"),
            "account_chart": (AccountChart, "科目", "account_code"),
            "account_mapping": (AccountMapping, "科目映射", "original_account_code"),
            "trial_balance": (TrialBalance, "试算表", "standard_account_code"),
            "financial_report": (FinancialReport, "报表", "row_name"),
            # 名称列：章节号（原写 ``section_code``，附注表没有这一列 ⇒ 列表里附注只显示 id 前 8 位）
            "disclosure_note": (DisclosureNote, "附注", "note_section"),
            "audit_report": (AuditReport, "审计报告", "title"),
            "wp_template": (WpTemplate, "底稿模板", "template_name"),
            "review_record": (ReviewRecord, "复核记录", "id"),
        }
    return _RECYCLABLE_TABLES


def _is_admin(user: User) -> bool:
    return getattr(user.role, "value", user.role) == "admin"


async def _visible_project_ids(db: AsyncSession, user: User) -> set[UUID] | None:
    """当前用户可见的项目（``None`` = 不限，admin）。"""
    if _is_admin(user):
        return None
    rows = await db.execute(
        select(ProjectUser.project_id).where(ProjectUser.user_id == user.id, ProjectUser.is_deleted == False)  # noqa: E712
    )
    return {r[0] for r in rows.all()}


def _visibility_filter(tbl_key: str, model, visible: set[UUID] | None):
    """列表 / 统计的项目过滤条件；``False`` = 该类型对当前用户整体不可见。"""
    if visible is None:
        return None
    if tbl_key == "project":
        return model.id.in_(visible) if visible else False
    if not hasattr(model, "project_id"):
        return False  # 不属于任何项目（如底稿模板）只给 admin
    return model.project_id.in_(visible) if visible else False


def _row_project_id(item_type: str, row) -> UUID | None:
    return row.id if item_type == "project" else getattr(row, "project_id", None)


async def _authorize_row(db: AsyncSession, user: User, item_type: str, row) -> None:
    """恢复 / 彻底删除：admin 放行；其余须是该行所属项目的编制（edit）成员；无项目归属的只给 admin。"""
    if _is_admin(user):
        return
    project_id = _row_project_id(item_type, row)
    if project_id is None:
        raise HTTPException(status_code=403, detail="该记录不属于任何项目，仅管理员可操作")
    await assert_project_permission(db, user, project_id, "edit")


def _deleted_by(tbl_key: str, row) -> str | None:
    """返回删除人 user_id。

    - 底稿：回收站去向记录最后一条「移入」的操作人；
    - 项目：删除时写 ``updated_by`` 与 ``deleted_at``；
    - 其他类型：删除路径沿用 ``updated_by`` 作为操作人记录，旧数据没有该字段时留空。
    """
    if tbl_key == WORKPAPER_TYPE:
        from app.services.workpaper_recycle_service import last_recycle_actor

        return last_recycle_actor(getattr(row, "cross_ref_codes", None))
    updated_by = getattr(row, "updated_by", None)
    if updated_by is not None:
        return str(updated_by)
    return None


def _display_name(tbl_key: str, row, name_field: str) -> str:
    if tbl_key == WORKPAPER_TYPE:
        return f"{row.wp_code} {row.wp_name}".strip()
    name_val = getattr(row, name_field, None) if hasattr(row, name_field) else str(row.id)
    return str(name_val) if name_val else str(row.id)[:8]


async def _cascade_delete_project(db: AsyncSession, project_id: UUID) -> None:
    """级联删除单个项目及其所有关联数据。

    使用独立的 raw connection + session_replication_role=replica 禁用 FK，
    绕过 SQLAlchemy session 的事务管理避免 rollback 污染。
    """
    from app.core.database import async_engine

    pid = str(project_id)

    async with async_engine.connect() as conn:
        # 获取底层 asyncpg connection 设置 autocommit-like 行为
        raw = await conn.get_raw_connection()
        pg_conn = raw.driver_connection  # asyncpg connection

        # 禁用 FK 检查
        await pg_conn.execute("SET session_replication_role = 'replica'")

        try:
            # 查出所有引用 projects.id 的子表
            rows = await pg_conn.fetch("""
                SELECT DISTINCT tc.table_name, kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND ccu.table_name = 'projects'
                  AND tc.table_name != 'projects'
            """)

            # 逐表删除
            for row in rows:
                table_name = row["table_name"]
                column_name = row["column_name"]
                try:
                    await pg_conn.execute(
                        f'DELETE FROM "{table_name}" WHERE "{column_name}" = $1::uuid', pid
                    )
                except Exception:
                    pass

            # 处理自引用
            try:
                await pg_conn.execute(
                    "UPDATE projects SET parent_project_id = NULL WHERE parent_project_id = $1::uuid", pid
                )
            except Exception:
                pass

            # 删项目本身
            await pg_conn.execute("DELETE FROM projects WHERE id = $1::uuid", pid)
        finally:
            # 恢复 FK 检查
            await pg_conn.execute("SET session_replication_role = 'origin'")


@router.get("")
async def list_recycle_bin(
    item_type: str | None = Query(None, description="筛选类型：project/adjustment/working_paper/attachment 等"),
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """查询回收站中的已删除记录（只含当前用户是成员的项目，admin 全部）"""
    tables = _get_recyclable_tables()
    visible = await _visible_project_ids(db, user)
    items = []
    total = 0

    target_tables = {item_type: tables[item_type]} if item_type and item_type in tables else tables

    for tbl_key, (model, label, name_field) in target_tables.items():
        if not hasattr(model, "is_deleted"):
            continue
        scope = _visibility_filter(tbl_key, model, visible)
        if scope is False:
            continue

        try:
            conds = [model.is_deleted == True]  # noqa: E712
            if scope is not None:
                conds.append(scope)
            # 计数
            count_q = select(func.count()).select_from(model).where(*conds)
            count_result = await db.execute(count_q)
            tbl_count = count_result.scalar() or 0
            total += tbl_count

            if tbl_count == 0:
                continue

            # 查询记录 —— 排序键与下面合并排序同一个：删除时间（deleted_at，旧记录没有就用 updated_at）倒序、空值在后。
            # 🔴 原先按 deleted_at 倒序：PG 倒序空值排最前，旧记录 deleted_at 全空 ⇒ 新删的（有 deleted_at）排到所有旧记录之后，
            #    每表又只取一页 ⇒ 刚删的项目在回收站里看不到；且每表只取 page_size 条 ⇒ 单类型第 2 页起恒空。
            #    每表取 offset + page_size 条：多表合并后的前 offset + page_size 条一定都在里面。
            if hasattr(model, "deleted_at") and hasattr(model, "updated_at"):
                order_expr = func.coalesce(model.deleted_at, model.updated_at).desc().nulls_last()
            elif hasattr(model, "deleted_at"):
                order_expr = model.deleted_at.desc().nulls_last()
            elif hasattr(model, "updated_at"):
                order_expr = model.updated_at.desc().nulls_last()
            else:
                order_expr = model.id
            q = (
                select(model)
                .where(*conds)
                .order_by(order_expr, model.id)
                .limit(pagination.offset + pagination.page_size)
            )
            result = await db.execute(q)
            rows = result.scalars().all()

            for row in rows:
                deleted_at = getattr(row, "deleted_at", None) or getattr(row, "updated_at", None)
                items.append({
                    "id": str(row.id),
                    "type": tbl_key,
                    "type_label": label,
                    "name": _display_name(tbl_key, row, name_field),
                    "deleted_at": deleted_at.isoformat() if deleted_at else None,
                    "deleted_by": _deleted_by(tbl_key, row),
                    "project_id": str(getattr(row, "project_id", "")) if hasattr(row, "project_id") else None,
                    "purgeable": tbl_key != WORKPAPER_TYPE,
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
    # 底稿删除人：先读生命周期事件（spec procedure-chain-hardening-and-java-contracts R18），没有事件的旧数据沿用去向记录
    from app.services.workpaper_recycle_service import latest_recycle_actors

    wp_items = [i for i in paged_items if i["type"] == WORKPAPER_TYPE]
    if wp_items:
        actors = await latest_recycle_actors(db, [UUID(i["id"]) for i in wp_items])
        for item in wp_items:
            wid = UUID(item["id"])
            if wid in actors:
                item["deleted_by"] = actors[wid]
    # 删除人显示名（原先列表项没有删除人，回收站「删除人」恒空，spec procedure-chain-followup-closure R3.2）
    from app.services.user_display_names import resolve_user_display_names

    names = await resolve_user_display_names(db, {i["deleted_by"] for i in paged_items if i["deleted_by"]})
    for item in paged_items:
        item["deleted_by_name"] = names.get(item["deleted_by"]) if item["deleted_by"] else None

    return {
        "items": paged_items,
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
        "limit": RECYCLE_BIN_LIMIT,
        "is_over_limit": total > RECYCLE_BIN_LIMIT,
    }


async def _restore_workpaper(db: AsyncSession, user: User, row) -> None:
    """底稿两层恢复；仍在程序裁剪中标为不执行的不恢复（否则恢复出来也不能委派、生成会再跳过）。"""
    from app.services.procedure_scope_retention import TrimScopeUnavailable, load_trimmed_scope
    from app.services.workpaper_recycle_service import restore_from_recycle_bin

    try:
        scope = await load_trimmed_scope(db, row.project_id)
    except TrimScopeUnavailable as e:
        raise HTTPException(status_code=503, detail=e.http_detail())
    owner = scope.trim_owner(row.wp_code)
    if owner:
        raise HTTPException(status_code=409, detail={
            "error": "workpaper_still_trimmed",
            "message": f"底稿 {row.wp_code} 仍在程序裁剪中标为不执行（{owner}），请先在程序裁剪中恢复执行，"
                       "恢复执行会自动把它从回收站恢复",
        })
    await restore_from_recycle_bin(db, row.project_id, [row.wp_code], kind=None, reason="从回收站恢复",
                                   actor_user_id=user.id)


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
    await _authorize_row(db, user, item_type, row)

    if item_type == WORKPAPER_TYPE:
        await _restore_workpaper(db, user, row)
        await db.commit()
        return {"message": f"{label}已恢复", "id": str(item_id)}

    row.is_deleted = False
    if hasattr(row, "deleted_at"):
        row.deleted_at = None
    if item_type == "disclosure_note":
        # 恢复附注章节 = 用户编辑附注：与编辑器「恢复章节」同样盖「最近一次编辑」
        # （spec disclosure-note-template-word-realignment Task 17）
        from app.services.note_edit_stamp import stamp_note_edit

        stamp_note_edit(row, user.id)
    if item_type == "project":
        # consol-tree-three-code-autobuild 需求 7.2：恢复项目后按三码重算本年度派生链接
        from app.services.group_links import sync_group_links_for

        await sync_group_links_for(db, row)
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
    if item_type == WORKPAPER_TYPE:
        raise HTTPException(status_code=409, detail=WORKPAPER_PURGE_FORBIDDEN)

    model, label, _ = tables[item_type]
    result = await db.execute(
        select(model).where(model.id == item_id, model.is_deleted == True)  # noqa: E712
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="记录不存在或未被删除")
    await _authorize_row(db, user, item_type, row)

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
    if item_type == WORKPAPER_TYPE:
        raise HTTPException(status_code=409, detail=WORKPAPER_PURGE_FORBIDDEN)

    model, label, _ = tables[item_type]
    rows = (await db.execute(
        select(model).where(model.id.in_(body.ids), model.is_deleted == True)  # noqa: E712
    )).scalars().all()
    for row in rows:
        await _authorize_row(db, user, item_type, row)
    result = await bulk_hard_delete(db, model, body.ids, filter_deleted=True)
    await db.commit()
    return result


@router.post("/empty")
async def empty_recycle_bin(
    item_type: str | None = Query(None, description="清空指定类型，不传则清空全部"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """清空回收站（永久删除所有已软删除的记录，仅管理员；底稿不清除）

    对于项目类型，需要按 FK 依赖顺序级联删除子表数据。
    """
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="清空回收站会永久删除全部项目的已删除数据，仅管理员可操作")
    if item_type == WORKPAPER_TYPE:
        raise HTTPException(status_code=409, detail=WORKPAPER_PURGE_FORBIDDEN)

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

    # 1. 先删非 project 类型的软删除记录（这些通常没有复杂 FK）；底稿两层软删保留，不清除
    for tbl_key, (model, label, _) in tables.items():
        if tbl_key in ("project", WORKPAPER_TYPE):
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
        deleted_count += len(deleted_pids)

    await db.commit()
    return {"message": f"已永久删除 {deleted_count} 条记录（底稿不支持彻底删除，仍保留在回收站）",
            "deleted_count": deleted_count}


@router.get("/stats")
async def recycle_bin_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """回收站统计（各类型数量；只含当前用户是成员的项目，admin 全部）"""
    tables = _get_recyclable_tables()
    visible = await _visible_project_ids(db, user)
    stats = {}
    total = 0

    for tbl_key, (model, label, _) in tables.items():
        if not hasattr(model, "is_deleted"):
            continue
        scope = _visibility_filter(tbl_key, model, visible)
        if scope is False:
            continue
        count_q = select(func.count()).select_from(model).where(model.is_deleted == True)  # noqa: E712
        if scope is not None:
            count_q = count_q.where(scope)
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
