"""OwnershipGuard — 高级查询模块防 IDOR 准入守卫

Design: advanced-query-module design.md §Components 7「OwnershipGuard（防 IDOR，R9）」。

统一准入，任何注册 / 覆盖 / 回写路径不得绕过（P0 IDOR 缺口修复）。

机制（复用平台既有能力，不重造轮子）：
  - 复用 ``deps.require_project_access`` 的准入机制：project_users 成员校验
    + RLS session context（``set_rls_context``）+ Redis 权限缓存
    （``deps._get_cached_permission``）。
  - **补充** ``project_assignments`` 有效分派校验（列名 ``staff_id``，经
    ``staff_members.user_id`` 映射到当前用户）。用户「可访问项目集合」=
    project_users 成员 ∪ project_assignments 有效分派；admin / partner 视为
    可访问全部项目（与 ``deps.get_visible_project_ids`` 语义一致）。

铁律：
  - 校验在任何数据读写**之前**执行（R9.1 / R9.5）；不通过 → HTTP 403 且不触达
    数据层（R9.2）。
  - 跨 sheet 回写逐 cell 校验目标底稿 project_id 归属，任一不通过即抛 403，由调用方
    在同一事务内 raise → 整事务回滚，所有目标 cell 均不被修改（R9.3 / R9.4）。
  - 跨项目聚合仅返回可访问项目行，过滤其余（R9.6）。
  - 越权尝试记录审计（请求用户标识 + 目标 project_id + 操作类型，R9.7 / R4.7）。

_Requirements: 9.1, 9.2, 9.3, 9.4, 9.6, 9.7, 4.7_
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import set_rls_context
from app.deps import _get_cached_permission
from app.models.core import ProjectUser
from app.models.staff_models import ProjectAssignment, StaffMember
from app.services.audit_logger_enhanced import audit_logger

if TYPE_CHECKING:  # 避免对尚未落地的 addressing_service（task 2.1）产生硬运行时依赖
    from app.services.custom_query.addressing_service import ResolvedTarget

logger = logging.getLogger(__name__)

# 视为可访问全部项目的系统角色（与 deps.get_visible_project_ids 一致）
_ALL_ACCESS_ROLES = ("admin", "partner")


def _to_uuid(value: Any) -> UUID | None:
    """将 str / UUID / None 归一为 UUID，非法输入返回 None。"""
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


class OwnershipGuard:
    """项目归属准入守卫（防 IDOR）。

    作为 router 依赖注入到全部查询 / 回写端点的单点，任何路径不得绕过。
    """

    # ── 内部：计算可访问项目集合 ─────────────────────────────────────────

    async def _accessible_project_ids(
        self, user: Any, db: AsyncSession
    ) -> set[UUID] | None:
        """返回当前用户可访问的 project_id 集合。

        返回 ``None`` 作为哨兵表示「可访问全部项目」（admin / partner）。
        否则返回 project_users 成员 ∪ project_assignments 有效分派的并集。
        """
        if getattr(getattr(user, "role", None), "value", None) in _ALL_ACCESS_ROLES:
            return None

        user_id = getattr(user, "id", None)
        if user_id is None:
            return set()

        ids: set[UUID] = set()

        # (1) project_users 成员（复用 require_project_access 的数据源）
        pu_res = await db.execute(
            select(ProjectUser.project_id).where(
                ProjectUser.user_id == user_id,
                ProjectUser.is_deleted == False,  # noqa: E712
            )
        )
        for r in pu_res.all():
            pid = _to_uuid(r[0])
            if pid is not None:
                ids.add(pid)

        # (2) project_assignments 有效分派（列名 staff_id，经 staff_members.user_id 映射）
        pa_res = await db.execute(
            select(ProjectAssignment.project_id)
            .join(StaffMember, StaffMember.id == ProjectAssignment.staff_id)
            .where(
                StaffMember.user_id == user_id,
                ProjectAssignment.is_deleted == False,  # noqa: E712
                StaffMember.is_deleted == False,  # noqa: E712
            )
        )
        for r in pa_res.all():
            pid = _to_uuid(r[0])
            if pid is not None:
                ids.add(pid)

        return ids

    async def get_accessible_project_ids(
        self, user: Any, db: AsyncSession
    ) -> set[UUID] | None:
        """公开出口：返回当前用户可访问的 project_id 集合。

        供同包消费方（如 ``TemplateService`` 的模板可见性判定 R13.4）复用同一份
        「可访问项目集合」语义，避免各处重造。返回 ``None`` 作为哨兵表示
        「可访问全部项目」（admin / partner）。
        """
        return await self._accessible_project_ids(user, db)

    async def _can_access_project(
        self, user: Any, project_id: UUID, db: AsyncSession
    ) -> bool:
        """判断用户是否可访问指定项目（含 Redis 权限缓存快路径）。"""
        if getattr(getattr(user, "role", None), "value", None) in _ALL_ACCESS_ROLES:
            return True

        user_id = getattr(user, "id", None)
        if user_id is None:
            return False

        # 复用 require_project_access 的 Redis 权限缓存快路径（命中即代表有 project_users 权限）
        try:
            cached = await _get_cached_permission(user_id, project_id)
            if cached is not None:
                return True
        except Exception:  # Redis 不可用降级为直接查库
            pass

        accessible = await self._accessible_project_ids(user, db)
        return accessible is None or project_id in accessible

    # ── 审计：越权尝试 ──────────────────────────────────────────────────

    async def _audit_denied(
        self, user: Any, project_id: UUID | None, operation: str, db: AsyncSession
    ) -> None:
        """记录一条越权访问尝试审计（用户 / 目标 project_id / 操作类型，R9.7）。

        审计写入失败不得掩盖 403，故全程吞异常。
        """
        try:
            user_id = getattr(user, "id", None)
            await audit_logger.log_action(
                user_id=user_id,
                action="advanced_query.ownership_denied",
                object_type="project",
                object_id=str(project_id) if project_id else None,
                project_id=str(project_id) if project_id else None,
                details={
                    "operation": operation,
                    "reason": "project_not_accessible",
                    "user_id": str(user_id) if user_id else None,
                    "target_project_id": str(project_id) if project_id else None,
                },
            )
        except Exception as exc:  # 审计失败不阻断 403
            logger.warning("ownership_denied 审计写入失败（非致命）: %s", exc)

    @staticmethod
    def _forbidden(message: str, *, addr_id: str | None = None) -> HTTPException:
        detail: dict[str, Any] = {"error_code": "FORBIDDEN_PROJECT", "message": message}
        if addr_id is not None:
            detail["addr_id"] = addr_id
        return HTTPException(status_code=403, detail=detail)

    # ── 公开 API ────────────────────────────────────────────────────────

    async def assert_target_accessible(
        self, *, user: Any, project_id: Any, db: AsyncSession
    ) -> None:
        """校验目标项目可访问；不通过 → 403 且不触达数据层（R9.1 / R9.2）。

        通过时设置 RLS session context（复用 require_project_access 机制），
        使后续查询在正确的项目上下文内执行。
        """
        pid = _to_uuid(project_id)
        if pid is None:
            # 无法确定目标项目 → fail-closed 拒绝并记审计
            await self._audit_denied(user, None, "assert_target_accessible", db)
            raise self._forbidden("目标项目标识无效，拒绝访问")

        if await self._can_access_project(user, pid, db):
            await set_rls_context(db, pid)
            return

        await self._audit_denied(user, pid, "assert_target_accessible", db)
        raise self._forbidden("无权访问该项目数据")

    async def filter_accessible_rows(
        self, rows: list[Any], *, user: Any, db: AsyncSession
    ) -> list[Any]:
        """跨项目聚合仅保留可访问项目行，过滤其余（R9.6）。

        行的 project_id 从 dict 键 ``project_id`` 或对象属性 ``project_id`` 提取；
        无法确定项目归属的行 fail-closed 剔除。
        """
        accessible = await self._accessible_project_ids(user, db)
        if accessible is None:  # admin / partner 可见全部
            return list(rows)

        kept: list[Any] = []
        for row in rows:
            pid = _to_uuid(self._extract_row_project_id(row))
            if pid is not None and pid in accessible:
                kept.append(row)
        return kept

    async def assert_all_targets(
        self, targets: list["ResolvedTarget"], *, user: Any, db: AsyncSession
    ) -> None:
        """跨 sheet 回写逐目标校验 project_id 归属；任一不通过 → 403（R9.3 / R9.4）。

        调用方在写入前、同一事务内调用；抛出即整事务回滚，所有目标 cell 均不被修改。
        每个目标的 project_id 优先取显式属性，其次经 ``wp_id`` 反查 working_paper。
        无法确定归属的目标 fail-closed 拒绝。
        """
        if not targets:
            return

        accessible = await self._accessible_project_ids(user, db)
        if accessible is None:  # admin / partner 可访问全部
            return

        # (target, project_id) 解析：优先显式 project_id，其次 wp_id 反查
        resolved: list[tuple[Any, UUID | None]] = []
        wp_lookup: dict[str, list[Any]] = {}

        for t in targets:
            pid = _to_uuid(getattr(t, "project_id", None))
            wp_id = getattr(t, "wp_id", None)
            if pid is not None:
                resolved.append((t, pid))
            elif wp_id is not None:
                wp_lookup.setdefault(str(wp_id), []).append(t)
            else:
                resolved.append((t, None))

        # 批量反查 working_paper.project_id（asyncpg 用 = ANY + uuid[] 强转）
        if wp_lookup:
            res = await db.execute(
                text(
                    "SELECT id, project_id FROM working_paper "
                    "WHERE id = ANY(CAST(:ids AS uuid[]))"
                ),
                {"ids": list(wp_lookup.keys())},
            )
            pid_map = {str(r[0]): _to_uuid(r[1]) for r in res.all()}
            for wid, ts in wp_lookup.items():
                mapped = pid_map.get(wid)
                for t in ts:
                    resolved.append((t, mapped))

        for t, pid in resolved:
            if pid is None or pid not in accessible:
                await self._audit_denied(user, pid, "cross_sheet_writeback", db)
                raise self._forbidden(
                    "跨 sheet 回写目标含无权访问项目",
                    addr_id=getattr(t, "addr_id", None),
                )

    # ── 内部：行 project_id 提取 ─────────────────────────────────────────

    @staticmethod
    def _extract_row_project_id(row: Any) -> Any:
        if isinstance(row, dict):
            return row.get("project_id")
        return getattr(row, "project_id", None)


# 模块级单例
ownership_guard = OwnershipGuard()
