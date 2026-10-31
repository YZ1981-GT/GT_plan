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

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import ObjectDeletedError

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
#: 附件：永久删除前过归档 / 法定保全 / 引用守卫（spec attachment-security-baseline 需求 4.3）
ATTACHMENT_TYPE = "attachment"
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
            Adjustment, AccountChart, AccountMapping, TrialBalance,
        )
        from app.models.report_models import (
            FinancialReport, DisclosureNote, AuditReport,
        )
        from app.models.workpaper_models import (
            WpIndex, WpTemplate, ReviewRecord,
        )
        from app.models.attachment_models import Attachment
        from app.models.custom_query_models import CustomQueryTemplate

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
            # 高级查询模板（spec advanced-query-linkage-closure 任务 25）：按作者可见，见 _OWNER_SCOPED
            "custom_query_template": (CustomQueryTemplate, "查询模板", "name"),
        }
    return _RECYCLABLE_TABLES


#: 按作者可见的类型（类型键 → 作者列表达式）：作者与 admin 可见、可恢复、可彻底删除，不走项目成员判定。
#: 查询模板不属于任何项目，作者多为系统 auditor（v-permission 按系统角色会把按钮藏掉）⇒ 列表逐行下发 can_restore /
#: can_purge。作者口径与模型 ``owner_id``（creator_id 优先、否则 created_by）一致。
_OWNER_SCOPED: dict[str, Any] = {
    "custom_query_template": lambda model: func.coalesce(model.creator_id, model.created_by),
}


def _is_row_owner(row, user: User) -> bool:
    return getattr(row, "owner_id", None) == user.id


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


def _visibility_filter(tbl_key: str, model, visible: set[UUID] | None, user: User):
    """列表 / 统计的过滤条件；``False`` = 该类型对当前用户整体不可见。按作者可见的类型只给作者（admin 不限）。"""
    if visible is None:
        return None
    if tbl_key in _OWNER_SCOPED:
        return _OWNER_SCOPED[tbl_key](model) == user.id
    if tbl_key == "project":
        return model.id.in_(visible) if visible else False
    if not hasattr(model, "project_id"):
        return False  # 不属于任何项目（如底稿模板）只给 admin
    return model.project_id.in_(visible) if visible else False


def _row_project_id(item_type: str, row) -> UUID | None:
    return row.id if item_type == "project" else getattr(row, "project_id", None)


async def _authorize_row(db: AsyncSession, user: User, item_type: str, row) -> None:
    """恢复 / 彻底删除：admin 放行；按作者可见的类型只给作者；其余须是该行所属项目的编制（edit）成员；无项目归属的只给 admin。"""
    if _is_admin(user):
        return
    if item_type in _OWNER_SCOPED:
        if not _is_row_owner(row, user):
            raise HTTPException(status_code=403, detail="该记录只有作者本人或管理员可以操作")
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
    if tbl_key in _OWNER_SCOPED:  # 只有作者能删除（模板端点 admin 亦不例外）⇒ 删除人即作者
        owner = getattr(row, "owner_id", None)
        return str(owner) if owner is not None else None
    updated_by = getattr(row, "updated_by", None)
    if updated_by is not None:
        return str(updated_by)
    return None


def _display_name(tbl_key: str, row, name_field: str) -> str:
    if tbl_key == WORKPAPER_TYPE:
        return f"{row.wp_code} {row.wp_name}".strip()
    name_val = getattr(row, name_field, None) if hasattr(row, name_field) else str(row.id)
    return str(name_val) if name_val else str(row.id)[:8]


async def _lock_deleted_projects_for_purge(
    db: AsyncSession,
    rows: list[Project],
) -> list[Project]:
    """与恢复共用年度锁，并在锁后确认仍是同一批已删除项目。"""
    if not rows:
        return []
    from app.services.group_topology_lock import lock_topology_years
    from app.services.project_audit_year import resolve_project_audit_year

    baseline = {row.id: resolve_project_audit_year(row) for row in rows}
    await lock_topology_years(db, baseline.values())
    current = list((await db.execute(
        select(Project)
        .where(Project.id.in_(baseline))
        .execution_options(populate_existing=True)
    )).scalars().all())
    if (
        set(baseline) != {row.id for row in current}
        or any(not row.is_deleted for row in current)
        or any(resolve_project_audit_year(row) != baseline[row.id] for row in current)
    ):
        raise HTTPException(status_code=409, detail="项目回收站状态已变化，请刷新后重试")
    return current


