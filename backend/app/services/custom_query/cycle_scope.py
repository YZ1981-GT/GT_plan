"""高级查询的循环级可见性（advanced-query-linkage-closure ADR-AQL-19、design §3.10；R3.8、R3.1 / R3.5 / R3.6 的循环范围部分）。

**存在理由（AQ-19 循环范围部分）**：试算表页、调整分录页、附注页对受限成员按审计循环过滤（团队分配只勾 D 循环的审计员
只见 D 循环科目），高级查询原先不看循环范围 —— 同一个人在高级查询里能查到全部科目、全部分录、全部附注章节，接上完整
导出后范围更大。本模块让高级查询与这三个页面同口径：

- 口径只来自平台唯一入口 ``deps.get_user_scope_cycles``（= ``wp_visibility.effective_scope.resolve_member_scope``）：
  ``None`` = 不限（系统 admin / partner、本项目链路唯一的主管），列表 = 受限成员的有效范围（可为空，空即什么都看不到）。
  本模块不复制它的规则、不另读 ``project_users.scope_cycles`` / ``project_assignments.assigned_cycles``。
- 科目 / 章节集合与原页面同一函数：``mapping_service.get_codes_by_cycles`` / ``get_sections_by_cycles``；任一调用异常按空集
  （与调整分录页「取不到不放行」同）。
- :meth:`CycleScopeCache.cycles` 是本模块**唯一**调用平台入口的地方，在保存点里调用、成败都回滚到保存点：平台函数吞掉
  查询异常、返回受限空集但不回滚，PG 上本请求事务会停在 aborted，后续取数随之 ``InFailedSQLTransactionError`` ⇒ 500。
  回滚到保存点在 aborted 状态下照样可执行，外层事务随之恢复；平台函数纯读，回滚不丢任何东西。不用
  ``async with db.begin_nested()``：保存点正常退出要先 ``RELEASE SAVEPOINT``，事务已 aborted 时这一步失败，SQLAlchemy 随后
  把该保存点置为非活动、不再发 ``ROLLBACK TO SAVEPOINT``，外层事务仍是 aborted（design §3.10）。
- 同一请求内按项目记忆化（业务视图的 ``FetchContext`` 与构建器的作用域解析各持一个实例），不写批量版判定。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import deps
from app.services import mapping_service
from app.services.custom_query.builder_access import ALL_PROJECT_ROLES, role_value

logger = logging.getLogger(__name__)

#: 附注章节不在本人循环范围（R3.8）
SECTION_OUT_OF_SCOPE = "SECTION_OUT_OF_SCOPE"
SECTION_OUT_OF_SCOPE_MESSAGE = "该附注章节不在您被分配的审计循环内"


@dataclass(frozen=True)
class CycleScope:
    """一个用户在一个项目上的可见范围：``None`` = 不限；空集 = 什么都看不到。"""

    codes: frozenset[str] | None
    sections: frozenset[str] | None

    @property
    def restricted(self) -> bool:
        return self.codes is not None or self.sections is not None


UNRESTRICTED = CycleScope(None, None)


def _uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


async def _mapped(func: Any, project_id: UUID, cycles: list[str], what: str) -> frozenset[str]:
    try:
        return frozenset(str(v) for v in await func(project_id, cycles))
    except Exception as exc:  # noqa: BLE001 — 取不到即不放行（与调整分录页同）
        logger.warning("循环范围：取循环%s失败 project=%s: %s", what, project_id, exc)
        return frozenset()


class CycleScopeCache:
    """一次请求一个实例；用户在实例上固定，按项目记忆平台入口的返回值与解析出的范围。"""

    def __init__(self, user: Any, db: AsyncSession) -> None:
        self._user = user
        self._db = db
        self._cycles: dict[UUID, list[str] | None] = {}
        self._scopes: dict[UUID, CycleScope] = {}

    @property
    def user(self) -> Any:
        return self._user

    async def cycles(self, project_id: Any) -> list[str] | None:
        """``deps.get_user_scope_cycles`` 的返回值（本模块唯一调用处；见模块说明里的保存点写法）。"""
        pid = _uuid(project_id)
        if pid in self._cycles:
            return self._cycles[pid]
        if role_value(self._user) in ALL_PROJECT_ROLES:
            # 系统 admin / partner 恒不限（ADR-AQL-19；平台入口对它们也不查库）：同构建器（design §3.4）不调用、不开保存点
            self._cycles[pid] = None
            return None
        sp = await self._db.begin_nested()
        try:
            value = await deps.get_user_scope_cycles(self._user, pid, self._db)
        except Exception as exc:  # noqa: BLE001 — 平台函数自身抛出（如主管分支的 project_cycles 在其 try 之外）
            logger.warning("循环范围读取失败 user=%s project=%s: %s", getattr(self._user, "id", None), pid, exc)
            value = []  # 受限空集（fail-closed）
        finally:
            await sp.rollback()  # 平台函数纯读：成败都回滚到保存点
        self._cycles[pid] = value
        return value

    async def scope(self, project_id: Any) -> CycleScope:
        pid = _uuid(project_id)
        if pid not in self._scopes:
            cycles = await self.cycles(pid)
            if cycles is None:
                self._scopes[pid] = UNRESTRICTED
            else:
                self._scopes[pid] = CycleScope(
                    await _mapped(mapping_service.get_codes_by_cycles, pid, cycles, "科目"),
                    await _mapped(mapping_service.get_sections_by_cycles, pid, cycles, "附注章节"),
                )
        return self._scopes[pid]

    async def is_restricted(self, project_id: Any) -> bool:
        return await self.cycles(project_id) is not None


async def resolve_cycle_scope(user: Any, project_id: Any, db: AsyncSession,
                              cache: CycleScopeCache | None = None) -> CycleScope:
    return await (cache or CycleScopeCache(user, db)).scope(project_id)


async def is_cycle_restricted(user: Any, project_id: Any, db: AsyncSession,
                              cache: CycleScopeCache | None = None) -> bool:
    return await (cache or CycleScopeCache(user, db)).is_restricted(project_id)


def section_out_of_scope(section: str) -> HTTPException:
    return HTTPException(status_code=403, detail={
        "error_code": SECTION_OUT_OF_SCOPE, "message": SECTION_OUT_OF_SCOPE_MESSAGE, "section": section,
    })


def sections_label(scope: CycleScope) -> str:
    """附注版本摘要里的循环章节集合（``*`` = 不限）。"""
    return "*" if scope.sections is None else ",".join(sorted(scope.sections))
