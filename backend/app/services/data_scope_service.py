"""Scope_Resolver —— 数据权限解析核心（dept-role-data-permission Task 2）

两个职责：
  1. `compute_effective_data_scope()` —— 多角色 data_scope 取**最大权限**（纯函数）
  2. `resolve_scope_project_ids()` —— 按 effective_data_scope 算出数据权限可见项目集合

⚠️ 本模块**不自己实现项目级可见性**（`project_users` / `partner_id` / `manager_id` /
   `project_members` / `created_by` 那 5 个来源），那是 `deps.py::_project_level_visible_ids`
   的职责。本模块产出的集合会与项目级集合做 **AND 交集**（Task 8.1），
   所以这里返回得再大也不会越权 —— 但返回 `None`（不过滤）是例外，务必只在 scope=1 用。

   📌 **例外：`scope=6`「我参与的项目」会转调那个函数**
      （`data-scope-participant-visibility` Req 3.2）。那是**转调**而非重新实现 ——
      5 个来源里有 3 处非显然细节（详见 scope=6 分支内注释），复制一份必漂移。
      转调用**函数内 import** 破环（`deps` 反向依赖本模块）。

📌 **为什么用 Protocol 而不直接 import LoginUser**：
   `LoginUser` Pydantic schema 属 Task 7.1（登录组装）的产物，而本模块是纯逻辑层、
   应能独立于鉴权链路被测试与复用。故这里只声明**结构化协议** `ScopeContext`
   —— 任何带 `user_id` / `effective_data_scope` / `custom_project_ids` 三个属性的对象
   都能传进来（`LoginUser` 天然满足）。附带好处是避免 services 之间的循环 import。

Validates: Requirements 6.1~6.5, 7.1~7.6, 4.4, 9.4, 10.5, 12.1, 12.2, 12.3
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from typing import Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.models.sys_permission import (
    DATA_SCOPE_ALL,
    DATA_SCOPE_CUSTOM,
    DATA_SCOPE_DEPT,
    DATA_SCOPE_DEPT_AND_CHILD,
    DATA_SCOPE_PARTICIPANT,
    DATA_SCOPE_SELF,
    DEPRECATED_DATA_SCOPES,
    VALID_DATA_SCOPES,
)

logger = logging.getLogger(__name__)

__all__ = [
    "DATA_SCOPE_ALL",
    "DATA_SCOPE_CUSTOM",
    "DATA_SCOPE_DEPT",
    "DATA_SCOPE_DEPT_AND_CHILD",
    "DATA_SCOPE_PARTICIPANT",
    "DATA_SCOPE_SELF",
    "DEPRECATED_DATA_SCOPES",
    "PRIORITY_ORDER",
    "VALID_DATA_SCOPES",
    "ScopeContext",
    "compute_effective_data_scope",
    "normalize_data_scope",
    "resolve_dept_project_ids",
    "resolve_scope_project_ids",
]


# ---------------------------------------------------------------------------
# 优先级序列
# ---------------------------------------------------------------------------

PRIORITY_ORDER: dict[int, int] = {
    DATA_SCOPE_ALL: 0,          # 1 全部数据 —— 权限最大
    DATA_SCOPE_CUSTOM: 1,       # 2 自定义项目
    DATA_SCOPE_PARTICIPANT: 2,  # 6 我参与的项目（恒 ⊇ scope=5，故排在它之前）
    DATA_SCOPE_SELF: 3,         # 5 仅本人 —— 权限最小
}
"""data_scope → 优先级序号（**数字越小权限越大**）。

「取最大权限」= 取 `PRIORITY_ORDER` 值最小者（argmin）。
⚠️ 不能直接对 data_scope 数值取 min/max：取值本身（1/2/5/6）不构成权限序
   —— 5（仅本人）是最小权限却不是最大数字，6（我参与的）权限更大却数字更大。
   加入 6 之后这一点更明显：`min([5, 6])` 会得到 5，方向完全相反。
   这是本模块最容易写错的地方。

🔴 **为什么 6 必须排在 5 之前 —— 这有数学依据，不是偏好**
   （`data-scope-participant-visibility` design D3.1）：

   设 `PL(u)` = 项目级 5 来源并集，`Own(u)` = `{p : p.created_by == u}`。
   来源 5 的定义即 `Own(u)`，而 `PL(u) = S1 ∪ S2 ∪ S3 ∪ S4 ∪ Own(u)`
   ⇒ **`Own(u) ⊆ PL(u)` 恒成立**（对任意账号、任意数据状态，不依赖夹具）。

   即 `scope5_result ⊆ scope6_result` ⇒ scope=6 的可见范围恒不小于 scope=5
   ⇒ 权限序必须是「6 优先于 5」。

   若排反（`{..., DATA_SCOPE_SELF: 2, DATA_SCOPE_PARTICIPANT: 3}`），一个同时
   绑了 scope=5 与 scope=6 角色的账号会 argmin 出 5，**看得比单绑 scope=6
   更少** —— 违反上游 Req 7.1「多角色取最大权限」的既有语义。

