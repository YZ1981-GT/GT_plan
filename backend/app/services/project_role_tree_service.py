"""Tree_Assembly_Service —— 用户 → 项目 → 角色 三层树的只读组装
（project-data-permission-isolation Task 2.1~2.3）

═══════════════════════════════════════════════════════════════════════════
🔴 纯读：全模块只有 SELECT，无 flush / commit / add / delete
═══════════════════════════════════════════════════════════════════════════
Req 6.4 明确要求本服务不提供任何修改 `project_users` / `sys_role` /
`sys_user_role` / `sys_role_project` 的能力。有 Property 9 的属性测试盯着
"调用前后各表行数不变"。

═══════════════════════════════════════════════════════════════════════════
🔴 主体是「被查看的目标用户」，不是「当前登录的管理员」
═══════════════════════════════════════════════════════════════════════════
**刻意不调用 `deps.py::get_visible_project_ids`** —— 那个函数的主体是当前请求
的 token 持有者（"看的人"），而本 spec 要算的是"被看的那个账号能看到什么"。
若误用它，管理员查看任何账号都会得到自己的可见集，整个 out_of_scope 标记
全错且**看不出错**（管理员通常 scope=1，标记会全为 False，像是"一切正常"）。

改为组合两个以 `User` 为输入、不碰 token 的既有函数：
  1. `deps.py::_project_level_visible_ids(target_user, db)` —— 项目级 4 来源并集
  2. `data_scope_service.resolve_scope_project_ids(login_user, db)` —— 数据权限集

⚠️ **`_project_level_visible_ids` 是直接复用而非重实现**（它在 `deps.py`
   第 522 行）。自行按"同语义"重写必然与它漂移 —— 它的 4 个来源里有两处
   非显然的细节（来源 1 要 JOIN Project 过滤项目软删；来源 4 的
   `project_members` 表没有 `is_deleted` 列），漏掉任一处都会让结果**偏大**，
   而偏大方向就是越权。

Validates: Requirements 1.1~1.5, 2.1~2.5, 5.1, 5.2, 5.5, 6.4, 7.1~7.3
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project, ProjectUser, User
from app.schemas.project_role_tree import (
    ProjectNode,
    RoleNode,
    UserNode,
    UserSubtree,
    data_scope_label,
)

logger = logging.getLogger("audit_platform.project_role_tree")

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
"""单页上限。6000 账号规模下靠 el-tree 懒加载分页，不允许一次拉全量。"""


def _enum_value(v: object) -> str:
    """取枚举的 `.value`，已是字符串则原样返回。

    ⚠️ 库里可能存在 ORM 枚举尚未收录的历史值（本仓 `ProjectUserRole` 就因
       V109 补过 `eqcr`），此时 SQLAlchemy 可能给出裸字符串而非 Enum 成员
       ⇒ 必须两种形态都能处理，否则整棵树会因一行脏数据打不开。
    """
    return v.value if hasattr(v, "value") else str(v)


class TreeAssemblyService:
    """三层树的只读组装服务。

    无状态（所有方法都是 `staticmethod` 语义上的纯函数 + db 参数），
    刻意不在 `__init__` 里持 db —— 让调用方对"每次查询用哪个会话"保持显式。
    """

    # -----------------------------------------------------------------
    # 根层：用户节点列表（Task 2.1）
    # -----------------------------------------------------------------

    @staticmethod
    async def list_user_nodes(
        db: AsyncSession,
        *,
        search: str | None = None,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> tuple[list[UserNode], int]:
        """返回根层用户节点分页 + 过滤后总数（Req 1.1~1.5）。

        Args:
            search: 用户名或邮箱关键字（ILIKE 模糊匹配），None/空串 = 不过滤
            page: 页码，从 1 起；<1 的值按 1 处理
            page_size: 单页条数，超过 `MAX_PAGE_SIZE` 按上限截断

        Returns:
            `(用户节点列表, 过滤后的未删除账号总数)`

        🔴 **`has_children` 用一次聚合查询批量算，不逐账号查**（Req 7.1）：
           逐账号查是根层 N+1 —— 50 条/页就是 51 次查询，6000 账号规模下
           翻页体验会崩。有 Property 12 的 N+1 守卫盯着查询次数。
        """
        page = max(1, page)
        page_size = max(1, min(page_size, MAX_PAGE_SIZE))

        base = select(User).where(User.is_deleted == False)  # noqa: E712
        count_q = select(func.count()).select_from(User).where(
            User.is_deleted == False  # noqa: E712
        )

        kw = (search or "").strip()
        if kw:
            # ⚠️ 转义 LIKE 元字符：用户搜 `100%` 时不该匹配到所有账号。
            #    `%` 与 `_` 在 LIKE 里是通配符。
            escaped = kw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            # 🔴 **`escape=` 参数必须传**：`ilike(pattern)` 默认**不生成 `ESCAPE`
            #    子句**（实测 PG 与 SQLite 编译结果均无），此时上面那些反斜杠会被当
            #    **字面量** ⇒ 搜 `100%` 变成"找含 `\%` 的字符串"，一条都返回不了
            #    —— 比完全不转义更糟（不转义至少还能匹配到东西，只是范围过宽）。
            #    带上 escape 后 SQL 里才有 `ESCAPE '\'`。
            cond = User.username.ilike(pattern, escape="\\") | User.email.ilike(
                pattern, escape="\\"
            )
            base = base.where(cond)
            count_q = count_q.where(cond)

        total = int((await db.execute(count_q)).scalar_one())

        rows = (
            await db.execute(
                base.order_by(User.username)
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        ).scalars().all()

        page_ids = [u.id for u in rows]
        with_children = await TreeAssemblyService._user_ids_having_projects(
            db, page_ids
        )

        nodes = [
            UserNode(
                id=u.id,
                username=u.username,
                full_name=u.full_name,
                email=u.email,
                system_role=_enum_value(u.role),
                is_active=bool(u.is_active),
                has_children=u.id in with_children,
            )
            for u in rows
        ]
        return nodes, total

    @staticmethod
    async def _user_ids_having_projects(
        db: AsyncSession, user_ids: list[UUID]
    ) -> set[UUID]:
        """一次聚合查出「这批账号里哪些有活跃项目绑定」（避免根层 N+1）。

        🔴 **必须 JOIN Project 过滤项目自身的软删**，与
           `deps.py::_project_level_visible_ids` 来源 1 同口径：
           只看 `ProjectUser.is_deleted` 会让"绑定行活着但项目已软删"的账号
           被标成 `has_children=True`，展开后却是空列表 —— 前端 el-tree
           懒加载遇到"说有孩子结果没有"会留下一个永远转圈的加载态。
        """
        if not user_ids:
            return set()

        rows = (
            await db.execute(
                select(ProjectUser.user_id)
                .join(Project, Project.id == ProjectUser.project_id)
                .where(
                    ProjectUser.user_id.in_(user_ids),
                    ProjectUser.is_deleted == False,  # noqa: E712
                    Project.is_deleted == False,  # noqa: E712
                )
                .group_by(ProjectUser.user_id)
            )
        ).all()
        return {r[0] for r in rows}

    # -----------------------------------------------------------------
    # 单用户子树：项目层 + 角色层 + 数据权限视角（Task 2.2 / 2.3）
    # -----------------------------------------------------------------

    @staticmethod
    async def get_user_project_role_subtree(
        db: AsyncSession, user_id: UUID
    ) -> UserSubtree:
        """返回目标账号的项目层 + 角色层，并标注数据权限可见性（Req 2.1~2.5, 5.1~5.4）。

        Raises:
            ValueError: 账号不存在或已软删 —— 由 router 转 **404**「账号不存在」
                （Req 2.5）。刻意抛 ValueError 而非 HTTPException：
                服务层不该依赖 FastAPI，否则无法脱离 web 框架做单元测试。

        🔴 **异常绝不降级为「全部可见」**（Req 5.5 + 本 spec 铁律）：
           数据权限计算若失败，`out_of_scope` 会**全部标 True**（如实标记不可见）
           而不是全 False。方向选择的依据：标错成"不可见"只是显示保守，
           标错成"可见"会让管理员误判某账号的权限边界 —— 后者是安全问题。
        """
        target = (
            await db.execute(
                select(User).where(
                    User.id == user_id,
                    User.is_deleted == False,  # noqa: E712
                )
            )
        ).scalar_one_or_none()
        if target is None:
            raise ValueError("账号不存在")

        # ---- 1) 项目层 + 角色层（一次 JOIN 查全，无 N+1）----
        rows = (
            await db.execute(
                select(
                    Project.id,
                    Project.name,
                    Project.client_name,
                    Project.status,
                    ProjectUser.role,
                    ProjectUser.permission_level,
                    ProjectUser.valid_from,
                    ProjectUser.valid_to,
                    ProjectUser.scope_cycles,
                    ProjectUser.scope_accounts,
                )
                .join(ProjectUser, ProjectUser.project_id == Project.id)
                .where(
                    ProjectUser.user_id == user_id,
                    ProjectUser.is_deleted == False,  # noqa: E712
                    Project.is_deleted == False,  # noqa: E712
                )
                .order_by(Project.name)
            )
        ).all()

        # ---- 2) 数据权限视角（Req 5.1 / 5.2）----
        effective_scope, scope_ids, degraded = (
            await TreeAssemblyService._resolve_scope_view(db, target)
        )

        projects: list[ProjectNode] = []
        for r in rows:
            pid = r[0]
            if degraded:
                # 计算失败 ⇒ 如实标记不可见（见上方方向说明）
                out_of_scope = True
            elif scope_ids is None:
                # 🔴 `None` = 不过滤（scope=1）⇒ **全部可见**，不是全部不可见。
                #    这里若写成 True，管理员会看到"admin 的所有项目都不可见"
                #    这种荒谬结论 —— 而它恰恰是最容易写反的一处。
                out_of_scope = False
            else:
                out_of_scope = pid not in scope_ids

            projects.append(
                ProjectNode(
                    project_id=pid,
                    name=r[1],
                    client_name=r[2],
                    status=_enum_value(r[3]),
                    out_of_scope=out_of_scope,
                    role=RoleNode(
                        role=_enum_value(r[4]),
                        permission_level=_enum_value(r[5]),
                        valid_from=r[6],
                        valid_to=r[7],
                        scope_cycles=r[8],
                        scope_accounts=r[9],
                    ),
                )
            )

        return UserSubtree(
            user_id=user_id,
            effective_data_scope=effective_scope,
            effective_data_scope_label=data_scope_label(effective_scope),
            projects=projects,
        )

    @staticmethod
    async def _resolve_scope_view(
        db: AsyncSession, target: User
    ) -> tuple[int, set[UUID] | None, bool]:
        """算目标账号的 `effective_data_scope` 与数据权限可见项目集。

        Returns:
            `(effective_data_scope, scope_ids, degraded)`
              - `scope_ids is None` ⇒ 不过滤（scope=1）
              - `scope_ids == set()` ⇒ 什么都不可见
              - `degraded=True` ⇒ 计算失败，调用方应把所有节点标为不可见

        ⚠️ **只调用不重算**（Req 5.5）：`effective_data_scope` 取自
           `assemble_login_user` 的结果，不在这里用
           `compute_effective_data_scope` 再算一遍 —— 重算会与登录态的口径
           漂移（例如角色在两次之间被改动），导致"树上显示的范围"与
           "实际生效的范围"不一致。
        """
        # 延迟 import：避免 `services → deps → services` 的循环依赖
        from app.services.login_user_service import assemble_login_user

        try:
            login_user = await assemble_login_user(target, db)
        except Exception:
            logger.exception(
                "[project_role_tree] 组装账号 %s 的 LoginUser 失败 ⇒ "
                "按最小权限展示（全部项目标记为不可见）",
                target.id,
            )
            # 拿不到 scope 时给最小权限值 5，而不是 1 —— 显示保守优于误示宽松
            return 5, set(), True

        try:
            from app.services.data_scope_service import resolve_scope_project_ids

            scope_ids = await resolve_scope_project_ids(login_user, db)
        except Exception:
            logger.exception(
                "[project_role_tree] 解析账号 %s 的数据权限可见集失败 ⇒ "
                "全部项目标记为不可见",
                target.id,
            )
            return login_user.effective_data_scope, set(), True

        return login_user.effective_data_scope, scope_ids, False

    # -----------------------------------------------------------------
    # 项目级可见集（供需要时对照，Task 2.3）
    # -----------------------------------------------------------------

    @staticmethod
    async def project_level_visible_ids(
        db: AsyncSession, target: User
    ) -> list[UUID]:
        """目标账号的**项目级**可见集 —— 直接委托 `deps.py::_project_level_visible_ids`。

        🔴 **本方法只是转调，刻意不实现任何逻辑**。存在的意义是把"复用而非
           重写"这件事在代码里固定下来：`_project_level_visible_ids` 的 4 个来源
           有两处非显然细节（来源 1 需 JOIN Project 过滤项目软删；来源 4 的
           `project_members` 无 `is_deleted` 列），任何重写都容易漏掉其中一处，
           而漏掉的方向是结果**偏大** = 越权。

        ⚠️ 它以 `User` 为输入、不碰 token，可安全用于"目标用户"视角。
        """
        from app.deps import _project_level_visible_ids

        return await _project_level_visible_ids(target, db)


__all__ = ["DEFAULT_PAGE_SIZE", "MAX_PAGE_SIZE", "TreeAssemblyService"]
