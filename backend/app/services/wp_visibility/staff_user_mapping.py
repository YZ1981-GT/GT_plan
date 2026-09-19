"""严格 staff↔user 映射服务（Task 3 / 组件 C3）

Feature: procedure-delegation-visibility-isolation
Requirements:
  - 2.4：Workpaper_Lead 委派成功时 ``WorkingPaper.assigned_to``（user_id）与
    ``ProcedureInstance.assigned_to``（staff_id）必须通过目标项目唯一 active staff↔user
    映射表达同一自然人。
  - 2.5：同人判定 **只** 使用映射关系。
  - 2.6：以字段值直接相等（user_id == staff_id）判同人的事务必须拒绝。
  - 3.1–3.6：写事务映射不变量（目标项目内唯一 active StaffMember、非空 user_id、
    唯一反向映射；跨项目、缺失、重复、inactive 均拒绝）。
Design: "DelegationMappingService" / Property 2 / Property 5（映射子集）

**与宽松 helper 的边界**：``procedure_authorization.normalize_staff_to_user`` 是全局宽松
归一（不校验项目成员、不校验反向唯一），只可用于读路径与取 user_id；**不得** 替代写事务
校验。本服务在其之上叠加目标项目成员链路与反向唯一性，构成写事务的严格入口。

纯读、无写副作用；service 约定只 flush 不 commit（本模块不写库）。asyncpg 用
``= ANY(:list)`` 而非 IN tuple；此处均为标量/聚合查询，无 IN 展开需求。
所有分支 try/except → fail-closed 拒绝，绝不 500 / 不泄露内部错误。
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.staff_models import ProjectAssignment, StaffMember
from app.services.procedure_authorization import normalize_staff_to_user

logger = logging.getLogger(__name__)


class MappingRejectReason(str, enum.Enum):
    """映射拒绝原因（内部诊断用；对外仍统一 fail-closed）。"""

    empty_staff = "empty_staff"          # staff_id 为空
    not_found = "not_found"              # staff 缺失 / inactive / 无 user_id（Req 3.2/3.3）
    cross_project = "cross_project"      # 仅能在目标项目之外解析到 active StaffMember（Req 3.6）
    ambiguous = "ambiguous"              # 反向映射非唯一（同 user 在项目内映射到多个 active staff，Req 3.4）
    query_error = "query_error"          # 查询异常 → fail-closed 拒绝


@dataclass(frozen=True)
class StaffMappingResolution:
    """staff↔user 严格映射解析结果（不可变）。

    - ``ok``：True 表示目标项目内唯一 active 双向映射成立，可用于写事务。
    - ``user_id``：ok 时为映射到的 ``users.id``；否则 None。
    - ``staff_id``：回显入参 staff_id。
    - ``reason``：ok=False 时的拒绝原因；ok=True 时为 None。
    """

    ok: bool
    user_id: UUID | None
    staff_id: UUID | None
    reason: MappingRejectReason | None = None


class StaffUserMappingService:
    """写事务专用的严格 staff↔user 映射校验器（fail-closed）。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def resolve_active_project_mapping(
        self, project_id: UUID, staff_id: UUID | None
    ) -> StaffMappingResolution:
        """解析目标项目内唯一 active staff↔user 映射（Req 3.1–3.6）。

        接受条件（全部满足才 ok）：
          1. staff_id 非空（Req 3.1 前置）。
          2. staff 为 active 且 ``user_id`` 非空（Req 3.2/3.3）——复用宽松 helper
             ``normalize_staff_to_user`` 取 user_id。
          3. staff 在目标项目内恰有一个 active ProjectAssignment（Req 3.1）；仅项目外可解析
             → ``cross_project`` 拒绝（Req 3.6）。
          4. 该 user_id 在目标项目内唯一映射到该 active StaffMember（反向唯一，Req 3.4）。

        任一不成立 → ``ok=False``（Req 3.5，由调用方回滚事务）。查询异常 → fail-closed。
        """
        if staff_id is None:
            return StaffMappingResolution(False, None, None, MappingRejectReason.empty_staff)

        try:
            # ② active + 非空 user_id（宽松 helper；staff 缺失/inactive/无 user_id → None）
            user_id = await normalize_staff_to_user(self.db, staff_id)
            if user_id is None:
                return StaffMappingResolution(
                    False, None, staff_id, MappingRejectReason.not_found
                )

            # ③ 目标项目内 active ProjectAssignment 数量（唯一索引保证 ≤1，仍防御性计数）
            in_project = (
                await self.db.execute(
                    sa.select(sa.func.count()).select_from(ProjectAssignment).where(
                        ProjectAssignment.project_id == project_id,
                        ProjectAssignment.staff_id == staff_id,
                        ProjectAssignment.is_deleted == False,  # noqa: E712
                    )
                )
            ).scalar_one()
            if in_project == 0:
                # staff 本身 active（②已过），但不属于目标项目 → 跨项目拒绝
                return StaffMappingResolution(
                    False, None, staff_id, MappingRejectReason.cross_project
                )
            if in_project > 1:
                return StaffMappingResolution(
                    False, None, staff_id, MappingRejectReason.ambiguous
                )

            # ④ 反向唯一：该 user_id 在目标项目内映射到的 active StaffMember 数量必须为 1
            reverse_count = (
                await self.db.execute(
                    sa.select(sa.func.count(sa.distinct(StaffMember.id)))
                    .select_from(StaffMember)
                    .join(ProjectAssignment, ProjectAssignment.staff_id == StaffMember.id)
                    .where(
                        StaffMember.user_id == user_id,
                        StaffMember.is_deleted == False,  # noqa: E712
                        ProjectAssignment.project_id == project_id,
                        ProjectAssignment.is_deleted == False,  # noqa: E712
                    )
                )
            ).scalar_one()
            if reverse_count != 1:
                # 同一 user 在目标项目内映射到 0 或多个 active staff → 非唯一
                return StaffMappingResolution(
                    False, None, staff_id, MappingRejectReason.ambiguous
                )

            return StaffMappingResolution(True, user_id, staff_id, None)
        except Exception as exc:  # noqa: BLE001 — fail-closed，不 500 泄露
            logger.warning(
                "staff↔user 映射查询异常 (project=%s staff=%s): %s",
                project_id,
                staff_id,
                exc,
            )
            return StaffMappingResolution(
                False, None, staff_id, MappingRejectReason.query_error
            )

    async def is_same_natural_person(
        self, project_id: UUID, user_id: UUID | None, staff_id: UUID | None
    ) -> bool:
        """判定 Workpaper_Lead user_id 与 Staff_Projection staff_id 是否同一自然人（Req 2.4–2.6）。

        **只** 依据目标项目唯一 active staff↔user 映射判定（Req 2.5）；**绝不** 用
        ``user_id == staff_id`` 字段值直接相等推断（Req 2.6）——本方法根本不比较两个 UUID 的值，
        而是解析 staff 的映射 user 再与传入 user_id 比较。

        映射不成立（缺失/跨项目/重复/inactive/查询异常）一律返回 False（fail-closed）。
        """
        if user_id is None or staff_id is None:
            return False
        resolution = await self.resolve_active_project_mapping(project_id, staff_id)
        return resolution.ok and resolution.user_id == user_id
