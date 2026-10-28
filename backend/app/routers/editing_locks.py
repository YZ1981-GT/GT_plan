"""通用编辑锁端点 — global-refinement-v5-closure 能力域 C

POST   /api/editing-locks/{resource_type}/{resource_id}            — acquire
PATCH  /api/editing-locks/{resource_type}/{resource_id}/heartbeat  — 续期
DELETE /api/editing-locks/{resource_type}/{resource_id}            — release
POST   /api/editing-locks/{resource_type}/{resource_id}/force      — force-acquire
GET    /api/editing-locks/active                                   — 活跃锁列表（仅 admin）

鉴权（spec procedure-chain-hardening-and-java-contracts R2）：取锁 / 续期 / 强制接管先判资源，再动锁行。
原先五个端点只要求登录 ⇒ 打不开某底稿（404）的审计员照样能占锁续期，负责人打开时被锁成只读。
  - ``workpaper``：与保存同一受众（底稿门 ``workpaper.editing_lock``，看不见 / 无编辑权 ⇒ 404，与打开底稿一致），
    再按项目 edit 级判（归档 423）；强制接管另过 ``workpaper.editing_lock_force``（只登记给全权身份），能看见但不是全权 ⇒ 403。
  - ``disclosure_note`` / ``audit_report``：资源 id 为 ``{项目 uuid}_note`` / ``{项目 uuid}_report``，附注走附注编辑门禁、
    报告按项目 edit 级；强制接管要求项目委派人（合伙人 / 经理）或 admin。
  - 其他类型 404。释放只认锁持有者（service 已按 holder 过滤，被撤权的人也要能放掉自己的锁）。
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import assert_project_permission, get_current_user
from app.models.core import User
from app.services.editing_lock_service import (
    acquire_lock,
    force_acquire_lock,
    get_active_locks,
    heartbeat_lock,
    release_lock,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/editing-locks",
    tags=["editing-locks"],
)

#: 与底稿门拒绝同一句（不泄露资源是否存在）
LOCK_NOT_FOUND_DETAIL = "资源不存在或不可访问"
LOCK_FORCE_DENIED_DETAIL = "只有底稿负责人、主管或管理员可以强制接管编辑锁"
_LOCK_ROUTE = "/api/editing-locks/{resource_type}/{resource_id}"
#: 项目级资源：资源 id = 项目 uuid + 后缀（前端 DisclosureEditor / AuditReportEditor 的写法）
_PROJECT_SCOPED_SUFFIX = {"disclosure_note": "_note", "audit_report": "_report"}


def _holder_name(user: User) -> str:
    """从 User 取 holder_name：full_name > username > 空串"""
    return getattr(user, "full_name", None) or user.username or ""


async def _authorize_lock(
    db: AsyncSession, user: User, resource_type: str, resource_id: str, *, mode: str,
) -> UUID:
    """取锁（acquire）/ 续期（renew）/ 强制接管（force）前的资源判定；放行返回资源所属项目，拒绝抛 HTTPException。"""
    if resource_type == "workpaper":
        try:
            wp_id = UUID(str(resource_id))
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(status_code=404, detail=LOCK_NOT_FOUND_DETAIL)
        from app.routers._wp_gate import enforce_wp_gate

        renew = mode == "renew"
        ctx = await enforce_wp_gate(
            db, user,
            entrypoint="workpaper.editing_lock",
            action="renew_edit_lock" if renew else "acquire_edit_lock",
            method="PATCH" if renew else "POST",
            wp_id=wp_id, route_name=_LOCK_ROUTE, entry_family="editing_lock",
        )
        if mode == "force":
            try:
                await enforce_wp_gate(
                    db, user,
                    entrypoint="workpaper.editing_lock_force", action="force_edit_lock", method="POST",
                    wp_id=wp_id, route_name=f"{_LOCK_ROUTE}/force", entry_family="editing_lock",
                )
            except HTTPException as exc:
                if exc.status_code == 404:  # 能看见这张底稿（上一道门已过）但不是全权身份
                    raise HTTPException(status_code=403, detail=LOCK_FORCE_DENIED_DETAIL) from exc
                raise
        await assert_project_permission(db, user, ctx.project_id, "edit")
        return ctx.project_id

    suffix = _PROJECT_SCOPED_SUFFIX.get(resource_type)
    if suffix and str(resource_id).endswith(suffix):
        try:
            project_id = UUID(str(resource_id)[: -len(suffix)])
        except ValueError:
            raise HTTPException(status_code=404, detail=LOCK_NOT_FOUND_DETAIL)
        if resource_type == "disclosure_note":
            from app.services.note_edit_gate import assert_note_edit_access

            await assert_note_edit_access(db, user, project_id, consol_lock=False)
        else:
            await assert_project_permission(db, user, project_id, "edit")
        if mode == "force":
            from app.services.procedure_authorization import ensure_project_delegator

            try:
                await ensure_project_delegator(db, user, project_id)
            except HTTPException as exc:
                raise HTTPException(status_code=403, detail=LOCK_FORCE_DENIED_DETAIL) from exc
        return project_id

    raise HTTPException(status_code=404, detail=LOCK_NOT_FOUND_DETAIL)


@router.get("/active")
async def list_active_locks(
    resource_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取活跃锁列表（可选 ?resource_type= 过滤）。跨项目可见 ⇒ 只给 admin（前端无调用方）。"""
    if current_user.role.value != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可以查看全部活跃编辑锁")
    locks = await get_active_locks(db, resource_type=resource_type)
    await db.commit()
    return {"locks": locks}


