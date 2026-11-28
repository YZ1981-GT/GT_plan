"""操作日志查询 API（V274，spec operation-log-and-last-login）

GET /api/system/operation-logs —— 仅 admin。
合并两个数据源：
  - sys_login_log（登录成功/失败/锁定/登出；type 取 result 原值）
  - logs（写操作审计；type 取 action_type：create/update/delete 等）
统一投影：时间 / 类型 / 详情 / 人名 / 账号 / 部门 / IP。
筛选与分页全部下推数据库（日志表会持续增长，不整表拉内存）。
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_role
from app.models.core import Department, Log, SysLoginLog, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["operation-logs"])

#: type 筛选白名单（前端下拉与后端同源；login 系按 result 过滤，业务类按 action_type 过滤）
LOGIN_RESULT_TYPES = ("success", "failed", "locked", "logout")
BUSINESS_ACTION_TYPES = ("create", "update", "delete")
VALID_TYPES = frozenset(LOGIN_RESULT_TYPES + BUSINESS_ACTION_TYPES)

#: keyword 覆盖的列（账号 / 人名）
_MAX_PAGE_SIZE = 200


def _type_filter(type_value: str):
    """把 type 筛选转成两源各自的条件（返回 login_cond, biz_cond）。"""
    if type_value in LOGIN_RESULT_TYPES:
        return SysLoginLog.result == type_value, sa.false()
    # 业务类动作
    if type_value in BUSINESS_ACTION_TYPES:
        return sa.false(), Log.action_type == type_value
    raise HTTPException(status_code=422, detail=f"不支持的操作类型：{type_value}")


def _like_both(keyword: str, *columns):
    """两库通用的模糊匹配（SQLite 无 ILIKE；两端 lower 后 LIKE）。"""
    pat = f"%{keyword.lower()}%"
    return sa.or_(*[sa.func.lower(c).like(pat) for c in columns])


@router.get("/operation-logs")
async def list_operation_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=_MAX_PAGE_SIZE),
    type: str | None = Query(None, description="操作类型：success/failed/locked/logout/create/update/delete"),
    keyword: str | None = Query(None, max_length=100, description="按账号或人名模糊匹配"),
    dept_id: UUID | None = Query(None, description="按部门筛选"),
    from_time: datetime | None = Query(None, alias="from"),
    to_time: datetime | None = Query(None, alias="to"),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(["admin"])),
):
    """合并查询登录留痕与写操作日志（仅 admin）。"""
    # ---- 时间条件（两源同构）----
    login_conds = []
    biz_conds = []
    if from_time is not None:
        login_conds.append(SysLoginLog.ts >= from_time)
        biz_conds.append(Log.created_at >= from_time)
    if to_time is not None:
        login_conds.append(SysLoginLog.ts < to_time)
        biz_conds.append(Log.created_at < to_time)

    # ---- type 条件 ----
    if type is not None:
        lc, bc = _type_filter(type)
        login_conds.append(lc)
        biz_conds.append(bc)

    # ---- 部门条件：login_log 可空 user；logs 的 user_id 理论上都有，但同样允许 NULL ----
    dept_join_user = (
        sa.outerjoin(User, Department, User.dept_id == Department.id)
    )
    dept_cond_user = (
        Department.id == dept_id if dept_id is not None else sa.true()
    )
    login_conds.append(dept_cond_user)
    biz_conds.append(dept_cond_user)

    # ---- keyword：账号 / 人名 ----
    if keyword is not None and keyword.strip():
        kw = keyword.strip()
        kw_cond = _like_both(kw, User.username, User.full_name, SysLoginLog.username)
        login_conds.append(kw_cond)
        biz_conds.append(sa.or_(kw_cond, sa.and_(User.username.is_(None), SysLoginLog.username.is_(None), sa.false())))

    # ---- 两源统一投影的子查询 ----
    login_sel = (
        sa.select(
            SysLoginLog.id.label("id"),
            SysLoginLog.ts.label("ts"),
            SysLoginLog.result.label("type"),
            sa.literal(None).label("detail"),
            SysLoginLog.user_id.label("user_id"),
            sa.func.coalesce(User.full_name, sa.literal(None)).label("full_name"),
            sa.func.coalesce(User.username, SysLoginLog.username).label("username"),
            Department.name.label("dept_name"),
            SysLoginLog.ip.label("ip"),
        )
        .select_from(SysLoginLog)
        .outerjoin(User, SysLoginLog.user_id == User.id)
        .outerjoin(Department, User.dept_id == Department.id)
        .where(sa.and_(*login_conds))
    )

    biz_sel = (
        sa.select(
            Log.id.label("id"),
            Log.created_at.label("ts"),
            Log.action_type.label("type"),
            # detail：对象类型（+短对象 id），人可读
            sa.func.concat(
                Log.object_type,
                sa.case((Log.object_id.isnot(None), sa.literal("")), else_=sa.literal("")),
            ).label("detail"),
            Log.user_id.label("user_id"),
            User.full_name.label("full_name"),
            User.username.label("username"),
            Department.name.label("dept_name"),
            Log.ip_address.label("ip"),
        )
        .select_from(Log)
        .outerjoin(User, Log.user_id == User.id)
        .outerjoin(Department, User.dept_id == Department.id)
        .where(sa.and_(*biz_conds))
    )

    union = sa.union_all(login_sel, biz_sel).subquery()
    ts_col = union.c.ts

    count_stmt = sa.select(sa.func.count()).select_from(union)
    total = (await db.execute(count_stmt)).scalar_one()

    rows = (await db.execute(
        sa.select(union)
        .order_by(ts_col.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).all()

    return {
        "items": [
            {
                "id": str(r.id),
                "ts": r.ts.isoformat() if r.ts else None,
                "type": r.type,
                "detail": r.detail,
                "user_id": str(r.user_id) if r.user_id else None,
                "full_name": r.full_name,
                "username": r.username,
                "dept_name": r.dept_name,
                "ip": r.ip,
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
