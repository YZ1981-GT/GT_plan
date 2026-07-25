"""底稿批量操作 + 看板 API 路由（从 working_paper.py 拆出，零行为变更）

批量+看板域端点（与 working_paper 主 router 共用 `/api/projects/{project_id}` 前缀）：
- GET    /working-papers-kanban                  — 底稿看板视图（按状态分组）
- POST   /working-papers/batch-assign            — 批量分配编制人/复核人
- POST   /working-papers/batch-submit            — 批量提交复核
- POST   /working-papers/batch-export            — 批量导出 ZIP
- GET    /working-papers/{wp_id}/edit-time        — 编制时间统计

请求模型 `BatchAssignRequest` / `BatchSubmitRequest` 仅由本模块端点使用，随端点同模块迁移。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
from app.models.workpaper_models import WpIndex, WorkingPaper, WpFileStatus

router = APIRouter(
    prefix="/api/projects/{project_id}",
    tags=["working-papers"],
)


# ═══ 底稿看板视图 + 批量操作 + 编制时间 ═══

class BatchAssignRequest(BaseModel):
    wp_ids: list[str]
    assigned_to: UUID | None = None
    reviewer: UUID | None = None


class BatchSubmitRequest(BaseModel):
    wp_ids: list[str]


def _kanban_column_for(status: str) -> str:
    """底稿状态 → 看板列 key（单一映射，供分组与按人聚合共用）。"""
    if status in ("not_started",):
        return "not_started"
    if status in ("under_review", "review_level1", "review_level2"):
        return "under_review"
    if status in ("review_passed", "archived"):
        return "completed"
    # draft / edit_complete / 其余未知状态 → 编制中
    return "in_progress"


async def _resolve_user_names(db: AsyncSession, user_ids: set[str]) -> dict[str, str]:
    """批量解析 user_id → 显示名（StaffMember.staff_name 优先，回退 User.username）。

    fail-open：任一查询异常返回已解析部分，不阻断看板。
    """
    from app.models.staff_models import StaffMember

    def _as_uuid(v):
        try:
            return UUID(str(v))
        except Exception:
            return None

    ids = [g for g in (_as_uuid(u) for u in user_ids) if g]
    name_map: dict[str, str] = {}
    if not ids:
        return name_map
    # StaffMember.name 优先（人员库显示名）；两条查询各自 fail-open，互不影响
    try:
        sr = await db.execute(
            sa.select(StaffMember.user_id, StaffMember.name).where(
                StaffMember.user_id.in_(ids),
                StaffMember.is_deleted == sa.false(),
            )
        )
        for uid, sname in sr.all():
            if uid and sname:
                name_map[str(uid)] = sname
    except Exception:  # noqa: BLE001 — 人员库解析失败不影响看板主体
        pass
    try:
        ur = await db.execute(sa.select(User.id, User.username).where(User.id.in_(ids)))
        for uid, uname in ur.all():
            if uname:
                name_map.setdefault(str(uid), uname)
    except Exception:  # noqa: BLE001
        pass
    return name_map


@router.get("/working-papers-kanban")
async def get_workpapers_kanban(
    project_id: UUID,
    audit_cycle: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """底稿看板视图 — 按状态分组 + 按人聚合（服务端强制可见性隔离）。

    - 可见性：复用 ``VisibilityRoleClassifier`` + ``VisibilityQueryService`` 的可见集
      （admin/partner/manager 看全部；restricted 角色只看被委派/主编/复核的底稿），
      与列表端点口径一致，避免看板越权可见（procedure-delegation-visibility-isolation）。
    - 按状态：4 列 待编制 / 编制中 / 待复核 / 已通过，卡片含编制人/复核人姓名。
    - 按人：``by_assignee`` 每位编制人各列数量 + 完成率 + 逾期占位，供负责人查看每人完成情况。
    """
    from app.services.wp_visibility import VisibilityRoleClassifier
    from app.services.wp_visibility.visibility_query import VisibilityQueryService

    # ① 服务端角色分类 → 可见 wp_index 集合（与列表端点同源）
    context = await VisibilityRoleClassifier(db).classify(current_user, project_id)
    visible_ids = await VisibilityQueryService(db).visible_wp_index_ids(context)

    kanban: dict[str, list] = {
        "not_started": [],   # 待编制
        "in_progress": [],   # 编制中
        "under_review": [],  # 待复核
        "completed": [],     # 已通过
    }

    if not visible_ids:
        stats = {k: 0 for k in kanban}
        stats["total"] = 0
        stats["completion_rate"] = 0.0
        return {"kanban": kanban, "stats": stats, "by_assignee": []}

    query = sa.select(WpIndex, WorkingPaper).outerjoin(
        WorkingPaper, sa.and_(
            WorkingPaper.wp_index_id == WpIndex.id,
            WorkingPaper.is_deleted == sa.false(),
        )
    ).where(
        WpIndex.project_id == project_id,
        WpIndex.is_deleted == sa.false(),
        WpIndex.id.in_(list(visible_ids)),
    )
    if audit_cycle:
        query = query.where(WpIndex.audit_cycle == audit_cycle)
    query = query.order_by(WpIndex.wp_code)

    result = await db.execute(query)
    rows = result.all()

    # 先收集所有 user_id 供批量人名解析（编制人 + 复核人）
    user_ids: set[str] = set()
    for _idx_row, wp in rows:
        if wp and wp.assigned_to:
            user_ids.add(str(wp.assigned_to))
        if wp and getattr(wp, "reviewer", None):
            user_ids.add(str(wp.reviewer))
    name_map = await _resolve_user_names(db, user_ids)

    # 按人聚合累加器：key=assignee user_id 或 None（未分配）
    _EMPTY = lambda: {"not_started": 0, "in_progress": 0, "under_review": 0, "completed": 0}
    by_assignee: dict[str | None, dict] = {}

    for idx_row, wp in rows:
        status = wp.status.value if wp and wp.status else "not_started"
        col = _kanban_column_for(status)
        assignee = str(wp.assigned_to) if wp and wp.assigned_to else None
        reviewer = str(wp.reviewer) if wp and getattr(wp, "reviewer", None) else None
        item = {
            "wp_id": str(wp.id) if wp else None,
            "wp_code": idx_row.wp_code,
            "wp_name": idx_row.wp_name,
            "audit_cycle": idx_row.audit_cycle,
            "status": status,
            "assigned_to": assignee,
            "assigned_to_name": name_map.get(assignee) if assignee else None,
            "reviewer": reviewer,
            "reviewer_name": name_map.get(reviewer) if reviewer else None,
        }
        kanban[col].append(item)

        bucket = by_assignee.setdefault(assignee, _EMPTY())
        bucket[col] += 1

    # 统计（按状态）
    stats = {k: len(v) for k, v in kanban.items()}
    stats["total"] = sum(stats.values())
    stats["completion_rate"] = round(stats["completed"] / max(stats["total"], 1) * 100, 1)

    # 按人视图：每人各列数量 + 完成率（负责人查看每人完成情况）
    assignee_rows = []
    for uid, cnt in by_assignee.items():
        total = cnt["not_started"] + cnt["in_progress"] + cnt["under_review"] + cnt["completed"]
        assignee_rows.append({
            "user_id": uid,
            "name": (name_map.get(uid) if uid else None) or ("未分配" if uid is None else uid[:8]),
            "not_started": cnt["not_started"],
            "in_progress": cnt["in_progress"],
            "under_review": cnt["under_review"],
            "completed": cnt["completed"],
            "total": total,
            "completion_rate": round(cnt["completed"] / max(total, 1) * 100, 1),
        })
    # 已分配的人排前面（按完成率降序），未分配殿后
    assignee_rows.sort(key=lambda r: (r["user_id"] is None, -r["completion_rate"], -r["total"]))

    return {"kanban": kanban, "stats": stats, "by_assignee": assignee_rows}


@router.post("/working-papers/batch-assign")
async def batch_assign(
    project_id: UUID,
    data: BatchAssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("review")),
):
    """批量分配底稿（编制人/复核人）"""
    updated = 0
    for wp_id_str in data.wp_ids:
        wp_id = UUID(wp_id_str)
        result = await db.execute(
            sa.select(WorkingPaper).where(WorkingPaper.id == wp_id, WorkingPaper.is_deleted == sa.false())
        )
        wp = result.scalar_one_or_none()
        if not wp:
            continue
        if data.assigned_to is not None:
            wp.assigned_to = data.assigned_to
        if data.reviewer is not None:
            wp.reviewer = data.reviewer
        updated += 1

    await db.flush()
    await db.commit()
    return {"updated": updated, "message": f"已批量分配 {updated} 个底稿"}


@router.post("/working-papers/batch-submit")
async def batch_submit_review(
    project_id: UUID,
    data: BatchSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """批量提交复核（跳过不满足条件的底稿）"""
    submitted = 0
    skipped = []

    for wp_id_str in data.wp_ids:
        wp_id = UUID(wp_id_str)
        result = await db.execute(
            sa.select(WorkingPaper).where(WorkingPaper.id == wp_id, WorkingPaper.is_deleted == sa.false())
        )
        wp = result.scalar_one_or_none()
        if not wp:
            skipped.append({"wp_id": wp_id_str, "reason": "不存在"})
            continue
        if wp.status != WpFileStatus.edit_complete:
            skipped.append({"wp_id": wp_id_str, "reason": f"状态为{wp.status.value}，需先完成编制"})
            continue

        # 简化门禁：检查复核人是否已分配
        if not wp.reviewer:
            skipped.append({"wp_id": wp_id_str, "reason": "未分配复核人"})
            continue

        wp.status = WpFileStatus.under_review
        submitted += 1

    await db.flush()
    await db.commit()
    return {"submitted": submitted, "skipped": skipped, "message": f"已提交 {submitted} 个，跳过 {len(skipped)} 个"}


@router.post("/working-papers/batch-export")
async def batch_export_zip(
    project_id: UUID,
    data: BatchSubmitRequest,  # 复用 wp_ids 字段
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """批量导出底稿为 ZIP"""
    import io
    import zipfile
    from pathlib import Path

    from app.services.wp_visibility.entry_integration import make_bulk_visible_filter

    # Wp_Bound_Gate（Task 4 / R3）：打包底稿正文前用可见集过滤 wp_ids；
    # 不可见/跨项目/未委派/scope 外底稿静默剔除，manifest 只由可见集构建。
    _visible = make_bulk_visible_filter(
        db, current_user, entrypoint="workpaper.detail", action="read_detail",
        method="GET", entry_family="export",
    )
    visible_wp_ids = [wid for wid in data.wp_ids if await _visible(wid, None)]

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for wp_id_str in visible_wp_ids:
            wp_id = UUID(wp_id_str)
            result = await db.execute(
                sa.select(WorkingPaper, WpIndex)
                .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
                .where(WorkingPaper.id == wp_id, WorkingPaper.is_deleted == sa.false())
            )
            row = result.first()
            if not row:
                continue
            wp, idx = row
            if wp.file_path:
                fp = Path(wp.file_path)
                if fp.exists():
                    arcname = f"{idx.audit_cycle or 'OTHER'}/{idx.wp_code}.xlsx"
                    zf.write(fp, arcname)

    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=workpapers_{project_id}.zip"},
    )


@router.get("/working-papers/{wp_id}/edit-time")
async def get_edit_time(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """获取底稿编制时间统计

    从审计日志中提取编辑时间段（首次编辑→提交复核）。
    """
    from app.models.core import Log

    # 查找该底稿的编辑相关日志
    result = await db.execute(
        sa.select(Log.created_at, Log.action).where(
            sa.or_(
                sa.and_(Log.action == "workpaper_online_open", Log.new_value.contains(str(wp_id))),
                sa.and_(Log.action == "workpaper_online_save", Log.new_value.contains(str(wp_id))),
            )
        ).order_by(Log.created_at)
    )
    logs = result.all()

    if not logs:
        return {"wp_id": str(wp_id), "total_minutes": 0, "sessions": 0, "message": "无编辑记录"}

    # 计算编辑时间（相邻 open-save 配对）
    total_minutes = 0
    sessions = 0
    first_edit = logs[0][0] if logs else None
    last_edit = logs[-1][0] if logs else None

    # 简化计算：总时长 = 最后一次操作 - 第一次操作
    if first_edit and last_edit and first_edit != last_edit:
        diff = (last_edit - first_edit).total_seconds() / 60
        total_minutes = round(diff, 1)
        sessions = len([l for l in logs if l[1] == "workpaper_online_open"])

    return {
        "wp_id": str(wp_id),
        "total_minutes": total_minutes,
        "sessions": sessions,
        "first_edit": first_edit.isoformat() if first_edit else None,
        "last_edit": last_edit.isoformat() if last_edit else None,
    }