@router.post("/{resource_type}/{resource_id}")
async def acquire(
    resource_type: str,
    resource_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    x_client_instance: Optional[str] = Header(None, alias="X-Client-Instance"),
):
    """获取编辑锁（先判资源：看不见 / 无编辑权不建锁行、不清理他人过期锁）"""
    await _authorize_lock(db, current_user, resource_type, resource_id, mode="acquire")
    result = await acquire_lock(
        db,
        resource_type=resource_type,
        resource_id=resource_id,
        holder_id=current_user.id,
        holder_name=_holder_name(current_user),
        client_instance=x_client_instance,
    )
    await db.commit()

    if result.get("locked"):
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "LOCK_HELD",
                "locked_by": result["locked_by"],
                "locked_by_name": result["locked_by_name"],
                "acquired_at": result["acquired_at"],
            },
        )
    return result


@router.patch("/{resource_type}/{resource_id}/heartbeat")
async def heartbeat(
    resource_type: str,
    resource_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    x_client_instance: Optional[str] = Header(None, alias="X-Client-Instance"),
):
    """续期 heartbeat。撤权后续期被拒 ⇒ 先放掉本人在该资源上的锁再拒绝（别人不用等锁过期）。"""
    try:
        await _authorize_lock(db, current_user, resource_type, resource_id, mode="renew")
    except HTTPException:
        await release_lock(
            db, resource_type=resource_type, resource_id=resource_id,
            holder_id=current_user.id, client_instance=x_client_instance,
        )
        await db.commit()
        raise
    result = await heartbeat_lock(
        db,
        resource_type=resource_type,
        resource_id=resource_id,
        holder_id=current_user.id,
        client_instance=x_client_instance,
    )
    await db.commit()

    if not result.get("refreshed"):
        raise HTTPException(status_code=404, detail="无活跃锁")
    return result


@router.delete("/{resource_type}/{resource_id}")
async def release(
    resource_type: str,
    resource_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    x_client_instance: Optional[str] = Header(None, alias="X-Client-Instance"),
):
    """释放编辑锁（只认锁持有者：service 按 holder_id 过滤）"""
    result = await release_lock(
        db,
        resource_type=resource_type,
        resource_id=resource_id,
        holder_id=current_user.id,
        client_instance=x_client_instance,
    )
    await db.commit()

    if not result.get("released"):
        raise HTTPException(status_code=404, detail="无活跃锁")
    return result


@router.post("/{resource_type}/{resource_id}/force")
async def force_acquire(
    resource_type: str,
    resource_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    x_client_instance: Optional[str] = Header(None, alias="X-Client-Instance"),
):
    """强制获取锁（释放原锁 + 创建新锁）。只给全权身份；新锁记录窗口标识（原先不记 ⇒ 本人所有窗口都能续期）。"""
    project_id = await _authorize_lock(db, current_user, resource_type, resource_id, mode="force")
    result = await force_acquire_lock(
        db,
        resource_type=resource_type,
        resource_id=resource_id,
        holder_id=current_user.id,
        holder_name=_holder_name(current_user),
        client_instance=x_client_instance,
    )
    await db.commit()

    # Best-effort SSE notification for force-acquired event
    try:
        from app.services.event_bus import event_bus

        payload = {
            "project_id": str(project_id) if project_id else None,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "new_holder_id": str(current_user.id),
            "new_holder_name": _holder_name(current_user),
            "previous_holder_id": result.get("previous_holder_id"),
        }
        # Frontend useEditingLock matches force events by wp_id for workpapers
        if resource_type == "workpaper":
            payload["wp_id"] = resource_id

        event_bus.broadcast_raw("editing_lock.force_acquired", payload)
    except Exception as exc:
        logger.warning(
            "Failed to broadcast editing_lock.force_acquired for %s/%s: %s",
            resource_type,
            resource_id,
            exc,
        )

    return result


async def _resolve_project_id(
    db: AsyncSession, resource_type: str, resource_id: str
) -> UUID | None:
    """Best-effort resolve project_id from the resource for SSE routing.

    Returns None if resolution fails (non-blocking). 强制接管已改用鉴权返回的项目；本函数保留给既有调用方。
    """
    try:
        if resource_type == "workpaper":
            from sqlalchemy import select

            from app.models.workpaper_models import WorkingPaper

            # resource_id 来自 URL path（str），WorkingPaper.id 是 UUID 列
            # 需显式转 UUID 以兼容 SQLite 测试环境（PG 隐式转换但显式更健壮）
            wp_uuid = UUID(resource_id)
            stmt = select(WorkingPaper.project_id).where(
                WorkingPaper.id == wp_uuid
            )
            row = (await db.execute(stmt)).scalar_one_or_none()
            return row
    except Exception as exc:
        logger.warning(
            "_resolve_project_id failed for %s/%s: %s",
            resource_type,
            resource_id,
            exc,
        )
    return None