⚠️ **本表的键集必须恒等于 `VALID_DATA_SCOPES`**：
   `compute_effective_data_scope` 用 `PRIORITY_ORDER[s]` 查表，加了合法值却
   忘了排优先级会抛 `KeyError`（运行时才炸，不是启动期）。
   由 `tests/data_scope_participant/test_baseline_three_scopes.py::
   test_priority_order_covers_every_valid_scope` 钉住双向一致。
"""

_FALLBACK_WHEN_UNKNOWN = DATA_SCOPE_SELF
"""未知/废弃取值统一按**最小权限**处理（Req 7.6 / 12.3 的 fail-safe 方向）。"""


@runtime_checkable
class ScopeContext(Protocol):
    """`resolve_scope_project_ids` 需要的最小上下文（`LoginUser` 满足本协议）。"""

    user_id: UUID
    effective_data_scope: int
    custom_project_ids: Sequence[UUID] | set[UUID] | frozenset[UUID]


# ---------------------------------------------------------------------------
# compute_effective_data_scope —— 多角色取最大权限
# ---------------------------------------------------------------------------


def normalize_data_scope(scope: object) -> int:
    """把任意输入规整为**有效** data_scope，未知/废弃一律降为最小权限 5。

    这是 `compute_effective_data_scope` 与 `resolve_scope_project_ids` 共用的入口，
    保证两处对"什么算合法取值"的口径完全一致（Req 7.6 / 12.3）。

    - 3 / 4（部门维度，已废弃）→ 5 并记 warning
    - 非 int、None、0、7、-1 等未知值 → 5 并记 warning
    - bool 也算未知：`True == 1` 在 Python 里成立，若放行会让 `True` 静默变成
      「全部数据」这个最大权限 —— 方向与 fail-safe 相反，故显式拦掉。
    """
    if isinstance(scope, bool) or not isinstance(scope, int):
        logger.warning(
            "[data_scope] 非法类型 %r（%s）→ 按最小权限 %d 处理",
            scope, type(scope).__name__, _FALLBACK_WHEN_UNKNOWN,
        )
        return _FALLBACK_WHEN_UNKNOWN

    if scope in VALID_DATA_SCOPES:
        return scope

    if scope in DEPRECATED_DATA_SCOPES:
        logger.warning(
            "[data_scope] 已废弃取值 %d（部门维度不实现）→ 降级为仅本人（%d）",
            scope, _FALLBACK_WHEN_UNKNOWN,
        )
        return _FALLBACK_WHEN_UNKNOWN

    logger.warning(
        "[data_scope] 未知取值 %d（有效集合 %s）→ 按最小权限 %d 处理",
        scope, sorted(VALID_DATA_SCOPES), _FALLBACK_WHEN_UNKNOWN,
    )
    return _FALLBACK_WHEN_UNKNOWN


def compute_effective_data_scope(
    role_scopes: Iterable[object],
    fallback_scope: int = _FALLBACK_WHEN_UNKNOWN,
) -> int:
    """多角色 data_scope 取**最大权限**。

    Args:
        role_scopes: 该账号绑定的全部角色的 data_scope（可含重复、未知值、废弃值）。
        fallback_scope: 列表为空时的回退值 —— 由调用方按 `users.role` 枚举对应的
            seed 角色 data_scope 传入（Req 4.4 / 10.5）。**不是**系统级默认配置。

    Returns:
        有效 data_scope（恒 ∈ {1, 2, 5}）。

    语义（Req 7.1~7.6）：
      - 任一为 1 → 短路返回 1（最大权限）
      - 否则取 `PRIORITY_ORDER` 最小者（argmin）
      - 空列表 → 规整后的 `fallback_scope`
      - 未知/废弃取值按 5 参与比较并告警

    顺序无关且幂等：结果只取决于输入的**集合**，与顺序、重复次数无关（Property 5）。
    """
    normalized = [normalize_data_scope(s) for s in role_scopes]

    if not normalized:
        # 空列表不是错误：账号可能尚未在 sys_user_role 建立任何绑定（历史账号）。
        # 此时按其 users.role 枚举对应的 seed 角色解析（调用方负责传入）。
        resolved_fallback = normalize_data_scope(fallback_scope)
        logger.debug(
            "[data_scope] 无角色绑定 → 回退为 %d（来源：调用方按 users.role 传入）",
            resolved_fallback,
        )
        return resolved_fallback

    # 短路：1 是最大权限，出现即可直接返回（Req 7.2）
    if DATA_SCOPE_ALL in normalized:
        return DATA_SCOPE_ALL

    # argmin over PRIORITY_ORDER —— 不是 min(normalized)！
    # 反例：[2, 5] 若取 min 得 2（碰巧对），但 [1, 5] 取 min 得 1（对）、
    #       [2, 1] 取 min 得 1（对）…… 数值巧合在 {1,2,5} 上大多成立，
    #       却在语义上是错的：一旦有效集合改成含 3，min 立刻给出错误答案。
    #       故一律走 PRIORITY_ORDER。
    return min(normalized, key=lambda s: PRIORITY_ORDER[s])


# ---------------------------------------------------------------------------
# resolve_scope_project_ids —— 按 data_scope 算数据权限可见项目集合
# ---------------------------------------------------------------------------


async def resolve_scope_project_ids(
    login_user: ScopeContext,
    db: AsyncSession,
) -> set[UUID] | None:
    """按 `effective_data_scope` 返回数据权限可见项目 ID 集合。

    Returns:
        - `None` —— **不过滤**（scope=1，全部未删除项目可见）。
          ⚠️ 语义上区别于空集：`None` 是"放行全部"，`set()` 是"什么都不可见"。
          调用方（Task 8.1）必须分别处理，混淆会导致越权或全盲。
        - `set()` —— 空集，什么都不可见（scope=2 且 custom_project_ids 为空）。
        - 非空 set —— 具体可见项目 id。

    四种范围（均含 `is_deleted == False`）：
      | scope | 过滤条件 |
      |---|---|
      | 1 全部 | 返回 None |
      | 2 自定义 | `projects.id IN custom_project_ids`（sys_role_project 并集） |
      | 6 我参与的 | **转调** `deps._project_level_visible_ids`（项目级 5 来源并集） |
      | 5 仅本人 | `projects.created_by == user_id` |
      | 3/4 废弃 | 降级为 5 并告警 |

    ⚠️ **scope=6 与 scope=5 的关系**：`created_by` 本身就是项目级 5 来源之一
       ⇒ `scope=5 的结果 ⊆ scope=6 的结果` 恒成立。这是 `PRIORITY_ORDER` 里
       6 排在 5 之前的依据。

    ⚠️ **scope=6 的一个推论**：`get_visible_project_ids` = 项目级 ∩ 数据权限，
       而 scope=6 的数据权限集**就是**项目级集 ⇒ 交集 = 项目级本身
       ⇒ 对这类账号，数据权限维度**不再收窄**。这是设计意图（"我参与的都能看到"），
       不是"交集失效了"。

    Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 9.4, 12.1, 12.2, 12.3
                （data-scope-participant-visibility: 3.1~3.5, 4.1）
    """
    scope = normalize_data_scope(getattr(login_user, "effective_data_scope", None))

    # ---- scope=1：不过滤 ----
    if scope == DATA_SCOPE_ALL:
        return None

    # ---- scope=2：自定义项目并集 ----
    if scope == DATA_SCOPE_CUSTOM:
        raw_ids = getattr(login_user, "custom_project_ids", None) or []
        custom_ids = {UUID(str(pid)) for pid in raw_ids}

        if not custom_ids:
            # 🔴 安全兜底（Req 9.4 / 12.1 / 12.2）：并集为空必须返回**空集**，
            #    绝不能返回 None（=放行全部）或抛异常。
            #    这条方向弄反就是越权 —— 一个没配任何项目的角色反而能看全部。
            logger.info(
                "[data_scope] 账号 %s 的 data_scope=2 但 custom_project_ids 为空 "
                "→ 返回空集（安全兜底，不放行全部）",
                getattr(login_user, "user_id", "?"),
            )
            return set()

        rows = await db.execute(
            select(Project.id).where(
                Project.id.in_(custom_ids),
                Project.is_deleted == False,  # noqa: E712
            )
        )
        # 用 DB 实际存在且未软删的行收窄 —— custom_project_ids 里可能残留已被
        # 硬删/软删的项目 id（角色绑定表虽有 FK CASCADE，但软删不触发 CASCADE）。
        return {r[0] for r in rows.all()}

    # ---- scope=6：我参与的项目（项目级 5 来源并集）----
    if scope == DATA_SCOPE_PARTICIPANT:
        participant_user_id = getattr(login_user, "user_id", None)
        if participant_user_id is None:
            # 与 scope=5 同一 fail-safe 手法：拿不到账号 id 时给空集，
            # **绝不** None（那是"放行全部"）。
            logger.warning(
                "[data_scope] scope=%d 但 login_user 无 user_id → 返回空集（安全兜底）",
                scope,
            )
            return set()

        # 🔴 **函数内 import，不得上提到模块级**：`deps.py` 会（在函数内）
        #    import 本模块的 `resolve_scope_project_ids`，模块级反向 import
        #    会形成环。上游 `project_role_tree_service` 用的是同一手法。
        #    由 `tests/data_scope_participant/test_scope_participant.py::
        #    test_module_level_has_no_deps_import` 钉住。
        from app.deps import _project_level_visible_ids
        from app.models.core import User as _User

        # ⚠️ **需要 ORM User 对象而非 user_id**：`_project_level_visible_ids`
        #    读 `current_user.role.value` 来判 admin/partner 分支，而
        #    `ScopeContext` 协议只给 `user_id: UUID` ⇒ 必须先查一次。
        #    刻意**不**把 User 加进 ScopeContext 协议 —— 那会波及 `LoginUser`
        #    与全部既有调用方（design D2.2）。
        participant_user = (
            await db.execute(select(_User).where(_User.id == participant_user_id))
        ).scalar_one_or_none()
        if participant_user is None:
            # user_id 来自已通过鉴权的 LoginUser，查不到只可能是并发软删/硬删
            # ⇒ fail-safe 取最小权限。
            logger.warning(
                "[data_scope] scope=%d 但账号 %s 不存在 → 返回空集（安全兜底）",
                scope, participant_user_id,
            )
            return set()

        # 🔴 **转调，刻意不实现任何同语义查询**：那 5 个来源里有 3 处非显然细节，
        #    重写必漂移，且漏掉任何一处都会让**结果偏大 = 越权**：
        #      ① 来源1 `ProjectUser` 需 JOIN Project 过滤**项目**软删
        #         （2026-08-21 修过的既有安全缺陷，绑定行活着但项目已删）
        #      ② 来源4 `project_members` **无 `is_deleted` 列**，只能靠 JOIN 兜
        #      ③ 来源5 `created_by` 靠 SQL 三值逻辑天然排除 NULL
        #    ⇒ 由 `test_scope_participant.py::test_delegates_not_reimplements`
        #      做 AST 守卫：本分支必须出现对 `_project_level_visible_ids` 的调用、
        #      且不得出现 `select(Project`。
        #
        # ⚠️ admin/partner 走到这里是**安全**的：他们的 effective_data_scope 被
        #    上游的「权限地板」（Req 10.6）恒抬到 1 ⇒ 在 scope=1 分支就已 return
        #    None，走不到这里。即便哪天地板被撤、admin 被绑了 scope=6 的角色，
        #    结果 = 全部未删除项目，与 admin 应有范围一致，不构成越权。
        return set(await _project_level_visible_ids(participant_user, db))

    # ---- scope=5（含 3/4 降级）：仅本人创建 ----
    # normalize_data_scope 已把 3/4 转成 5 并记 warning，此处无需重复判断；
    # 走到这里 scope 必为 DATA_SCOPE_SELF。
    user_id = getattr(login_user, "user_id", None)
    if user_id is None:
        # 拿不到账号 id 时不能返回 None（放行全部），按最小权限给空集。
        logger.warning(
            "[data_scope] scope=%d 但 login_user 无 user_id → 返回空集（安全兜底）",
            scope,
        )
        return set()

    rows = await db.execute(
        select(Project.id).where(
            Project.created_by == user_id,
            Project.is_deleted == False,  # noqa: E712
        )
    )
    result = {r[0] for r in rows.all()}
    if not result:
        # 不是错误，但值得记一笔：本库历史项目的 created_by 曾全为 NULL
        # （Task 1.6 才补上写入路径），老数据上此范围为空属预期。
        logger.debug(
            "[data_scope] 账号 %s 的 scope=5 结果为空集（其名下无未删除项目）", user_id
        )
    return result


# 向后兼容别名：早期设计称之为 dept（部门维度），现已改为项目维度。
# 保留别名以免外部调用方（若有）断裂；新代码一律用 resolve_scope_project_ids。
resolve_dept_project_ids = resolve_scope_project_ids