async def _cascade_delete_project(db: AsyncSession, project_id: UUID) -> None:
    """级联删除单个项目及其所有关联数据（R12：不吞失败）。

    使用独立的 raw connection + session_replication_role=replica 禁用 FK 触发器（包括只追加表的禁改触发器），
    在同一事务里按 FK 关系逐表删除。任一步失败立即中断、事务回滚，不留孤儿行。
    """
    from app.core.database import async_engine

    pid = str(project_id)

    async with async_engine.connect() as conn:
        raw = await conn.get_raw_connection()
        pg_conn = raw.driver_connection

        still_deleted = await pg_conn.fetchval(
            "SELECT is_deleted FROM projects WHERE id = $1::uuid", pid
        )
        if still_deleted is not True:
            raise RuntimeError("项目已恢复或不存在，拒绝永久删除")

        await pg_conn.execute("SET session_replication_role = 'replica'")

        try:
            # 处理自引用（必须在删除项目行之前）
            await pg_conn.execute(
                "UPDATE projects SET parent_project_id = NULL WHERE parent_project_id = $1::uuid", pid
            )

            # 查出所有引用 projects.id 的子表并逐表删除——不再 except pass
            rows = await pg_conn.fetch("""
                SELECT DISTINCT tc.table_name, kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND ccu.table_name = 'projects'
                  AND tc.table_name != 'projects'
            """)
            for row in rows:
                table_name = row["table_name"]
                column_name = row["column_name"]
                try:
                    await pg_conn.execute(
                        f'DELETE FROM "{table_name}" WHERE "{column_name}" = $1::uuid', pid
                    )
                except Exception as exc:
                    raise HTTPException(
                        status_code=500,
                        detail=f"永久删除项目关联数据失败（表 {table_name}）：{type(exc).__name__}",
                    ) from exc

            result = await pg_conn.execute(
                "DELETE FROM projects WHERE id = $1::uuid AND is_deleted = true", pid
            )
            if result != "DELETE 1":
                raise RuntimeError("项目回收站状态已变化，永久删除已取消")
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
        scope = _visibility_filter(tbl_key, model, visible, user)
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
                item = {
                    "id": str(row.id),
                    "type": tbl_key,
                    "type_label": label,
                    "name": _display_name(tbl_key, row, name_field),
                    "deleted_at": deleted_at.isoformat() if deleted_at else None,
                    "deleted_by": _deleted_by(tbl_key, row),
                    "project_id": str(getattr(row, "project_id", "")) if hasattr(row, "project_id") else None,
                    "purgeable": tbl_key != WORKPAPER_TYPE,
                }
                if tbl_key in _OWNER_SCOPED:
                    # 逐行能力 = 与 _authorize_row 同一判定（界面据此显示按钮，不经按系统角色的 v-permission）；
                    # 其余类型不带这两个键，界面照旧按系统角色权限
                    item["can_restore"] = item["can_purge"] = _is_admin(user) or _is_row_owner(row, user)
                items.append(item)
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

    if item_type == "project":
        from app.services.group_topology_lock import lock_topology_years
        from app.services.project_audit_year import resolve_project_audit_year

        await lock_topology_years(db, [resolve_project_audit_year(row)])
        try:
            await db.refresh(row)
        except (InvalidRequestError, ObjectDeletedError) as exc:
            raise HTTPException(
                status_code=409, detail="项目已被永久删除，请刷新回收站"
            ) from exc
        if not row.is_deleted:
            raise HTTPException(status_code=409, detail="项目已被其他操作恢复，请刷新后重试")
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
    if item_type == "project":
        row = (await _lock_deleted_projects_for_purge(db, [row]))[0]
    if item_type == ATTACHMENT_TYPE:
        # 归档 423 / 法定保全 423 / 仍被引用 409，对管理员同样生效（spec attachment-security-baseline 需求 4.3）
        from app.services.attachment_destructive_guard import assert_destructible

        await assert_destructible(db, user, row, operation="purge")

    # 项目类型需要级联删除子表
    file_paths = [row.file_path] if item_type == ATTACHMENT_TYPE else []
    if item_type == "project":
        await _cascade_delete_project(db, item_id)
    else:
        await db.delete(row)

    await db.commit()
    cleanup = await _unlink_purged_files(db, file_paths)
    return {"message": f"{label}已永久删除" + _cleanup_message(cleanup), "id": str(item_id),
            **({"file_cleanup": cleanup} if file_paths else {})}


async def _unlink_purged_files(db: AsyncSession, file_paths: list[str | None]) -> dict[str, int]:
    """提交之后删无人引用的附件文件（spec attachment-archive-and-a-class-evidence 需求 9）。"""
    from app.services.attachment_file_purge import unlink_unreferenced_files

    return await unlink_unreferenced_files(db, file_paths) if file_paths else {}


def _cleanup_message(stats: dict[str, int]) -> str:
    from app.services.attachment_file_purge import cleanup_message

    return cleanup_message(stats)


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
    if item_type == ATTACHMENT_TYPE:
        return await _batch_purge_attachments(db, user, rows, body.ids)
    if item_type == "project":
        await _lock_deleted_projects_for_purge(db, list(rows))
    result = await bulk_hard_delete(db, model, body.ids, filter_deleted=True)
    await db.commit()
    return result


async def _batch_purge_attachments(db: AsyncSession, user: User, rows, ids: list[UUID]) -> dict:
    """批量永久删除附件：归档 / 保全 / 仍被引用的跳过，回执按原因计数（需求 4.3）。"""
    from app.services.attachment_destructive_guard import SKIP_REASONS, partition_purgeable, skipped_summary

    purgeable, skipped = await partition_purgeable(db, user, rows)
    skipped_ids = {row.id for skipped_rows in skipped.values() for row in skipped_rows}
    file_paths = [row.file_path for row in purgeable]
    model = _get_recyclable_tables()[ATTACHMENT_TYPE][0]
    result = await bulk_hard_delete(db, model, [i for i in ids if i not in skipped_ids], filter_deleted=True)
    for reason, skipped_rows in skipped.items():
        result["failed"].extend({"id": str(row.id), "error": SKIP_REASONS[reason]} for row in skipped_rows)
    result["fail_count"] = len(result["failed"])
    result["total"] = len(ids)
    result["skipped"] = skipped_summary(skipped)
    await db.commit()
    # 没删成的行仍引用自己的文件 ⇒ 引用检查会保留它（不必再按回执筛）
    result["file_cleanup"] = await _unlink_purged_files(db, file_paths)
    return result


async def _purge_deleted_attachments(db: AsyncSession, user: User) -> tuple[int, dict[str, int], list[str]]:
    """清空回收站里的附件：只删可删的，返回（删除数，按原因的跳过数，被删行的文件路径）（需求 4.3）。"""
    from app.models.attachment_models import Attachment
    from app.services.attachment_destructive_guard import partition_purgeable, skipped_summary

    rows = (await db.execute(select(Attachment).where(Attachment.is_deleted == True))).scalars().all()  # noqa: E712
    purgeable, skipped = await partition_purgeable(db, user, rows)
    if purgeable:
        await db.execute(delete(Attachment).where(Attachment.id.in_([row.id for row in purgeable])))
    return len(purgeable), skipped_summary(skipped), [row.file_path for row in purgeable]


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

    if item_type == ATTACHMENT_TYPE:
        count, skipped, file_paths = await _purge_deleted_attachments(db, user)
        await db.commit()
        cleanup = await _unlink_purged_files(db, file_paths)
        return {"message": f"已永久删除 {count} 条记录" + _skipped_message(skipped) + _cleanup_message(cleanup),
                "deleted_count": count, "skipped": skipped, "file_cleanup": cleanup}

    # 如果指定了非 project 类型，直接删
    if item_type and item_type != "project" and item_type in tables:
        model = tables[item_type][0]
        if hasattr(model, "is_deleted"):
            result = await db.execute(delete(model).where(model.is_deleted == True))  # noqa: E712
            await db.commit()
            return {"message": f"已永久删除 {result.rowcount} 条记录", "deleted_count": result.rowcount}
        return {"message": "该类型不支持软删除", "deleted_count": 0}

    # 获取并冻结待删除项目；与恢复共用年度锁，锁后状态变化则整次清空失败。
    deleted_projects = list((await db.execute(
        select(Project).where(Project.is_deleted == True)  # noqa: E712
    )).scalars().all())
    deleted_projects = await _lock_deleted_projects_for_purge(db, deleted_projects)
    deleted_pids = [row.id for row in deleted_projects]

    deleted_count = 0
    skipped: dict[str, int] = {}
    file_paths: list[str] = []

    # 1. 先删非 project 类型的软删除记录（这些通常没有复杂 FK）；底稿两层软删保留，不清除
    for tbl_key, (model, label, _) in tables.items():
        if tbl_key in ("project", WORKPAPER_TYPE):
            continue
        if not hasattr(model, "is_deleted"):
            continue
        if tbl_key == ATTACHMENT_TYPE:
            # 附件只删可删的（归档 / 保全 / 仍被引用的保留）；判定失败整体保留，不吞成「已删」
            count, skipped, file_paths = await _purge_deleted_attachments(db, user)
            deleted_count += count
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
    cleanup = await _unlink_purged_files(db, file_paths)
    return {"message": f"已永久删除 {deleted_count} 条记录（底稿不支持彻底删除，仍保留在回收站）"
                       + _skipped_message(skipped) + _cleanup_message(cleanup),
            "deleted_count": deleted_count, "skipped": skipped, "file_cleanup": cleanup}


def _skipped_message(skipped: dict[str, int]) -> str:
    from app.services.attachment_destructive_guard import SKIP_REASONS

    if not skipped:
        return ""
    return "；以下附件未删除：" + "、".join(f"{SKIP_REASONS[k]} {v} 个" for k, v in skipped.items())


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
        scope = _visibility_filter(tbl_key, model, visible, user)
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
